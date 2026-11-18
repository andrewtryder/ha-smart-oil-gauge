"""Pure helpers for Smart Oil Gauge hourly history.

Everything in this module is free of Home Assistant runtime dependencies so
it can be unit tested in isolation. A *series* is a list of ``(ts, gallons)``
tuples, where ``ts`` is a UTC unix timestamp (float) and the list is sorted
ascending by timestamp with no duplicates.
"""

from __future__ import annotations

import bisect
import csv
import io
import logging
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

_LOGGER = logging.getLogger(__name__)

type Point = tuple[float, float]
type Series = list[Point]

# Two readings closer together than this are treated as the same reading.
DUPLICATE_TOLERANCE_S = 60.0
HOUR_S = 3600.0

# Refill detection tuning. Hour-to-hour sensor noise is about +/-1 gallon.
REFILL_MIN_AMOUNT = 15.0
REFILL_START_RISE = 3.0
REFILL_RISE_WINDOW = 3
REFILL_RISE_EPS = 1.5
REFILL_SETTLE_READINGS = 6
REFILL_BASELINE_READINGS = 3


def merge_series(*sources: Iterable[Point]) -> Series:
    """Merge point sources into one sorted series, dropping duplicates.

    When two points fall within ``DUPLICATE_TOLERANCE_S`` of each other the
    one from the later source wins, so fresher data replaces older data.
    """
    order = 0
    keyed: list[tuple[float, int, float]] = []
    for source in sources:
        for ts, gal in source:
            if not (math.isfinite(ts) and math.isfinite(gal)):
                continue
            keyed.append((float(ts), order, float(gal)))
            order += 1
    keyed.sort()
    result: Series = []
    for ts, _, gal in keyed:
        if result and ts - result[-1][0] < DUPLICATE_TOLERANCE_S:
            result[-1] = (result[-1][0], gal)
            continue
        result.append((ts, gal))
    return result


def trim_series(series: Series, keep_after_ts: float) -> Series:
    """Return the points newer than ``keep_after_ts``."""
    idx = bisect.bisect_right([p[0] for p in series], keep_after_ts)
    return series[idx:]


def value_at(series: Sequence[Point], ts: float) -> float | None:
    """Return the step-function value of the series at ``ts``."""
    idx = bisect.bisect_right([p[0] for p in series], ts) - 1
    if idx < 0:
        return None
    return series[idx][1]


def parse_graph_points(payload: object) -> Series:
    """Extract hourly points from a ``get_graph_data`` response.

    The portal keys ``datasets`` by sensor registration id (for example
    ``{"71796": {"day": ..., "week": ...}}``); the web app renames that to
    ``main`` before charting. Every registration found is merged, and the
    day and week sets are merged within each.
    """
    if not isinstance(payload, dict):
        return []
    datasets = payload.get("datasets")
    if not isinstance(datasets, dict):
        return []
    sources: list[list[Point]] = []
    for registration in datasets.values():
        if not isinstance(registration, dict):
            continue
        for period in ("week", "day"):
            block = registration.get(period)
            if isinstance(block, dict):
                sources.append(_parse_points(block.get("points")))
    return merge_series(*sources)


def _parse_points(points: object) -> list[Point]:
    """Parse a list of ``{"ts": ..., "gallons": ...}`` points."""
    if not isinstance(points, list):
        return []
    parsed: list[Point] = []
    for item in points:
        if not isinstance(item, dict):
            continue
        try:
            parsed.append((float(item["ts"]), float(item["gallons"])))
        except KeyError, TypeError, ValueError:
            continue
    return parsed


def parse_export_csv(text: str) -> list[tuple[datetime, float]]:
    """Parse the portal's CSV export into naive local datetimes and gallons.

    Rows keep their original order, which matters for resolving the repeated
    hour when clocks fall back.
    """
    rows: list[tuple[datetime, float]] = []
    reader = csv.reader(io.StringIO(text.strip()))
    header = next(reader, None)
    if not header or [h.strip().lower() for h in header[:2]] != ["time", "gallons"]:
        raise ValueError("Export does not look like a Smart Oil Gauge CSV")
    for row in reader:
        if len(row) < 2:
            continue
        try:
            local = datetime.strptime(row[0].strip(), "%Y-%m-%d %H:%M:%S")
            gal = float(row[1])
        except ValueError:
            continue
        if math.isfinite(gal):
            rows.append((local, gal))
    return rows


def localize_rows(
    rows: Sequence[tuple[datetime, float]], tz: ZoneInfo | None, fixed_offset_s: float
) -> Series:
    """Convert naive local rows to a UTC series.

    With a real time zone, daylight-saving folds are resolved by keeping the
    series monotonic: when a wall-clock time repeats, the second occurrence is
    taken from the later (``fold=1``) side. Without a time zone a fixed UTC
    offset is applied.
    """
    series: Series = []
    last_ts = -math.inf
    for local, gal in rows:
        if tz is None:
            ts = local.replace(tzinfo=UTC).timestamp() - fixed_offset_s
        else:
            first = local.replace(tzinfo=tz, fold=0).timestamp()
            second = local.replace(tzinfo=tz, fold=1).timestamp()
            ts = first
            if second != first:
                # Ambiguous wall-clock time (clocks fell back). Readings are
                # about an hour apart, so pick the candidate that keeps that
                # cadence after the previous reading.
                candidates = [c for c in (first, second) if c > last_ts]
                if candidates:
                    ts = min(candidates, key=lambda c: abs(c - last_ts - HOUR_S))
        if ts <= last_ts:
            _LOGGER.debug("Dropping out-of-order export row at %s", local)
            continue
        series.append((ts, gal))
        last_ts = ts
    return series


def timezone_matches(
    rows: Sequence[tuple[datetime, float]],
    reference: Sequence[Point],
    tz: ZoneInfo,
) -> bool:
    """Check that ``tz`` maps export rows onto known UTC readings.

    The reference series (from ``get_graph_data``) carries true UTC
    timestamps, so an export row and a reference point with the same reading
    must land within a couple of minutes of each other.
    """
    if not rows or not reference:
        return False
    converted = localize_rows(rows, tz, 0)
    ref_ts = [p[0] for p in reference]
    matches = 0
    checked = 0
    for ts, gal in converted:
        if ts < ref_ts[0] - HOUR_S or ts > ref_ts[-1] + HOUR_S:
            continue
        checked += 1
        idx = bisect.bisect_left(ref_ts, ts)
        for j in (idx - 1, idx):
            if 0 <= j < len(reference):
                if abs(reference[j][0] - ts) <= 120 and (
                    abs(reference[j][1] - gal) < 0.05
                ):
                    matches += 1
                    break
    return checked >= 3 and matches / checked >= 0.9


def offset_from_local_and_utc(local_text: str | None, utc_ts: float) -> float | None:
    """Derive the portal's UTC offset from a local and UTC timestamp pair."""
    if not local_text:
        return None
    try:
        local = datetime.strptime(local_text.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    diff = local.replace(tzinfo=UTC).timestamp() - utc_ts
    # Offsets are whole quarter hours.
    return round(diff / 900) * 900


@dataclass(slots=True)
class HourStat:
    """One hour of statistics."""

    start: datetime
    mean: float
    min: float
    max: float


def hourly_statistics(
    series: Sequence[Point],
    start_ts: float,
    end_ts: float,
    *,
    transform: Callable[[float], float] | None = None,
) -> list[HourStat]:
    """Compute time-weighted hourly statistics for a step-function series.

    Hours are aligned to the top of the UTC hour (which is also the top of
    the local hour for whole-hour offsets). Hours from ``floor(start_ts)`` up
    to, but not including, the hour containing ``end_ts`` are produced.
    Hours before the first reading are skipped. The value after the last
    reading is held constant, which mirrors how Home Assistant itself treats
    a sensor that has not changed.
    """
    if not series:
        return []
    fn = transform or (lambda v: v)
    timestamps = [p[0] for p in series]
    hour = math.floor(start_ts / HOUR_S) * HOUR_S
    stop = math.floor(end_ts / HOUR_S) * HOUR_S
    stats: list[HourStat] = []
    while hour < stop:
        hour_end = hour + HOUR_S
        idx = bisect.bisect_right(timestamps, hour) - 1
        if idx < 0:
            # No reading yet at the start of this hour; start at first reading
            # if it falls inside this hour, otherwise skip the hour.
            if timestamps[0] >= hour_end:
                hour = hour_end
                continue
            idx = 0
            cursor = timestamps[0]
        else:
            cursor = hour
        weighted = 0.0
        values: list[float] = []
        covered = 0.0
        j = idx
        while cursor < hour_end:
            value = fn(series[j][1])
            nxt = timestamps[j + 1] if j + 1 < len(series) else math.inf
            seg_end = min(nxt, hour_end)
            weighted += value * (seg_end - cursor)
            covered += seg_end - cursor
            values.append(value)
            cursor = seg_end
            j += 1
        if covered > 0:
            stats.append(
                HourStat(
                    start=datetime.fromtimestamp(hour, UTC),
                    mean=weighted / covered,
                    min=min(values),
                    max=max(values),
                )
            )
        hour = hour_end
    return stats


@dataclass(slots=True)
class RefillEvent:
    """A detected refill."""

    start_ts: float
    baseline: float
    peak: float
    peak_ts: float
    in_progress: bool

    @property
    def amount(self) -> float:
        """Gallons added."""
        return round(self.peak - self.baseline, 1)

    @property
    def start(self) -> datetime:
        """Start time as an aware UTC datetime."""
        return datetime.fromtimestamp(self.start_ts, UTC)


def detect_refills(
    series: Sequence[Point],
    *,
    min_amount: float = REFILL_MIN_AMOUNT,
) -> list[RefillEvent]:
    """Detect refills, including slow ones that climb over many hours.

    A candidate opens when the level rises by more than ``REFILL_START_RISE``
    over one reading. It stays open while the level keeps climbing (more than
    ``REFILL_RISE_EPS`` over the last ``REFILL_RISE_WINDOW`` readings) and
    closes after ``REFILL_SETTLE_READINGS`` readings without a climb.
    Candidates that never add ``min_amount`` gallons are discarded as noise.
    """
    events: list[RefillEvent] = []
    gal = [p[1] for p in series]
    ts = [p[0] for p in series]
    k = 1
    n = len(series)
    while k < n:
        if gal[k] - gal[k - 1] <= REFILL_START_RISE:
            k += 1
            continue
        base_slice = gal[max(0, k - REFILL_BASELINE_READINGS) : k]
        baseline = sorted(base_slice)[len(base_slice) // 2]
        peak, peak_ts = gal[k], ts[k]
        quiet = 0
        j = k + 1
        while j < n and quiet < REFILL_SETTLE_READINGS:
            if gal[j] > peak:
                peak, peak_ts = gal[j], ts[j]
            back = gal[max(k - 1, j - REFILL_RISE_WINDOW)]
            if gal[j] - back > REFILL_RISE_EPS:
                quiet = 0
            else:
                quiet += 1
            j += 1
        in_progress = quiet < REFILL_SETTLE_READINGS
        if peak - baseline >= min_amount:
            events.append(
                RefillEvent(
                    start_ts=ts[k],
                    baseline=baseline,
                    peak=peak,
                    peak_ts=peak_ts,
                    in_progress=in_progress,
                )
            )
            k = j
        else:
            k += 1
    return events


def hours_ago(now: datetime, hours: float) -> float:
    """Return the unix timestamp ``hours`` before ``now``."""
    return (now - timedelta(hours=hours)).timestamp()
