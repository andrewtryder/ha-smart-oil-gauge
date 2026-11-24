"""Work out when each gauge will next upload, and when to poll the portal.

The gauge uploads its hourly readings on an interval set on the portal
(1-24 hours). It downloads its settings far less often than it uploads (the
portal warns that a change "can take up to a few days"), so we cannot
predict when a changed interval takes effect. Instead we watch for it:

* ``configured_h``: what the portal says now.
* ``effective_h``: what the gauge is actually doing, confirmed by the gaps
  between its uploads.

While the two differ, a change is *pending* and the next upload may come
after either interval, so both are treated as possible.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

# Gauges upload a little after the exact interval (about a minute was seen).
GRACE_S = 5 * 60
# If an expected upload has not arrived, poll again at these offsets after it
# was due. Only when no other upload is expected later, keep trying hourly.
RETRY_OFFSETS_S = (15 * 60, 45 * 60, 105 * 60)
RETRY_EVERY_S = 60 * 60
# Bounds on the time between polls.
MIN_DELAY_S = 60
# Longest wait: just over the gauge's longest upload interval (24 h). Status
# data only changes when the gauge uploads, so there is nothing to refresh
# in between; this is only a safety net.
MAX_DELAY_S = 25 * 3600
# A gap counts as a whole number of hours if it is within this of one.
SPACING_TOLERANCE_S = 20 * 60
KEEP_UPLOADS = 6


@dataclass(slots=True)
class TankSchedule:
    """Upload schedule state for one gauge."""

    configured_h: int | None = None
    effective_h: int | None = None
    num_tanks: int | None = None
    upload_times: list[float] = field(default_factory=list)
    pending_since: float | None = None
    confirmed: bool = False
    config_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "configured_h": self.configured_h,
            "effective_h": self.effective_h,
            "num_tanks": self.num_tanks,
            "upload_times": list(self.upload_times),
            "pending_since": self.pending_since,
            "confirmed": self.confirmed,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> TankSchedule:
        """Load from storage, ignoring anything malformed."""
        if not isinstance(raw, dict):
            return cls()
        times = raw.get("upload_times")
        since = raw.get("pending_since")
        return cls(
            configured_h=_hours(raw.get("configured_h")),
            effective_h=_hours(raw.get("effective_h")),
            num_tanks=_hours(raw.get("num_tanks"), maximum=10),
            upload_times=sorted(
                float(t) for t in times if isinstance(t, int | float) and t > 0
            )[-KEEP_UPLOADS:]
            if isinstance(times, list)
            else [],
            pending_since=float(since) if isinstance(since, int | float) else None,
            confirmed=raw.get("confirmed") is True,
        )

    @property
    def pending(self) -> bool:
        """True while the portal setting differs from what the gauge does."""
        return (
            self.configured_h is not None
            and self.effective_h is not None
            and self.configured_h != self.effective_h
        )

    def update_configured(
        self, hours: int | None, num_tanks: int | None, now: float
    ) -> None:
        """Record the interval the portal shows now."""
        if num_tanks is not None:
            self.num_tanks = num_tanks
        if hours is None:
            return
        if self.effective_h is None:
            # First time we see this gauge: assume it already uses the setting
            # until its upload gaps say otherwise.
            self.effective_h = hours
        if hours != self.configured_h:
            self.configured_h = hours
            self.pending_since = now if self.pending else None
        elif not self.pending:
            self.pending_since = None

    def record_upload(self, last_read: float) -> None:
        """Record a new upload and learn the interval from the gap before it."""
        if self.upload_times and last_read <= self.upload_times[-1] + 1:
            return
        previous = self.upload_times[-1] if self.upload_times else None
        self.upload_times.append(last_read)
        self.upload_times = self.upload_times[-KEEP_UPLOADS:]
        if previous is None:
            return
        gap_h = _whole_hours(last_read - previous)
        if gap_h is None:
            return
        if gap_h == self.configured_h:
            # The gauge is following the portal setting.
            self.effective_h = gap_h
            self.confirmed = True
            self.pending_since = None
            return
        if self.effective_h and gap_h % self.effective_h == 0:
            # One interval, or a missed upload or two: nothing changed.
            self.confirmed = self.confirmed or gap_h == self.effective_h
            return
        measured = self.measured_h()
        if measured is not None and _whole_hours(measured * 3600) == gap_h:
            # Two consistent gaps that match neither setting: trust them.
            self.effective_h = gap_h
            self.confirmed = True

    def measured_h(self) -> float | None:
        """Interval implied by the last uploads, if their gaps agree."""
        times = self.upload_times
        if len(times) < 3:
            return None
        spacings = [b - a for a, b in zip(times[-3:], times[-2:], strict=False)]
        if abs(spacings[0] - spacings[1]) > SPACING_TOLERANCE_S:
            return None
        return statistics.mean(spacings) / 3600

    def interval(self) -> tuple[float | None, str]:
        """The interval the gauge is using, and how we know it."""
        if self.effective_h is None:
            measured = self.measured_h()
            return (measured, "observed") if measured is not None else (None, "unknown")
        return float(self.effective_h), "observed" if self.confirmed else "portal"

    def candidates(self, last_read: float | None) -> list[float]:
        """Every time the next upload could come, earliest first."""
        if last_read is None:
            return []
        hours = {self.effective_h, self.configured_h} - {None}
        if not hours:
            measured = self.measured_h()
            if measured is None:
                return []
            return [last_read + measured * 3600]
        return sorted(last_read + h * 3600 for h in hours)

    def next_expected(self, last_read: float | None, now: float) -> float | None:
        """The earliest possible upload that has not yet been missed."""
        future = [c for c in self.candidates(last_read) if c + GRACE_S > now]
        return future[0] if future else None

    def overdue(self, last_read: float | None, now: float) -> bool:
        """True when every expected upload time has passed."""
        found = self.candidates(last_read)
        return bool(found) and all(c + GRACE_S <= now for c in found)


def next_poll_delay(
    now: float, expected: list[float], fallback_s: float
) -> tuple[float, float]:
    """Return ``(delay_s, poll_at)`` for the next poll.

    Polls shortly after each possible upload time. Missed ones get a few
    retries; hourly retries only start once no upload is expected later.
    Without any expectation, uses ``fallback_s``. The delay is kept between
    ``MIN_DELAY_S`` and ``MAX_DELAY_S``.
    """
    dues = [exp + GRACE_S for exp in expected]
    upcoming = [d for d in dues if d > now]
    attempts = list(upcoming)
    for due in dues:
        if due <= now:
            attempts.extend(
                due + o for o in RETRY_OFFSETS_S if due + o > now + MIN_DELAY_S
            )
    if dues and not upcoming:
        attempts.append(_hourly_after(now, max(dues)))
    delay = min(attempts) - now if attempts else fallback_s
    delay = max(MIN_DELAY_S, min(MAX_DELAY_S, delay))
    return delay, now + delay


def _hourly_after(now: float, due: float) -> float:
    """The next hourly retry after the last fixed retry for ``due``."""
    last = due + RETRY_OFFSETS_S[-1]
    if last > now + MIN_DELAY_S:
        return last
    steps = int((now + MIN_DELAY_S - last) // RETRY_EVERY_S) + 1
    return last + steps * RETRY_EVERY_S


def _whole_hours(seconds: float) -> int | None:
    """Round a gap to whole hours, or None if it is not close to one."""
    hours = round(seconds / 3600)
    if hours < 1 or abs(seconds - hours * 3600) > SPACING_TOLERANCE_S:
        return None
    return hours


def _hours(value: Any, maximum: int = 24) -> int | None:
    try:
        hours = int(value)
    except TypeError, ValueError:
        return None
    return hours if 1 <= hours <= maximum else None
