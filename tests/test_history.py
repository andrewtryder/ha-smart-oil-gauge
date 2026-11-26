"""Tests for the pure hourly-history helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.smart_oil_gauge import history as h

FIXTURES = Path(__file__).parent / "fixtures"
NY = ZoneInfo("America/New_York")


def _graph_series() -> h.Series:
    return h.parse_graph_points(json.loads((FIXTURES / "graph_data.json").read_text()))


def test_parse_graph_points_page_shape() -> None:
    """The web page's renamed ``main`` dataset parses the same way."""
    raw = json.loads((FIXTURES / "graph_data.json").read_text())
    renamed = {**raw, "datasets": {"main": raw["datasets"]["71796"]}}
    assert h.parse_graph_points(renamed) == _graph_series()


def test_parse_graph_points_real_week() -> None:
    """The real week of readings parses into an hourly series."""
    series = _graph_series()
    assert len(series) == 172
    assert series[-1] == (1794992258.0, 201.41)
    gaps = [b[0] - a[0] for a, b in zip(series, series[1:], strict=False)]
    assert max(gaps) < 3700


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"datasets": None},
        {"datasets": {"main": None}},
        {"datasets": {"main": {"week": None, "day": {"points": None}}}},
        {"datasets": {"main": {"week": {"points": [None, {"ts": "x"}, {}]}}}},
    ],
)
def test_parse_graph_points_malformed(payload) -> None:
    """Malformed payloads produce an empty series instead of raising."""
    assert h.parse_graph_points(payload) == []


def test_merge_series_dedupes_and_prefers_later_sources() -> None:
    """Close timestamps merge; the later source wins; non-finite values drop."""
    merged = h.merge_series(
        [(100.0, 1.0), (3700.0, 2.0), (float("nan"), 5.0)],
        [(130.0, 1.5), (7300.0, 3.0)],
    )
    assert merged == [(100.0, 1.5), (3700.0, 2.0), (7300.0, 3.0)]


def test_trim_and_value_at() -> None:
    """Trimming keeps newer points; value_at is a step function."""
    series = [(10.0, 1.0), (20.0, 2.0), (30.0, 3.0)]
    assert h.trim_series(series, 20.0) == [(30.0, 3.0)]
    assert h.value_at(series, 5.0) is None
    assert h.value_at(series, 25.0) == 2.0


def test_parse_export_csv() -> None:
    """CSV rows parse in order; junk rows are skipped; bad headers raise."""
    text = 'Time,Gallons\n"2026-11-16 00:51:31",65.62\nbad,row\n"x",1\n\n'
    rows = h.parse_export_csv(text)
    assert rows == [(datetime(2026, 11, 16, 0, 51, 31), 65.62)]
    with pytest.raises(ValueError):
        h.parse_export_csv("<html>login</html>")


def test_localize_rows_resolves_fall_back_hour() -> None:
    """The repeated 1 AM hour on the fall-back day maps an hour apart."""
    rows = h.parse_export_csv((FIXTURES / "export_dst.csv").read_text())
    series = h.localize_rows(rows, NY, 0)
    stamps = [datetime.fromtimestamp(ts, UTC).hour for ts, _ in series]
    assert stamps == [2, 3, 4, 5, 6, 7, 8, 9]


def test_localize_rows_fixed_offset_and_out_of_order() -> None:
    """A fixed offset is applied and out-of-order rows are dropped."""
    rows = [
        (datetime(2026, 1, 1, 0, 0), 1.0),
        (datetime(2025, 12, 31, 23, 0), 2.0),
        (datetime(2026, 1, 1, 1, 0), 3.0),
    ]
    series = h.localize_rows(rows, None, -5 * 3600)
    assert [g for _, g in series] == [1.0, 3.0]
    assert series[0][0] == datetime(2026, 1, 1, 5, 0, tzinfo=UTC).timestamp()


def test_timezone_matches() -> None:
    """Only the portal's real time zone lines the export up with UTC readings."""
    reference = _graph_series()
    rows = h.parse_export_csv((FIXTURES / "export_recent.csv").read_text())
    assert h.timezone_matches(rows, reference, NY)
    assert not h.timezone_matches(rows, reference, ZoneInfo("America/Chicago"))
    assert not h.timezone_matches([], reference, NY)


def test_offset_from_local_and_utc() -> None:
    """The portal offset is derived from its local and UTC read times."""
    assert h.offset_from_local_and_utc("2026-11-18 03:57:38", 1794992258) == -18000
    assert h.offset_from_local_and_utc(None, 1.0) is None
    assert h.offset_from_local_and_utc("garbage", 1.0) is None


def test_hourly_statistics_time_weighted() -> None:
    """Hourly means weight each value by how long it was current."""
    base = datetime(2026, 11, 17, 10, 0, tzinfo=UTC).timestamp()
    series = [(base + 57 * 60, 60.0), (base + 3600 + 57 * 60, 70.0)]
    stats = h.hourly_statistics(series, base, base + 3 * 3600)
    # 10:00 hour starts before the first reading: only the covered part counts.
    assert stats[0].mean == pytest.approx(60.0)
    assert stats[1].mean == pytest.approx((60 * 57 + 70 * 3) / 60)
    assert (stats[1].min, stats[1].max) == (60.0, 70.0)
    assert stats[2].mean == pytest.approx(70.0)
    pct = h.hourly_statistics(series, base, base + 3 * 3600, transform=lambda v: v / 2)
    assert pct[2].mean == pytest.approx(35.0)
    assert h.hourly_statistics([], base, base + 3600) == []
    # Hours entirely before the first reading are skipped.
    assert h.hourly_statistics(series, base - 7200, base) == []


def test_detect_refills_real_slow_delivery() -> None:
    """The real 11/17 delivery is found at its true start and still filling."""
    events = h.detect_refills(_graph_series())
    assert len(events) == 1
    event = events[0]
    assert event.start == datetime(2026, 11, 17, 15, 55, 35, tzinfo=UTC)
    assert event.amount == pytest.approx(140.3)
    assert event.in_progress is True


def test_detect_refills_closes_and_ignores_noise() -> None:
    """A refill closes once the level settles; noise never counts."""
    noisy = [(i * 3600.0, 75.0 + (1.1 if i % 2 else 0.0)) for i in range(30)]
    assert h.detect_refills(noisy) == []
    small = [(i * 3600.0, 70.0 + (5.0 if i >= 5 else 0.0)) for i in range(20)]
    assert h.detect_refills(small) == []

    levels = [60.0] * 8 + [100.0, 140.0, 160.0] + [160.0] * 10
    events = h.detect_refills([(i * 3600.0, g) for i, g in enumerate(levels)])
    assert len(events) == 1
    assert events[0].amount == 100.0
    assert events[0].in_progress is False
    assert events[0].peak_ts == 10 * 3600.0


def test_hours_ago() -> None:
    """hours_ago returns a unix timestamp in the past."""
    now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    assert h.hours_ago(now, 2) == datetime(2026, 1, 1, 10, tzinfo=UTC).timestamp()


def test_slow_refill_settles_when_level_levels_off() -> None:
    """Real 11/17 delivery: brief pauses don't end it; it settles at 7 PM 11/19."""
    rows = h.parse_export_csv((FIXTURES / "export_refill_settle.csv").read_text())
    series = h.localize_rows(rows, NY, 0)

    def as_of(local: str) -> h.RefillEvent:
        cutoff = datetime.fromisoformat(local).replace(tzinfo=NY).timestamp()
        return h.detect_refills([p for p in series if p[0] <= cutoff])[-1]

    # The level paused for an hour at 2 AM and noon on 11/19 while still
    # filling; neither ends the refill.
    assert as_of("2026-11-19T02:30").in_progress
    assert as_of("2026-11-19T14:30").in_progress
    # A +2 gallon blip at 6 PM doesn't keep it open once the level is flat.
    settled = as_of("2026-11-19T19:30")
    assert not settled.in_progress
    final = h.detect_refills(series)[-1]
    assert final.start == datetime(2026, 11, 17, 15, 55, 35, tzinfo=UTC)
    assert not final.in_progress
    # Measured to the settled level (276.69), not the 277.58 blip.
    assert final.amount == pytest.approx(215.6)


def test_refill_not_reported_again_as_it_ages_out_of_the_window() -> None:
    """Real data: an old refill's tail is not reported as a new refill.

    As the 8-day window slides past the start of the 11/17 delivery, only the
    tail of the slow climb remains in view; it must not count again.
    """
    lines = (FIXTURES / "refill_window_series.csv").read_text().split()[1:]
    series = [(float(t), float(g)) for t, g in (line.split(",") for line in lines)]

    def detected(local: str) -> list[h.RefillEvent]:
        now = datetime.fromisoformat(local).replace(tzinfo=NY).timestamp()
        return h.detect_refills([p for p in series if now - 8 * 86400 < p[0] <= now])

    start = datetime(2026, 11, 17, 15, 55, 35, tzinfo=UTC)
    for when in ("2026-11-19T20:00", "2026-11-24T12:00"):
        events = detected(when)
        assert [e.start for e in events] == [start]
    # These used to report 186.5, 91.0 and 31.9 gallons "refills".
    for when in ("2026-11-25T12:21", "2026-11-26T00:23", "2026-11-26T12:24"):
        assert detected(when) == []


def test_rise_needs_flat_history_before_it() -> None:
    """A rise at the very start of the data, or after a climb, is not a refill."""
    climbing = [(i * 3600.0, 100.0 + 5 * i) for i in range(10)] + [
        ((10 + i) * 3600.0, 150.0) for i in range(10)
    ]
    assert h.detect_refills(climbing) == []
    flat_then_fill = (
        [(i * 3600.0, 60.0) for i in range(8)]
        + [((8 + i) * 3600.0, 60.0 + 20 * (i + 1)) for i in range(4)]
        + [((12 + i) * 3600.0, 140.0) for i in range(8)]
    )
    events = h.detect_refills(flat_then_fill)
    assert len(events) == 1
    assert events[0].amount == 80.0
