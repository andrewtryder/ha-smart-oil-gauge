"""Tests for upload-schedule tracking and poll timing.

The main scenario replays a real gauge: an interval change on the portal
took effect about a day later, not at the next upload.
"""

from __future__ import annotations

import pytest

from custom_components.smart_oil_gauge.schedule import (
    GRACE_S,
    MAX_DELAY_S,
    MIN_DELAY_S,
    TankSchedule,
    next_poll_delay,
)

H = 3600.0
T0 = 1_795_035_543.0  # an upload at 3:58 PM


def test_first_config_is_assumed_in_effect() -> None:
    """A newly seen gauge is assumed to use the portal interval."""
    sched = TankSchedule()
    sched.update_configured(12, 2, T0)
    assert (sched.configured_h, sched.effective_h, sched.num_tanks) == (12, 12, 2)
    assert not sched.pending
    assert sched.interval() == (12.0, "portal")
    assert sched.candidates(T0) == [T0 + 12 * H]
    assert sched.next_expected(T0, T0 + H) == T0 + 12 * H


def test_real_change_takes_effect_a_day_later() -> None:
    """12h -> 1h: the gauge kept 12h for two more uploads before switching."""
    sched = TankSchedule()
    sched.update_configured(12, 1, T0)
    sched.record_upload(T0)
    sched.record_upload(T0 + 12 * H)  # confirms 12h
    assert sched.interval() == (12.0, "observed")

    # Changed to 1 hour on the portal in the evening.
    changed_at = T0 + 13 * H
    sched.update_configured(1, 1, changed_at)
    assert sched.pending
    assert sched.pending_since == changed_at
    last = T0 + 24 * H  # next 4:00 AM upload: still 12 hours later
    sched.record_upload(last)
    assert sched.pending
    assert sched.effective_h == 12
    # Either interval is possible now.
    assert sched.candidates(last) == [last + H, last + 12 * H]
    # At 5:10 AM the 1-hour slot has passed; the display never shows the past.
    assert sched.next_expected(last, last + H + 600) == last + 12 * H
    assert not sched.overdue(last, last + H + 600)

    last += 12 * H  # 4:00 PM, still 12 hours
    sched.record_upload(last)
    assert sched.pending
    last += H  # 5:00 PM: the gauge now follows 1 hour
    sched.record_upload(last)
    assert not sched.pending
    assert sched.pending_since is None
    assert sched.effective_h == 1
    assert sched.candidates(last) == [last + H]


def test_pending_stays_through_old_interval_uploads() -> None:
    """1h -> 2h: hourly uploads keep coming until the gauge picks it up."""
    sched = TankSchedule(configured_h=1, effective_h=1, confirmed=True)
    last = T0
    sched.record_upload(last)
    sched.update_configured(2, 1, last + 0.5 * H)
    for _ in range(3):
        last += H
        sched.record_upload(last)
        assert sched.pending
        assert sched.effective_h == 1
    last += 2 * H
    sched.record_upload(last)
    assert not sched.pending
    assert sched.effective_h == 2


def test_missed_upload_is_not_a_new_interval() -> None:
    """A double-length gap on an unchanged setting is a missed upload."""
    sched = TankSchedule()
    sched.update_configured(1, 1, T0)
    sched.record_upload(T0)
    sched.record_upload(T0 + 2 * H)
    assert sched.effective_h == 1
    assert not sched.pending


def test_consistent_gaps_override_both_settings() -> None:
    """Two matching gaps that fit neither setting are trusted."""
    sched = TankSchedule()
    sched.update_configured(12, 1, T0)
    for i in range(3):
        sched.record_upload(T0 + i * 5 * H + i * 60)
    assert sched.effective_h == 5
    assert sched.interval() == (5.0, "observed")
    assert sched.pending


def test_irregular_gaps_are_ignored() -> None:
    """Gaps that aren't close to whole hours change nothing."""
    sched = TankSchedule()
    sched.update_configured(12, 1, T0)
    sched.record_upload(T0)
    sched.record_upload(T0 + 7.5 * H)
    assert sched.effective_h == 12
    assert sched.measured_h() is None


def test_unknown_and_measured_only() -> None:
    """Without a readable setting, measured gaps are used; else unknown."""
    sched = TankSchedule()
    assert sched.interval() == (None, "unknown")
    assert sched.candidates(T0) == []
    assert sched.candidates(None) == []
    assert sched.next_expected(T0, T0) is None
    assert not sched.overdue(T0, T0)
    for i in range(3):
        sched.record_upload(T0 + i * 12 * H)
    assert sched.interval() == (pytest.approx(12.0), "observed")
    assert sched.candidates(T0) == [pytest.approx(T0 + 12 * H)]


def test_expected_upload_shown_until_the_sync_after_it() -> None:
    """During the 5-minute grace after an expected upload it is still shown."""
    sched = TankSchedule(configured_h=2, effective_h=1)
    slot_1h, slot_2h = T0 + H, T0 + 2 * H
    assert sched.next_expected(T0, slot_1h + 60) == slot_1h  # "1 minute ago"
    assert not sched.overdue(T0, slot_1h + 60)
    assert sched.next_expected(T0, slot_1h + GRACE_S - 1) == slot_1h
    # The sync at +5 minutes moves on to the next possible upload.
    assert sched.next_expected(T0, slot_1h + GRACE_S) == slot_2h
    # Same for the last slot: shown during its grace, then unknown.
    assert sched.next_expected(T0, slot_2h + 60) == slot_2h
    assert sched.next_expected(T0, slot_2h + GRACE_S) is None
    assert sched.overdue(T0, slot_2h + GRACE_S)


def test_overdue_when_every_slot_passed() -> None:
    """Overdue only after every possible upload time has passed."""
    sched = TankSchedule(configured_h=1, effective_h=12)
    assert not sched.overdue(T0, T0 + 2 * H)
    assert sched.overdue(T0, T0 + 13 * H)
    assert sched.next_expected(T0, T0 + 13 * H) is None


def test_setting_changed_back_clears_pending() -> None:
    """Changing the portal back to the interval in use clears pending."""
    sched = TankSchedule()
    sched.update_configured(12, 1, T0)
    sched.update_configured(1, 1, T0 + H)
    assert sched.pending_since == T0 + H
    sched.update_configured(12, 1, T0 + 2 * H)
    assert not sched.pending
    assert sched.pending_since is None
    sched.update_configured(12, None, T0 + 3 * H)
    sched.update_configured(None, None, T0 + 3 * H)
    assert sched.configured_h == 12


def test_record_upload_ignores_repeats_and_keeps_recent() -> None:
    """The same upload is recorded once; only recent uploads are kept."""
    sched = TankSchedule()
    sched.record_upload(T0)
    sched.record_upload(T0)
    assert sched.upload_times == [T0]
    for i in range(1, 10):
        sched.record_upload(T0 + i * H)
    assert len(sched.upload_times) == 6


def test_storage_round_trip_and_garbage() -> None:
    """Schedules survive storage; malformed values are dropped."""
    sched = TankSchedule(
        configured_h=1, effective_h=12, num_tanks=2, pending_since=T0, confirmed=True
    )
    sched.upload_times = [T0, T0 + 12 * H]
    again = TankSchedule.from_dict(sched.as_dict())
    assert again.as_dict() == sched.as_dict()
    assert again.pending
    bad = TankSchedule.from_dict(
        {
            "configured_h": "x",
            "effective_h": 99,
            "num_tanks": 2,
            "upload_times": "no",
            "pending_since": "x",
        }
    )
    assert (bad.configured_h, bad.effective_h, bad.upload_times) == (None, None, [])
    assert bad.pending_since is None
    assert TankSchedule.from_dict(None).as_dict() == TankSchedule().as_dict()


def test_next_poll_shortly_after_expected_upload() -> None:
    """Poll a few minutes after the earliest expected upload."""
    expected = T0 + 12 * H
    delay, at = next_poll_delay(expected - H, [expected, expected + 3 * H], 6 * H)
    assert at == expected + GRACE_S
    assert delay == pytest.approx(H + GRACE_S)


def test_missed_slot_gets_short_retries_then_waits_for_the_next() -> None:
    """A passed slot gets a few retries; then polling waits for the next slot."""
    slot_1h, slot_12h = T0 + H, T0 + 12 * H
    due = slot_1h + GRACE_S
    assert next_poll_delay(due + 1, [slot_1h, slot_12h], 6 * H)[1] == due + 15 * 60
    assert next_poll_delay(due + 46 * 60, [slot_1h, slot_12h], 6 * H)[1] == (
        due + 105 * 60
    )
    # After the last retry, no hourly polling: wait for the 12-hour slot.
    _, at = next_poll_delay(due + 106 * 60, [slot_1h, slot_12h], 6 * H)
    assert at == slot_12h + GRACE_S


def test_hourly_retries_once_nothing_else_expected() -> None:
    """With every slot passed, retries continue hourly."""
    due = T0 + GRACE_S
    assert next_poll_delay(due + 1, [T0], 6 * H)[1] == due + 15 * 60
    assert next_poll_delay(due + 106 * 60, [T0], 6 * H)[1] == due + 165 * 60
    assert next_poll_delay(due + 10 * H, [T0], 6 * H)[1] == due + 105 * 60 + 9 * H


def test_next_poll_bounds_and_fallback() -> None:
    """Delays stay within bounds; no expectations means the fallback."""
    # A 24-hour gauge is waited for, not polled in between.
    assert next_poll_delay(T0, [T0 + 24 * H], 6 * H)[0] == 24 * H + GRACE_S
    assert next_poll_delay(T0, [T0 + 30 * H], 6 * H)[0] == MAX_DELAY_S
    assert next_poll_delay(T0, [T0 - GRACE_S + 5], 6 * H)[0] == MIN_DELAY_S
    assert next_poll_delay(T0, [], 3 * H)[0] == 3 * H
