"""Write backfilled readings into the Home Assistant recorder.

Two things are written:

* Long-term statistics, through the recorder's supported
  ``async_import_statistics`` API. This works on every database backend.
* Raw state history rows. Home Assistant has no public API for writing
  past states, so this runs as a task inside the recorder's own thread and
  session, using the recorder's own SQLAlchemy models. That keeps the SQL
  dialect (SQLite, MariaDB/MySQL, PostgreSQL) in the recorder's hands.

Existing rows inside a backfilled range are corrected rather than deleted,
so foreign keys between state rows (``old_state_id``) stay valid on
databases that enforce them.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .history import Point, hourly_statistics, value_at

if TYPE_CHECKING:
    from homeassistant.components.recorder import Recorder

_LOGGER = logging.getLogger(__name__)

# Rows within this many seconds of a reading are treated as that reading.
MATCH_TOLERANCE_S = 2.0
# Only import statistics for hours that ended at least this long ago, so the
# recorder has already compiled them and will not overwrite our values.
STATS_SETTLE_S = 15 * 60
NON_NUMERIC_STATES = ("unknown", "unavailable", "")


class RecorderUnavailable(Exception):
    """The recorder is not running or not ready for writes."""


@dataclass(slots=True)
class EntityBackfill:
    """Readings to write for one entity."""

    entity_id: str
    series: Sequence[Point]
    start_ts: float
    end_ts: float
    to_state: Callable[[float], str]
    unit: str | None = None
    transform: Callable[[float], float] | None = None
    write_states: bool = True
    states_not_before_ts: float | None = None


@dataclass(slots=True)
class BackfillResult:
    """Summary of a states backfill."""

    inserted: int = 0
    corrected: int = 0
    skipped_entities: list[str] = field(default_factory=list)


def recorder_ready(hass: HomeAssistant) -> Recorder:
    """Return the recorder instance if it can accept backfill writes."""
    if "recorder" not in hass.config.components:
        raise RecorderUnavailable("Recorder integration is not loaded")
    from homeassistant.components.recorder import get_instance  # noqa: PLC0415
    from homeassistant.components.recorder.db_schema import (  # noqa: PLC0415
        SCHEMA_VERSION,
    )

    instance = get_instance(hass)
    if getattr(instance, "migration_in_progress", False):
        raise RecorderUnavailable("Recorder database migration is in progress")
    schema = getattr(instance, "schema_version", None)
    if schema != SCHEMA_VERSION:
        raise RecorderUnavailable(
            f"Recorder schema {schema} does not match expected {SCHEMA_VERSION}"
        )
    return instance


def _states_task_class() -> type:
    """Build the recorder task class lazily so imports stay optional."""
    from homeassistant.components.recorder.tasks import (  # noqa: PLC0415
        RecorderTask,
    )

    @dataclass(slots=True)
    class BackfillStatesTask(RecorderTask):
        """Recorder task that inserts and corrects state rows."""

        jobs: list[EntityBackfill]
        loop: asyncio.AbstractEventLoop
        future: asyncio.Future[BackfillResult]

        def run(self, instance: Recorder) -> None:
            try:
                result = _write_states(instance, self.jobs)
            except Exception as err:  # noqa: BLE001
                self.loop.call_soon_threadsafe(_set_exception, self.future, err)
                return
            self.loop.call_soon_threadsafe(_set_result, self.future, result)

    return BackfillStatesTask


def _set_result(future: asyncio.Future[Any], value: Any) -> None:
    if not future.done():
        future.set_result(value)


def _set_exception(future: asyncio.Future[Any], err: BaseException) -> None:
    if not future.done():
        future.set_exception(err)


def _write_states(instance: Recorder, jobs: list[EntityBackfill]) -> BackfillResult:
    """Insert missing readings and correct stale rows. Runs in the recorder."""
    from homeassistant.helpers.recorder import session_scope  # noqa: PLC0415

    result = BackfillResult()
    with session_scope(session=instance.get_session()) as session:
        for job in jobs:
            _write_job(instance, session, job, result)
    return result


def _write_job(
    instance: Recorder, session: Any, job: EntityBackfill, result: BackfillResult
) -> None:
    """Insert and correct state rows for one entity."""
    from homeassistant.components.recorder.db_schema import States  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    lo = job.start_ts
    if job.states_not_before_ts is not None:
        lo = max(lo, job.states_not_before_ts)
    hi = job.end_ts
    if hi < lo:
        return
    metadata_id = instance.states_meta_manager.get(job.entity_id, session, True)
    if metadata_id is None:
        result.skipped_entities.append(job.entity_id)
        return

    latest = session.execute(
        select(States.attributes_id)
        .where(States.metadata_id == metadata_id)
        .where(States.attributes_id.is_not(None))
        .order_by(States.last_updated_ts.desc())
        .limit(1)
    ).scalar_one_or_none()

    existing = session.scalars(
        select(States)
        .where(States.metadata_id == metadata_id)
        .where(States.last_updated_ts >= lo - MATCH_TOLERANCE_S)
        .where(States.last_updated_ts <= hi + MATCH_TOLERANCE_S)
    ).all()
    existing_ts = sorted(row.last_updated_ts or 0.0 for row in existing)

    result.corrected += _correct_rows(existing, job)

    # Insert readings that have no row yet.
    for ts, gal in job.series:
        if ts < lo or ts > hi:
            continue
        if _has_row_near(existing_ts, ts):
            continue
        session.add(
            States(
                metadata_id=metadata_id,
                state=job.to_state(gal),
                attributes_id=latest,
                last_updated_ts=ts,
                last_changed_ts=None,
                last_reported_ts=None,
                origin_idx=0,
            )
        )
        result.inserted += 1


def _correct_rows(rows: Sequence[Any], job: EntityBackfill) -> int:
    """Set rows that hold a stale value to the true reading at their time."""
    corrected = 0
    for row in rows:
        if row.state in NON_NUMERIC_STATES or row.last_updated_ts is None:
            continue
        true_value = value_at(job.series, row.last_updated_ts + MATCH_TOLERANCE_S)
        if true_value is None:
            continue
        wanted = job.to_state(true_value)
        if row.state != wanted:
            row.state = wanted
            # The value changed at this row, so it counts as a state change
            # (NULL means "same as last_updated") for history graphs.
            row.last_changed_ts = None
            corrected += 1
    return corrected


def _has_row_near(sorted_ts: list[float], ts: float) -> bool:
    import bisect  # noqa: PLC0415

    idx = bisect.bisect_left(sorted_ts, ts - MATCH_TOLERANCE_S)
    return idx < len(sorted_ts) and sorted_ts[idx] <= ts + MATCH_TOLERANCE_S


async def async_backfill_states(
    hass: HomeAssistant, jobs: list[EntityBackfill]
) -> BackfillResult:
    """Queue a states backfill in the recorder and wait for it to finish."""
    instance = recorder_ready(hass)
    jobs = [job for job in jobs if job.write_states]
    if not jobs:
        return BackfillResult()
    loop = hass.loop
    future: asyncio.Future[BackfillResult] = loop.create_future()
    task_cls = _states_task_class()
    instance.queue_task(task_cls(jobs=jobs, loop=loop, future=future))
    return await future


async def async_import_hourly_statistics(
    hass: HomeAssistant, job: EntityBackfill
) -> int:
    """Import hourly mean/min/max statistics for an entity's own statistic id.

    Returns the number of hours imported.
    """
    recorder_ready(hass)
    from homeassistant.components.recorder.models import (  # noqa: PLC0415
        StatisticMeanType,
    )
    from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
        STATISTIC_UNIT_TO_UNIT_CONVERTER,
        async_import_statistics,
    )

    settle_end = dt_util.utcnow().timestamp() - STATS_SETTLE_S
    stats = hourly_statistics(
        job.series,
        job.start_ts,
        settle_end,
        transform=job.transform,
    )
    if not stats:
        return 0

    converter = STATISTIC_UNIT_TO_UNIT_CONVERTER.get(job.unit)
    metadata = {
        "mean_type": StatisticMeanType.ARITHMETIC,
        "has_sum": False,
        "name": None,
        "source": "recorder",
        "statistic_id": job.entity_id,
        "unit_class": converter.UNIT_CLASS if converter else None,
        "unit_of_measurement": job.unit,
    }
    async_import_statistics(
        hass,
        metadata,  # type: ignore[arg-type]
        [{"start": s.start, "mean": s.mean, "min": s.min, "max": s.max} for s in stats],
    )
    return len(stats)
