"""DataUpdateCoordinator for Smart Oil Gauge."""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import (
    CannotConnect,
    InvalidAuth,
    SmartOilGaugeClient,
    SmartOilGaugeException,
)
from .const import DOMAIN
from .history import (
    Series,
    detect_refills,
    localize_rows,
    merge_series,
    offset_from_local_and_utc,
    parse_export_csv,
    parse_graph_points,
    timezone_matches,
    trim_series,
)
from .recorder_writer import (
    EntityBackfill,
    RecorderUnavailable,
    async_backfill_states,
    async_import_hourly_statistics,
)
from .util import parse_finite_float

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1

# How much hourly history to keep in memory and storage for refill detection.
SERIES_KEEP = timedelta(days=8)
# The portal export accepts at most two years per request.
EXPORT_CHUNK_DAYS = 365
# Delay before the first history import so entity states exist in the recorder.
INITIAL_IMPORT_DELAY_S = 60
REFILL_SAME_EVENT_S = 2 * 3600


def parse_last_read(tank: dict[str, Any]) -> float | None:
    """Return the tank's last sensor upload time as a unix timestamp."""
    value = parse_finite_float(tank.get("last_read"))
    if value is None or value <= 0:
        return None
    return value


def format_state(value: float) -> str:
    """Format a number the same way the sensor entity reports it."""
    return str(float(value))


@dataclass
class SmartOilGaugeData:
    """Data stored in ConfigEntry.runtime_data."""

    client: SmartOilGaugeClient
    coordinator: SmartOilGaugeDataUpdateCoordinator


type SmartOilGaugeConfigEntry = ConfigEntry[SmartOilGaugeData]


class SmartOilGaugeDataUpdateCoordinator(
    DataUpdateCoordinator[dict[str, dict[str, Any]]]
):
    """Class to manage fetching Smart Oil Gauge data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SmartOilGaugeClient,
        update_interval_hours: int,
        entry_id: str = "default",
        *,
        backfill_states: bool = True,
        import_history: bool = True,
    ) -> None:
        """Initialize."""
        self.client = client
        self.entry_id = entry_id
        self.backfill_states = backfill_states
        self.import_history = import_history
        self.series: dict[str, Series] = {}
        self.last_read: dict[str, float] = {}
        self.backfilled_until: dict[str, float] = {}
        self.history_imported: dict[str, bool] = {}
        self.backfill_status: dict[str, Any] = {}
        self._backfill_lock = asyncio.Lock()
        self.issue_id = f"api_breakage_{entry_id}"
        self.last_successful_update: datetime | None = None
        self._previous_levels: dict[str, dict[str, float]] = {}
        self.last_refills: dict[str, dict[str, Any]] = {}
        self._store = Store(hass, STORAGE_VERSION, f"smart_oil_gauge_{entry_id}")
        self._storage_loaded = False

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=update_interval_hours),
        )

    def _parse_stored_previous_levels(
        self, stored: dict[str, Any]
    ) -> dict[str, dict[str, float]]:
        """Parse and validate stored previous levels."""
        raw_prev = stored.get("previous_levels")
        if not isinstance(raw_prev, dict):
            return {}

        clean: dict[str, dict[str, float]] = {}
        for tank_id, modes in raw_prev.items():
            if not isinstance(modes, dict) or not isinstance(tank_id, str):
                continue
            clean_modes: dict[str, float] = {}
            for mode_key, level_val in modes.items():
                parsed_lvl = parse_finite_float(level_val)
                if parsed_lvl is not None:
                    clean_modes[mode_key] = parsed_lvl
            if clean_modes:
                clean[tank_id] = clean_modes
        return clean

    def _parse_stored_last_refills(
        self, stored: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        """Parse and validate stored last refills."""
        raw_refills = stored.get("last_refills")
        if not isinstance(raw_refills, dict):
            return {}

        clean: dict[str, dict[str, Any]] = {}
        for tank_id, refill in raw_refills.items():
            if not isinstance(refill, dict) or not isinstance(tank_id, str):
                continue
            amount = parse_finite_float(refill.get("amount"))
            if amount is None or amount < 0:
                continue
            ts_raw = refill.get("timestamp")
            ts: datetime | None = None
            if isinstance(ts_raw, str):
                try:
                    ts = dt_util.parse_datetime(ts_raw)
                except ValueError:
                    continue
            if ts is None:
                continue
            ts = dt_util.as_utc(ts)
            clean[tank_id] = {
                "amount": amount,
                "timestamp": ts,
                "in_progress": refill.get("in_progress") is True,
            }
        return clean

    async def _async_load_storage(self) -> None:
        """Load stored refill state and previous levels safely."""
        if self._storage_loaded:
            return

        try:
            stored = await self._store.async_load()
            if isinstance(stored, dict):
                prev_levels = self._parse_stored_previous_levels(stored)
                refills = self._parse_stored_last_refills(stored)
                self._previous_levels = prev_levels
                self.last_refills = refills
                self._load_history_state(stored)
            self._storage_loaded = True
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.warning("Could not load persistent storage for refills: %s", ex)

    async def _async_save_storage(self) -> None:
        """Save refill state and previous levels to persistent storage."""
        if not self._storage_loaded:
            _LOGGER.debug("Skipping storage save because storage is not loaded")
            return

        try:
            serialized_refills = {}
            for tank_id, refill in self.last_refills.items():
                ts = refill.get("timestamp")
                serialized_refills[tank_id] = {
                    "amount": refill.get("amount"),
                    "timestamp": ts.isoformat() if isinstance(ts, datetime) else None,
                    "in_progress": bool(refill.get("in_progress", False)),
                }
            await self._store.async_save(
                {
                    "previous_levels": self._previous_levels,
                    "last_refills": serialized_refills,
                    "series": {k: [list(p) for p in v] for k, v in self.series.items()},
                    "last_read": self.last_read,
                    "backfilled_until": self.backfilled_until,
                    "history_imported": self.history_imported,
                }
            )
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.warning("Could not save persistent storage for refills: %s", ex)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Update data via client."""
        await self._async_load_storage()
        try:
            data = await self.client.async_get_tanks()

            tanks_dict: dict[str, dict[str, Any]] = {}
            for tank in data:
                raw_id = tank.get("tank_id")
                if raw_id is None:
                    continue
                tank_id = str(raw_id).strip()
                if not tank_id:
                    continue
                tanks_dict[tank_id] = tank
                last_read = parse_last_read(tank)
                if last_read is None:
                    # Portal did not send an upload time: fall back to
                    # comparing successive snapshots.
                    self._check_refill(tank_id, tank)
                else:
                    await self._async_process_reading(tank_id, tank, last_read)

            # Validated tanks_dict first before updating timestamp & clearing repairs
            self.last_successful_update = dt_util.utcnow()
            async_delete_issue(self.hass, DOMAIN, self.issue_id)
            await self._async_save_storage()

            return tanks_dict
        except CannotConnect as err:
            if "not found" in str(err).lower() or "invalid json" in str(err).lower():
                self._raise_api_breakage_issue()
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(f"Authentication error: {err}") from err
        except SmartOilGaugeException as err:
            self._raise_api_breakage_issue()
            raise UpdateFailed(f"Error fetching data: {err}") from err

    def _check_refill(self, tank_id: str, tank: dict[str, Any]) -> None:
        """Detect upward level changes indicating a refill."""
        source = "sensor_gallons"
        gal_str = tank.get("sensor_gallons")
        if gal_str is None:
            source = "model_gallons"
            gal_str = tank.get("model_gallons")

        if gal_str is None:
            return

        current_level = parse_finite_float(gal_str)
        if current_level is None:
            return

        if tank_id not in self._previous_levels:
            self._previous_levels[tank_id] = {}

        tank_levels = self._previous_levels[tank_id]
        if source in tank_levels:
            prev_level = tank_levels[source]
            if prev_level is not None:
                diff = current_level - prev_level
                if math.isfinite(diff) and diff >= 15.0:
                    _LOGGER.info(
                        "Refill detected for tank %s: %.1f gallons added", tank_id, diff
                    )
                    self.last_refills[tank_id] = {
                        "amount": round(diff, 1),
                        "timestamp": dt_util.utcnow(),
                    }

        tank_levels[source] = current_level

    def _load_history_state(self, stored: dict[str, Any]) -> None:
        """Load hourly series and backfill progress from storage."""
        raw_series = stored.get("series")
        if isinstance(raw_series, dict):
            for tank_id, points in raw_series.items():
                self.series[str(tank_id)] = _parse_stored_series(points)
        for key, target in (
            ("last_read", self.last_read),
            ("backfilled_until", self.backfilled_until),
        ):
            raw = stored.get(key)
            if isinstance(raw, dict):
                for tank_id, value in raw.items():
                    parsed = parse_finite_float(value)
                    if parsed is not None:
                        target[str(tank_id)] = parsed
        raw_imported = stored.get("history_imported")
        if isinstance(raw_imported, dict):
            self.history_imported = {str(k): v is True for k, v in raw_imported.items()}

    async def _async_process_reading(
        self, tank_id: str, tank: dict[str, Any], last_read: float
    ) -> None:
        """Merge new hourly readings and schedule the history backfill."""
        previous = self.last_read.get(tank_id)
        if previous is not None and last_read <= previous + 1:
            # No new upload. Finish any backfill that could not run before,
            # for example because the entities did not exist yet.
            series = self.series.get(tank_id)
            if series and self.backfilled_until.get(tank_id, 0) < last_read:
                self._schedule(
                    self._async_backfill_tank(tank_id, series, last_read),
                    f"smart_oil_gauge backfill {tank_id}",
                )
            return

        points: Series = []
        data_servers = tank.get("data_servers")
        if data_servers:
            try:
                payload = await self.client.async_get_graph_data(
                    tank_id, str(data_servers)
                )
                points = parse_graph_points(payload)
            except SmartOilGaugeException as err:
                _LOGGER.warning(
                    "Could not fetch hourly data for tank %s, keeping only the "
                    "latest reading: %s",
                    tank_id,
                    err,
                )

        snapshot: Series = []
        gallons = parse_finite_float(tank.get("sensor_gallons"))
        if gallons is not None:
            snapshot.append((last_read, gallons))

        series = merge_series(self.series.get(tank_id, []), points, snapshot)
        series = trim_series(series, (dt_util.utcnow() - SERIES_KEEP).timestamp())
        self.series[tank_id] = series
        self.last_read[tank_id] = last_read
        self._update_refill_from_series(tank_id, series)

        if series:
            self._schedule(
                self._async_backfill_tank(tank_id, series, last_read),
                f"smart_oil_gauge backfill {tank_id}",
            )

    def _schedule(self, coro: Any, name: str) -> None:
        """Run a coroutine in the background, tied to the config entry."""
        if self.config_entry is not None:
            self.config_entry.async_create_background_task(self.hass, coro, name)
        else:
            self.hass.async_create_background_task(coro, name)

    def _update_refill_from_series(self, tank_id: str, series: Series) -> None:
        """Update the last refill from the newest refill event in a series."""
        events = detect_refills(series)
        if not events:
            return
        event = events[-1]
        current = self.last_refills.get(tank_id)
        if current is not None:
            current_ts = current.get("timestamp")
            if isinstance(current_ts, datetime) and (
                event.start.timestamp() < current_ts.timestamp() - REFILL_SAME_EVENT_S
            ):
                # An older event than the one already known.
                return
        self.last_refills[tank_id] = {
            "amount": event.amount,
            "timestamp": event.start,
            "in_progress": event.in_progress,
        }

    def _entity_ids(self, tank_id: str) -> dict[str, str]:
        """Return the level and percentage entity ids for a tank."""
        registry = er.async_get(self.hass)
        result: dict[str, str] = {}
        for key in ("oil_level", "oil_percentage"):
            entity_id = registry.async_get_entity_id(
                "sensor", DOMAIN, f"{tank_id}_{key}"
            )
            if entity_id:
                result[key] = entity_id
        return result

    def _build_jobs(
        self,
        tank_id: str,
        series: Series,
        start_ts: float,
        end_ts: float,
    ) -> list[EntityBackfill]:
        """Build backfill jobs for the tank's level and percentage sensors.

        State rows are only written inside the recorder's own keep window
        (``purge_keep_days``); older hours go to long-term statistics only.
        """
        states_not_before_ts = self._states_cutoff_ts()
        tank = (self.data or {}).get(tank_id, {})
        ids = self._entity_ids(tank_id)
        jobs: list[EntityBackfill] = []

        level_id = ids.get("oil_level")
        if level_id and self._entity_unit(level_id) in ("gal", None):
            jobs.append(
                EntityBackfill(
                    entity_id=level_id,
                    series=series,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    to_state=format_state,
                    unit="gal",
                    write_states=self.backfill_states,
                    states_not_before_ts=states_not_before_ts,
                )
            )

        nominal = parse_finite_float(tank.get("nominal"))
        pct_id = ids.get("oil_percentage")
        if (
            pct_id
            and nominal
            and nominal > 0
            and (self._entity_unit(pct_id) in ("%", None))
        ):

            def to_pct(gal: float, nominal: float = nominal) -> float:
                return round(gal / nominal * 100.0, 1)

            jobs.append(
                EntityBackfill(
                    entity_id=pct_id,
                    series=series,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    to_state=lambda gal: format_state(to_pct(gal)),
                    unit="%",
                    transform=to_pct,
                    write_states=self.backfill_states,
                    states_not_before_ts=states_not_before_ts,
                )
            )
        return jobs

    def _states_cutoff_ts(self) -> float:
        """Oldest time to write state rows for: the recorder's keep window."""
        keep_days = _recorder_keep_days(self.hass)
        return (dt_util.utcnow() - timedelta(days=keep_days)).timestamp()

    def _entity_unit(self, entity_id: str) -> str | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        return state.attributes.get("unit_of_measurement")

    async def _async_run_jobs(self, tank_id: str, jobs: list[EntityBackfill]) -> bool:
        """Write states and statistics. Returns True when states were written."""
        states_done = not self.backfill_states
        status: dict[str, Any] = {"time": dt_util.utcnow().isoformat()}
        try:
            if self.backfill_states and jobs:
                result = await async_backfill_states(self.hass, jobs)
                status.update(
                    inserted=result.inserted,
                    corrected=result.corrected,
                    waiting_for=result.skipped_entities,
                )
                states_done = not result.skipped_entities
            hours = 0
            for job in jobs:
                hours += await async_import_hourly_statistics(self.hass, job)
            status["statistics_hours"] = hours
        except RecorderUnavailable as err:
            _LOGGER.warning("History backfill skipped for tank %s: %s", tank_id, err)
            status["error"] = str(err)
            states_done = False
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("History backfill failed for tank %s", tank_id)
            status["error"] = repr(err)
            states_done = False
        self.backfill_status[tank_id] = status
        return states_done

    async def _async_backfill_tank(
        self, tank_id: str, series: Series, last_read: float
    ) -> None:
        """Backfill readings received since the last successful backfill."""
        async with self._backfill_lock:
            start = self.backfilled_until.get(tank_id)
            if start is None or start < series[0][0]:
                start = series[0][0]
            jobs = self._build_jobs(tank_id, series, start, last_read)
            if not jobs:
                return
            if await self._async_run_jobs(tank_id, jobs):
                self.backfilled_until[tank_id] = last_read
                await self._async_save_storage()

    async def async_start_initial_import(self) -> None:
        """Run after setup: finish pending backfills, then first-time imports.

        Waits first so the new entities' states are in the recorder.
        """
        await asyncio.sleep(INITIAL_IMPORT_DELAY_S)
        for tank_id, series in list(self.series.items()):
            last_read = self.last_read.get(tank_id)
            if (
                series
                and last_read
                and self.backfilled_until.get(tank_id, 0) < (last_read)
            ):
                await self._async_backfill_tank(tank_id, series, last_read)
        if not self.import_history:
            return
        for tank_id in [
            t for t in (self.data or {}) if not self.history_imported.get(t)
        ]:
            await self.async_import_history(tank_id)

    async def async_import_history(self, tank_id: str) -> None:
        """Download the full CSV history for a tank and write it to the recorder."""
        tank = (self.data or {}).get(tank_id)
        if not tank:
            return
        registrations = tank.get("sensors")
        if not isinstance(registrations, list) or not registrations:
            _LOGGER.warning("No sensor registrations found for tank %s", tank_id)
            return

        rows = await self._async_fetch_export_rows(tank_id, registrations)
        if rows is None:
            return

        if not rows:
            _LOGGER.info("No exported history for tank %s", tank_id)
            self.history_imported[tank_id] = True
            await self._async_save_storage()
            return

        exported = self._localize_export(tank, rows, self.series.get(tank_id, []))
        full = merge_series(exported, self.series.get(tank_id, []))
        if not full:
            return

        self._update_refill_from_series(tank_id, full)
        self.async_update_listeners()

        end_ts = self.last_read.get(tank_id, full[-1][0])
        async with self._backfill_lock:
            jobs = self._build_jobs(tank_id, full, full[0][0], end_ts)
            if not jobs:
                _LOGGER.warning(
                    "History import for tank %s found no entities to write", tank_id
                )
                return
            states_done = await self._async_run_jobs(tank_id, jobs)
            self.backfill_status[tank_id]["imported_rows"] = len(exported)
            self.history_imported[tank_id] = True
            if states_done:
                self.backfilled_until[tank_id] = max(
                    end_ts, self.backfilled_until.get(tank_id, 0)
                )
            await self._async_save_storage()
        _LOGGER.info(
            "Imported %d hourly readings of history for tank %s",
            len(exported),
            tank_id,
        )

    async def _async_fetch_export_rows(
        self, tank_id: str, registrations: list[Any]
    ) -> list[tuple[datetime, float]] | None:
        """Download CSV exports for all sensor registrations of a tank."""
        rows: list[tuple[datetime, float]] = []
        today = dt_util.now().date()
        for reg in registrations:
            if not isinstance(reg, dict) or not reg.get("registration_id"):
                continue
            start = _parse_date(reg.get("registration_date")) or (
                today - timedelta(days=EXPORT_CHUNK_DAYS)
            )
            end = (_parse_date(reg.get("end_date")) or today) + timedelta(days=1)
            chunk_start = start
            while chunk_start < end:
                chunk_end = min(end, chunk_start + timedelta(days=EXPORT_CHUNK_DAYS))
                try:
                    text = await self.client.async_export_history(
                        str(reg["registration_id"]), chunk_start, chunk_end
                    )
                    rows.extend(parse_export_csv(text))
                except (SmartOilGaugeException, ValueError) as err:
                    _LOGGER.warning(
                        "History export failed for tank %s (%s to %s): %s",
                        tank_id,
                        chunk_start,
                        chunk_end,
                        err,
                    )
                    return None
                chunk_start = chunk_end

        return rows

    def _localize_export(
        self,
        tank: dict[str, Any],
        rows: list[tuple[datetime, float]],
        reference: Series,
    ) -> Series:
        """Convert exported local times to UTC, verifying the time zone."""
        candidates: list[str] = []
        if self.hass.config.time_zone:
            candidates.append(self.hass.config.time_zone)
        candidates += [
            "America/New_York",
            "America/Chicago",
            "America/Denver",
            "America/Phoenix",
            "America/Los_Angeles",
            "America/Anchorage",
            "Pacific/Honolulu",
            "America/Halifax",
        ]
        recent = rows[-24 * 9 :]
        if reference:
            for name in dict.fromkeys(candidates):
                try:
                    tz = ZoneInfo(name)
                except KeyError, ValueError:
                    continue
                if timezone_matches(recent, reference, tz):
                    _LOGGER.debug("Export time zone resolved as %s", name)
                    return localize_rows(rows, tz, 0)

        last_read = parse_last_read(tank)
        offset = (
            offset_from_local_and_utc(tank.get("sensor_rt"), last_read)
            if last_read is not None
            else None
        )
        if offset is not None and last_read is not None:
            # Prefer a real (daylight-saving aware) zone whose current offset
            # matches the portal's, trying Home Assistant's own zone first.
            for name in dict.fromkeys(candidates):
                try:
                    tz = ZoneInfo(name)
                except KeyError, ValueError:
                    continue
                current = datetime.fromtimestamp(last_read, tz).utcoffset()
                if current is not None and current.total_seconds() == offset:
                    _LOGGER.info(
                        "Export time zone taken as %s from the portal's UTC offset",
                        name,
                    )
                    return localize_rows(rows, tz, 0)
            _LOGGER.warning(
                "Could not confirm the portal time zone; using a fixed UTC "
                "offset of %+.1f hours for imported history",
                offset / 3600,
            )
            return localize_rows(rows, None, offset)

        tz = ZoneInfo(self.hass.config.time_zone or "UTC")
        _LOGGER.warning("Could not confirm the portal time zone; assuming %s", tz.key)
        return localize_rows(rows, tz, 0)

    def _raise_api_breakage_issue(self) -> None:
        """Raise an entry-specific Home Assistant repair issue for API breakage."""
        async_create_issue(
            self.hass,
            DOMAIN,
            self.issue_id,
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=IssueSeverity.ERROR,
            translation_key="api_breakage",
        )


def _parse_date(value: Any) -> date | None:
    """Parse the date part of a portal timestamp string."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _recorder_keep_days(hass: HomeAssistant) -> int:
    """Return the recorder's purge window in days."""
    try:
        from homeassistant.components.recorder import get_instance  # noqa: PLC0415

        return int(get_instance(hass).keep_days)
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return 10


def _parse_stored_series(points: Any) -> Series:
    """Parse a stored ``[[ts, gallons], ...]`` list into a series."""
    if not isinstance(points, list):
        return []
    clean: list[tuple[float, float]] = []
    for point in points:
        if isinstance(point, list | tuple) and len(point) == 2:
            ts = parse_finite_float(point[0])
            gal = parse_finite_float(point[1])
            if ts is not None and gal is not None:
                clean.append((ts, gal))
    return merge_series(clean)
