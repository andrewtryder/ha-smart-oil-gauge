"""Coordinator tests for hourly history, backfill scheduling, and imports."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_oil_gauge import coordinator as coord_mod
from custom_components.smart_oil_gauge.client import CannotConnect
from custom_components.smart_oil_gauge.const import DOMAIN
from custom_components.smart_oil_gauge.coordinator import (
    SmartOilGaugeDataUpdateCoordinator,
    _parse_date,
    _parse_stored_series,
    _recorder_keep_days,
    parse_last_read,
)
from custom_components.smart_oil_gauge.recorder_writer import (
    BackfillResult,
    RecorderUnavailable,
    recorder_ready,
)

FIXTURES = Path(__file__).parent / "fixtures"
GRAPH = json.loads((FIXTURES / "graph_data.json").read_text())
LAST = GRAPH["datasets"]["71796"]["week"]["points"][-1]
CLIENT = "custom_components.smart_oil_gauge.client.SmartOilGaugeClient"
WRITER = "custom_components.smart_oil_gauge.coordinator"


def _tank(**overrides: Any) -> dict[str, Any]:
    tank = {
        "tank_id": "940670",
        "tank_name": "Test Tank",
        "sensor_gallons": str(LAST["gallons"]),
        "nominal": "550",
        "battery": "Fair",
        "sensor_usg": "1.8",
        "last_read": str(LAST["ts"]),
        "sensor_rt": "2026-11-18 03:57:38",
        "data_servers": "data.example.com",
        "sensors": [
            {
                "registration_id": "71796",
                "registration_date": "2026-11-10 00:00:00",
                "end_date": None,
            }
        ],
    }
    tank.update(overrides)
    return tank


@pytest.fixture(autouse=True)
def pinned_now():
    """Run as if it were one hour after the sample data's last reading."""
    now = datetime.fromtimestamp(LAST["ts"], UTC) + timedelta(hours=1)
    with patch(f"{WRITER}.dt_util.utcnow", return_value=now):
        yield now


@pytest.fixture
def no_writes():
    """Patch out recorder writes so these tests need no database."""
    with (
        patch(
            f"{WRITER}.async_backfill_states",
            new=AsyncMock(return_value=BackfillResult(inserted=1)),
        ) as states,
        patch(
            f"{WRITER}.async_import_hourly_statistics",
            new=AsyncMock(return_value=3),
        ) as stats,
    ):
        yield states, stats


async def _setup(hass: HomeAssistant, tanks, graph=GRAPH, **options):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "u@example.com", "password": "pw"},
        options={"import_history": False, **options},
    )
    entry.add_to_hass(hass)
    get_tanks = patch(f"{CLIENT}.async_get_tanks", return_value=tanks)
    get_graph = patch(
        f"{CLIENT}.async_get_graph_data",
        new=AsyncMock(
            side_effect=graph if isinstance(graph, Exception) else None,
            return_value=graph,
        ),
    )
    with (
        get_tanks as tanks_mock,
        get_graph as graph_mock,
        patch.object(coord_mod, "INITIAL_IMPORT_DELAY_S", 0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry, tanks_mock, graph_mock


def test_small_helpers() -> None:
    """Parsing helpers tolerate bad input."""
    assert parse_last_read({"last_read": "0"}) is None
    assert parse_last_read({"last_read": "17"}) == 17.0
    assert _parse_date("2026-06-28 18:57:27").isoformat() == "2026-06-28"
    assert _parse_date("bad-date-xx") is None
    assert _parse_date(None) is None
    assert _parse_stored_series("x") == []
    assert _parse_stored_series([[1, 2], ["a", 1], [1], (500, 6)]) == [
        (1.0, 2.0),
        (500.0, 6.0),
    ]


async def test_keep_days_without_recorder(hass: HomeAssistant) -> None:
    """Without a recorder the default purge window is assumed."""
    assert _recorder_keep_days(hass) == 10


async def test_recorder_ready_checks(hass: HomeAssistant) -> None:
    """Writes are refused without a recorder or mid-migration."""
    with pytest.raises(RecorderUnavailable, match="not loaded"):
        recorder_ready(hass)
    hass.config.components.add("recorder")
    instance = MagicMock(migration_in_progress=True)
    with (
        patch("homeassistant.components.recorder.get_instance", return_value=instance),
        pytest.raises(RecorderUnavailable, match="migration"),
    ):
        recorder_ready(hass)
    instance = MagicMock(migration_in_progress=False, schema_version=1)
    with (
        patch("homeassistant.components.recorder.get_instance", return_value=instance),
        pytest.raises(RecorderUnavailable, match="schema"),
    ):
        recorder_ready(hass)


async def test_poll_merges_week_and_backfills(
    hass: HomeAssistant, no_writes, caplog
) -> None:
    """A new upload fetches the week, detects the refill, and backfills."""
    states, stats = no_writes
    entry, _, graph_mock = await _setup(hass, [_tank()])
    coordinator = entry.runtime_data.coordinator
    await hass.async_block_till_done()

    assert len(coordinator.series["940670"]) == 172
    assert coordinator.last_read["940670"] == LAST["ts"]
    assert coordinator.last_refills["940670"]["in_progress"] is True
    assert states.await_count == 1
    jobs = states.await_args.args[1]
    assert {j.unit for j in jobs} == {"gal", "%"}
    assert jobs[1].to_state(275.0) == "50.0"
    assert stats.await_count == 2
    assert coordinator.backfilled_until["940670"] == LAST["ts"]
    assert coordinator.backfill_status["940670"]["inserted"] == 1
    assert "Test Tank: upload at" in caplog.text
    assert "172 in the last 7 days" in caplog.text

    # Same upload again: no new graph fetch.
    with patch(f"{CLIENT}.async_get_tanks", return_value=[_tank()]):
        with patch(f"{CLIENT}.async_get_graph_data", new=AsyncMock()) as again:
            await coordinator.async_refresh()
            await hass.async_block_till_done()
    again.assert_not_awaited()
    assert graph_mock.await_count == 1
    await hass.config_entries.async_unload(entry.entry_id)


async def test_poll_graph_failure_keeps_snapshot(
    hass: HomeAssistant, no_writes, caplog
) -> None:
    """If hourly data cannot be fetched the latest reading is still kept."""
    entry, _, _ = await _setup(hass, [_tank()], graph=CannotConnect("down"))
    coordinator = entry.runtime_data.coordinator
    assert coordinator.series["940670"] == [(float(LAST["ts"]), LAST["gallons"])]
    assert "Could not fetch hourly data" in caplog.text
    await hass.config_entries.async_unload(entry.entry_id)


async def test_backfill_disabled_and_waiting(
    hass: HomeAssistant, no_writes, caplog
) -> None:
    """With state backfill off only statistics are written."""
    states, stats = no_writes
    entry, _, _ = await _setup(hass, [_tank()], backfill_states=False)
    await hass.async_block_till_done()
    states.assert_not_awaited()
    assert stats.await_count == 2
    await hass.config_entries.async_unload(entry.entry_id)

    states.return_value = BackfillResult(skipped_entities=["sensor.x"])
    hass2_entry, _, _ = await _setup(hass, [_tank(tank_id="2")])
    await hass.async_block_till_done()
    coordinator = hass2_entry.runtime_data.coordinator
    assert "2" not in coordinator.backfilled_until
    assert coordinator.backfill_status["2"]["waiting_for"] == ["sensor.x"]
    assert "waiting for sensor.x" in caplog.text
    await hass.config_entries.async_unload(hass2_entry.entry_id)


@pytest.mark.parametrize(
    ("error", "expected"),
    [(RecorderUnavailable("no recorder"), "no recorder"), (RuntimeError("x"), "x")],
)
async def test_backfill_errors_are_recorded(
    hass: HomeAssistant, error, expected
) -> None:
    """Backfill failures are logged and kept for diagnostics, not raised."""
    with patch(f"{WRITER}.async_backfill_states", new=AsyncMock(side_effect=error)):
        entry, _, _ = await _setup(hass, [_tank()])
        await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    assert expected in coordinator.backfill_status["940670"]["error"]
    assert "940670" not in coordinator.backfilled_until
    await hass.config_entries.async_unload(entry.entry_id)


async def test_storage_round_trip(hass: HomeAssistant, no_writes) -> None:
    """Series and progress survive a restart."""
    entry, _, _ = await _setup(hass, [_tank()])
    await hass.async_block_till_done()
    first = entry.runtime_data.coordinator
    await first._async_save_storage()

    client = MagicMock()
    second = SmartOilGaugeDataUpdateCoordinator(hass, client, 1, entry.entry_id)
    await second._async_load_storage()
    assert second.series["940670"] == first.series["940670"]
    assert second.last_read == first.last_read
    assert second.backfilled_until == first.backfilled_until
    assert second.last_refills["940670"]["in_progress"] is True
    await hass.config_entries.async_unload(entry.entry_id)


async def test_load_history_state_ignores_garbage(hass: HomeAssistant) -> None:
    """Corrupt stored history is ignored field by field."""
    coordinator = SmartOilGaugeDataUpdateCoordinator(hass, MagicMock(), 1, "x")
    coordinator._load_history_state(
        {
            "series": {"1": [[1, 2]], "2": "bad"},
            "last_read": {"1": "nan", "2": 5},
            "backfilled_until": "bad",
            "history_imported": {"1": True, "2": "yes"},
        }
    )
    assert coordinator.series == {"1": [(1.0, 2.0)], "2": []}
    assert coordinator.last_read == {"2": 5.0}
    assert coordinator.history_imported == {"1": True, "2": False}


def _csv(series_start: datetime, hours: int, gallons: float = 90.0) -> str:
    tz = coord_mod.ZoneInfo("America/New_York")
    lines = ["Time,Gallons"]
    for hour in range(hours):
        when = (series_start + timedelta(hours=hour)).astimezone(tz)
        lines.append(f'"{when:%Y-%m-%d %H:%M:%S}",{gallons}')
    for point in GRAPH["datasets"]["71796"]["week"]["points"]:
        when = datetime.fromtimestamp(point["ts"], UTC).astimezone(tz)
        lines.append(f'"{when:%Y-%m-%d %H:%M:%S}",{point["gallons"]}')
    return "\n".join(lines)


async def test_import_history_paths(hass: HomeAssistant, no_writes, caplog) -> None:
    """Exercise the import's guard rails and time-zone fallbacks."""
    states, _ = no_writes
    await hass.config.async_set_time_zone("America/New_York")
    entry, _, _ = await _setup(hass, [_tank()])
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    start = datetime(2026, 11, 1, tzinfo=UTC)

    # Unknown tank and tank without registrations.
    await coordinator.async_import_history("missing")
    coordinator.data["940670"]["sensors"] = []
    await coordinator.async_import_history("940670")
    assert "No sensor registrations" in caplog.text
    coordinator.data["940670"]["sensors"] = _tank()["sensors"]

    # Export failure stops the import without marking it done.
    with patch(
        f"{CLIENT}.async_export_history", new=AsyncMock(side_effect=CannotConnect())
    ):
        await coordinator.async_import_history("940670")
    assert not coordinator.history_imported.get("940670")

    # Empty export is marked done.
    with patch(
        f"{CLIENT}.async_export_history", new=AsyncMock(return_value="Time,Gallons\n")
    ):
        await coordinator.async_import_history("940670")
    assert coordinator.history_imported["940670"] is True

    # Normal import resolves the time zone from the overlap with the week.
    states.reset_mock()
    with patch(
        f"{CLIENT}.async_export_history",
        new=AsyncMock(return_value=_csv(start, 100)),
    ) as export:
        await coordinator.async_import_history("940670")
    assert export.await_count == 1
    assert coordinator.backfill_status["940670"]["imported_rows"] == 272
    job = states.await_args.args[1][0]
    assert job.series[0][0] == start.timestamp()
    assert job.states_not_before_ts is not None

    # Without any overlap, use the zone matching the portal's own offset,
    # which keeps daylight saving correct for older readings.
    coordinator.series["940670"] = []
    summer = datetime(2026, 7, 1, 12, tzinfo=UTC)
    with patch(
        f"{CLIENT}.async_export_history",
        new=AsyncMock(return_value=_csv(summer, 10)),
    ):
        await coordinator.async_import_history("940670")
    assert "taken as America/New_York" in caplog.text
    job = states.await_args.args[1][0]
    assert job.series[0][0] == summer.timestamp()

    # An offset no candidate zone has: fixed offset.
    coordinator.data["940670"]["sensor_rt"] = "2026-11-18 01:27:38"
    with patch(
        f"{CLIENT}.async_export_history",
        new=AsyncMock(return_value=_csv(start, 10)),
    ):
        await coordinator.async_import_history("940670")
    assert "fixed UTC offset of -7.5 hours" in caplog.text

    # No offset either: assume Home Assistant's time zone.
    coordinator.data["940670"]["sensor_rt"] = None
    with patch(
        f"{CLIENT}.async_export_history",
        new=AsyncMock(return_value=_csv(start, 10)),
    ):
        await coordinator.async_import_history("940670")
    assert "assuming America/New_York" in caplog.text
    await hass.config_entries.async_unload(entry.entry_id)


async def test_import_history_without_entities(
    hass: HomeAssistant, no_writes, caplog
) -> None:
    """If the sensors are gone the import reports it and writes nothing."""
    entry, _, _ = await _setup(hass, [_tank()])
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    with (
        patch.object(coordinator, "_entity_ids", return_value={}),
        patch(
            f"{CLIENT}.async_export_history",
            new=AsyncMock(return_value=_csv(datetime(2026, 11, 1, tzinfo=UTC), 5)),
        ),
    ):
        await coordinator.async_import_history("940670")
    assert "found no entities" in caplog.text
    await hass.config_entries.async_unload(entry.entry_id)


async def test_initial_import_runs_once(hass: HomeAssistant, no_writes) -> None:
    """The first-setup import runs for tanks never imported, after a delay."""
    entry, _, _ = await _setup(hass, [_tank()])
    coordinator = entry.runtime_data.coordinator
    coordinator.import_history = True
    with (
        patch.object(coord_mod, "INITIAL_IMPORT_DELAY_S", 0),
        patch.object(coordinator, "async_import_history", new=AsyncMock()) as run,
    ):
        await coordinator.async_start_initial_import()
        run.assert_awaited_once_with("940670")
        coordinator.history_imported["940670"] = True
        await coordinator.async_start_initial_import()
        run.assert_awaited_once()
        coordinator.import_history = False
        coordinator.history_imported.clear()
        await coordinator.async_start_initial_import()
        run.assert_awaited_once()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_import_button(hass: HomeAssistant, no_writes) -> None:
    """Pressing Import history starts an import for that tank."""
    entry, _, _ = await _setup(hass, [_tank()])
    coordinator = entry.runtime_data.coordinator
    with patch.object(coordinator, "async_import_history", new=AsyncMock()) as run:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.test_tank_import_history"},
            blocking=True,
        )
        await hass.async_block_till_done()
    run.assert_awaited_once_with("940670")
    await hass.config_entries.async_unload(entry.entry_id)


async def test_older_refill_does_not_replace_newer(hass: HomeAssistant) -> None:
    """A refill older than the known one is ignored."""
    coordinator = SmartOilGaugeDataUpdateCoordinator(hass, MagicMock(), 1, "x")
    newer = datetime(2030, 1, 1, tzinfo=UTC)
    coordinator.last_refills["1"] = {"amount": 5.0, "timestamp": newer}
    levels = [60.0] * 5 + [100.0, 140.0] + [140.0] * 8
    coordinator._update_refill_from_series(
        "1", [(i * 3600.0, g) for i, g in enumerate(levels)]
    )
    assert coordinator.last_refills["1"]["timestamp"] == newer


async def test_rolling_backfill_respects_keep_days(
    hass: HomeAssistant, no_writes
) -> None:
    """Rolling backfills honor the recorder's purge_keep_days, not a constant."""
    states, _ = no_writes
    now = datetime.fromtimestamp(LAST["ts"], UTC) + timedelta(hours=1)
    with (
        patch(f"{WRITER}.dt_util.utcnow", return_value=now),
        patch(f"{WRITER}._recorder_keep_days", return_value=3),
    ):
        entry, _, _ = await _setup(hass, [_tank()])
        await hass.async_block_till_done()
    job = states.await_args.args[1][0]
    assert job.states_not_before_ts == (now - timedelta(days=3)).timestamp()
    # The week of readings is still passed in full for statistics.
    assert job.start_ts == GRAPH["datasets"]["71796"]["week"]["points"][0]["ts"]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_keep_days_reads_recorder_setting(hass: HomeAssistant) -> None:
    """The keep window comes from the running recorder's configuration."""
    with patch(
        "homeassistant.components.recorder.get_instance",
        return_value=MagicMock(keep_days=45),
    ):
        assert _recorder_keep_days(hass) == 45
