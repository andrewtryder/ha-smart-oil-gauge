"""End-to-end tests that write backfilled history into a real recorder database.

These run against SQLite by default. Run them against MariaDB/MySQL or
PostgreSQL with ``--dburl``, for example::

    pytest tests/test_recorder_backfill.py \
        --dburl "mysql://root:pw@127.0.0.1:3306/ha_test?charset=utf8mb4"
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.smart_oil_gauge import coordinator as coordinator_module
from custom_components.smart_oil_gauge.const import DOMAIN
from custom_components.smart_oil_gauge.coordinator import format_state
from custom_components.smart_oil_gauge.recorder_writer import (
    EntityBackfill,
    async_backfill_states,
    async_import_hourly_statistics,
)

FIXTURES = Path(__file__).parent / "fixtures"
ENTITY = "sensor.test_tank_oil_level"
ATTRS = {"unit_of_measurement": "gal", "state_class": "measurement"}
T0 = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """Start the recorder before Home Assistant, then enable custom components."""
    return


def _history(hass: HomeAssistant, entity_id: str, start: datetime, end: datetime):
    return get_significant_states(
        hass,
        start,
        end,
        [entity_id],
        significant_changes_only=False,
        include_start_time_state=False,
    ).get(entity_id, [])


@pytest.fixture
def recorder_series() -> list[tuple[float, float]]:
    """Hourly readings at :57, as the gauge reports them."""
    base = T0 + timedelta(minutes=57)
    return [
        ((base + timedelta(hours=i)).timestamp(), 60.0 + 10.0 * i) for i in range(8)
    ]


async def test_backfill_inserts_and_corrects_rows(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    recorder_series: list[tuple[float, float]],
) -> None:
    """Readings appear in history at their real times; stale rows are fixed."""
    # Live state at T0 (reading 0 was known), then a stale poll at +3h05 that
    # still only knew reading 0 because the gauge had not uploaded yet.
    freezer.move_to(T0 + timedelta(minutes=58))
    hass.states.async_set(ENTITY, "60.0", ATTRS)
    await async_wait_recording_done(hass)
    freezer.move_to(T0 + timedelta(hours=3, minutes=5))
    hass.states.async_set(ENTITY, "60.0", {**ATTRS, "poll": 1})
    await async_wait_recording_done(hass)
    hass.states.async_set(ENTITY, "60.0", ATTRS)
    await async_wait_recording_done(hass)

    freezer.move_to(T0 + timedelta(hours=10))
    job = EntityBackfill(
        entity_id=ENTITY,
        series=recorder_series,
        start_ts=recorder_series[0][0],
        end_ts=recorder_series[-1][0],
        to_state=format_state,
        unit="gal",
    )
    result = await async_backfill_states(hass, [job])
    await async_wait_recording_done(hass)

    # Reading 0 already had a row (the live state 1 minute later is not a
    # match), so 8 readings are inserted and the stale polls are corrected.
    assert result.inserted == 8
    assert result.corrected >= 1
    assert result.skipped_entities == []

    history = await recorder_mock.async_add_executor_job(
        _history, hass, ENTITY, T0, T0 + timedelta(hours=10)
    )
    by_time = {s.last_updated.replace(microsecond=0): s.state for s in history}
    for ts, gal in recorder_series:
        assert by_time[datetime.fromtimestamp(ts, UTC)] == format_state(gal)
    # The poll at +3h05 now shows the reading taken at +2h57.
    stale_time = T0 + timedelta(hours=3, minutes=5)
    stale_rows = [s for s in history if s.last_updated == stale_time]
    assert stale_rows
    assert all(s.state == format_state(80.0) for s in stale_rows)
    # History is in time order and never steps backwards in this rising series.
    values = [float(s.state) for s in history]
    assert values == sorted(values)

    # Running the same backfill again changes nothing.
    again = await async_backfill_states(hass, [job])
    assert again.inserted == 0
    assert again.corrected == 0


async def test_backfill_waits_for_unknown_entity(
    recorder_mock: Recorder, hass: HomeAssistant, recorder_series
) -> None:
    """An entity with no recorded states yet is reported, not created."""
    job = EntityBackfill(
        entity_id="sensor.never_seen",
        series=recorder_series,
        start_ts=recorder_series[0][0],
        end_ts=recorder_series[-1][0],
        to_state=format_state,
    )
    result = await async_backfill_states(hass, [job])
    assert result.skipped_entities == ["sensor.never_seen"]
    assert result.inserted == 0


async def test_statistics_import(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    recorder_series: list[tuple[float, float]],
) -> None:
    """Hourly statistics match a time-weighted mean of the readings."""
    freezer.move_to(T0)
    hass.states.async_set(ENTITY, "60.0", ATTRS)
    await async_wait_recording_done(hass)
    freezer.move_to(T0 + timedelta(hours=12))

    job = EntityBackfill(
        entity_id=ENTITY,
        series=recorder_series,
        start_ts=recorder_series[0][0],
        end_ts=recorder_series[-1][0],
        to_state=format_state,
        unit="gal",
    )
    hours = await async_import_hourly_statistics(hass, job)
    await async_wait_recording_done(hass)
    assert hours > 0

    stats = await recorder_mock.async_add_executor_job(
        statistics_during_period,
        hass,
        T0,
        T0 + timedelta(hours=12),
        {ENTITY},
        "hour",
        None,
        {"mean", "min", "max"},
    )
    rows = stats[ENTITY]
    # Hour 11:00-12:00: 60 until 11:57, then 70.
    hour = next(r for r in rows if r["start"] == (T0 + timedelta(hours=1)).timestamp())
    assert hour["min"] == pytest.approx(60.0)
    assert hour["max"] == pytest.approx(70.0)
    assert hour["mean"] == pytest.approx((60 * 57 + 70 * 3) / 60)


def _tank(last_read: float, gallons: float) -> dict[str, Any]:
    return {
        "tank_id": "940670",
        "tank_name": "Test Tank",
        "sensor_gallons": str(gallons),
        "nominal": "550",
        "fillable": "502",
        "battery": "Fair",
        "sensor_usg": "1.8",
        "last_read": str(int(last_read)),
        "sensor_rt": "2026-11-18 03:57:38",
        "data_servers": "data.example.com",
        "sensors": [
            {
                "registration_id": "71796",
                "registration_date": "2026-11-17 00:00:00",
                "end_date": None,
            }
        ],
    }


async def test_integration_backfills_week_on_poll(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A poll with a new upload writes the week's hourly readings to history."""
    await hass.config.async_set_time_zone("America/New_York")
    graph = json.loads((FIXTURES / "graph_data.json").read_text())
    points = graph["datasets"]["71796"]["week"]["points"]
    last = points[-1]
    freezer.move_to(datetime.fromtimestamp(last["ts"], UTC) + timedelta(hours=1))

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "u@example.com", "password": "pw"},
        options={"import_history": False},
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
            return_value=[_tank(last["ts"], last["gallons"])],
        ),
        patch(
            "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_graph_data",
            new=AsyncMock(return_value=graph),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await async_wait_recording_done(hass)

        coordinator = entry.runtime_data.coordinator
        # The first backfill ran before the entity's first state was committed,
        # so it waits; the next poll finishes it.
        await coordinator._async_backfill_tank(
            "940670", coordinator.series["940670"], last["ts"]
        )
        await hass.async_block_till_done()
        await async_wait_recording_done(hass)

    registry = er.async_get(hass)
    level = registry.async_get_entity_id("sensor", DOMAIN, "940670_oil_level")
    pct = registry.async_get_entity_id("sensor", DOMAIN, "940670_oil_percentage")
    last_read = registry.async_get_entity_id("sensor", DOMAIN, "940670_last_read")
    refill = registry.async_get_entity_id("sensor", DOMAIN, "940670_last_refill_amount")
    assert level and pct and last_read and refill

    assert (
        hass.states.get(last_read).state
        == datetime.fromtimestamp(last["ts"], UTC).isoformat()
    )
    refill_state = hass.states.get(refill)
    assert float(refill_state.state) == pytest.approx(140.3)
    assert refill_state.attributes["equalizing"] is True

    start = datetime.fromtimestamp(points[0]["ts"], UTC) - timedelta(minutes=1)
    end = datetime.fromtimestamp(last["ts"], UTC) + timedelta(hours=1)
    history = await recorder_mock.async_add_executor_job(
        _history, hass, level, start, end
    )
    recorded = {round(s.last_updated.timestamp()): s.state for s in history}
    for point in points:
        assert recorded[point["ts"]] == format_state(point["gallons"])

    pct_history = await recorder_mock.async_add_executor_job(
        _history, hass, pct, start, end
    )
    pct_recorded = {round(s.last_updated.timestamp()): s.state for s in pct_history}
    assert pct_recorded[points[0]["ts"]] == format_state(
        round(points[0]["gallons"] / 550 * 100, 1)
    )
    assert coordinator.backfilled_until["940670"] == last["ts"]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_integration_csv_history_import(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The CSV import adds older readings to statistics and recent ones to history."""
    await hass.config.async_set_time_zone("America/New_York")
    graph = json.loads((FIXTURES / "graph_data.json").read_text())
    points = graph["datasets"]["71796"]["week"]["points"]
    last = points[-1]
    freezer.move_to(datetime.fromtimestamp(last["ts"], UTC) + timedelta(hours=1))

    # 20 days of older history, hourly, in local time, ending where the week
    # graph starts.
    week_start = datetime.fromtimestamp(points[0]["ts"], UTC)
    local_tz = coordinator_module.ZoneInfo("America/New_York")
    csv_lines = ["Time,Gallons"]
    for hour in range(20 * 24, 0, -1):
        when = (week_start - timedelta(hours=hour)).astimezone(local_tz)
        csv_lines.append(f'"{when:%Y-%m-%d %H:%M:%S}",90.0')
    for point in points:
        when = datetime.fromtimestamp(point["ts"], UTC).astimezone(local_tz)
        csv_lines.append(f'"{when:%Y-%m-%d %H:%M:%S}",{point["gallons"]}')
    csv_text = "\n".join(csv_lines) + "\n"

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "u@example.com", "password": "pw"},
        options={"import_history": False},
    )
    entry.add_to_hass(hass)
    export = AsyncMock(return_value=csv_text)
    with (
        patch(
            "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
            return_value=[_tank(last["ts"], last["gallons"])],
        ),
        patch(
            "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_graph_data",
            new=AsyncMock(return_value=graph),
        ),
        patch(
            "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_export_history",
            new=export,
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await async_wait_recording_done(hass)
        coordinator = entry.runtime_data.coordinator
        await coordinator.async_import_history("940670")
        await hass.async_block_till_done()
        await async_wait_recording_done(hass)

    assert export.await_count >= 1
    assert coordinator.history_imported["940670"] is True
    status = coordinator.backfill_status["940670"]
    assert status["imported_rows"] == 20 * 24 + len(points)
    assert "error" not in status

    level = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, "940670_oil_level")
    # 20 days back is older than the 10-day keep window: statistics only.
    old_hour = (week_start - timedelta(days=15)).replace(minute=0, second=0)
    stats = await recorder_mock.async_add_executor_job(
        statistics_during_period,
        hass,
        old_hour,
        old_hour + timedelta(hours=3),
        {level},
        "hour",
        None,
        {"mean"},
    )
    assert stats[level]
    assert stats[level][0]["mean"] == pytest.approx(90.0)
    old_history = await recorder_mock.async_add_executor_job(
        _history, hass, level, old_hour, old_hour + timedelta(hours=3)
    )
    assert old_history == []

    # Within the keep window: real state rows at their reading times.
    recent_start = week_start - timedelta(days=2)
    recent = await recorder_mock.async_add_executor_job(
        _history, hass, level, recent_start, week_start
    )
    assert len(recent) >= 40
    assert all(s.state == "90.0" for s in recent)
    await hass.config_entries.async_unload(entry.entry_id)
