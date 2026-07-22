"""Tests for Smart Oil Gauge sensor entities."""

from unittest.mock import MagicMock, patch

from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_oil_gauge.const import DOMAIN

MOCK_TANK_DATA = [
    {
        "tank_id": "12345",
        "tank_name": "Main House Tank",
        "sensor_gallons": "100.0",
        "nominal": "275",
        "battery": "Excellent",
        "sensor_usg": "0.85",
        "fillable": "250",
        "low_level": "0.25",
    }
]

MOCK_TANK_DATA_MODEL_FALLBACK = [
    {
        "tank_id": "12345",
        "tank_name": "Main House Tank",
        "sensor_gallons": None,
        "model_gallons": "80.0",
        "nominal": "200",
        "battery": "Fair",
        "sensor_usg": "0.50",
        "fillable": "180",
        "low_level": "0.25",
    }
]

MOCK_TANK_DATA_INVALID_CAPACITY = [
    {
        "tank_id": "12345",
        "tank_name": "Main House Tank",
        "sensor_gallons": "100.0",
        "nominal": "0",
        "battery": "Poor",
        "sensor_usg": "invalid_number",
        "fillable": "invalid_number",
        "low_level": "0.25",
    }
]

MOCK_TANK_DATA_LOW_USAGE = [
    {
        "tank_id": "12345",
        "tank_name": "Main House Tank",
        "sensor_gallons": "100.0",
        "nominal": "275",
        "battery": "Good",
        "sensor_usg": "0.15",  # Less than 0.2
        "fillable": "250",
        "low_level": "0.25",
    }
]

MOCK_TANK_DATA_INVALID_LEVEL = [
    {
        "tank_id": "12345",
        "tank_name": "Main House Tank",
        "sensor_gallons": "invalid_number",
        "nominal": "275",
        "battery": "Good",
        "sensor_usg": "0.85",
        "fillable": "250",
        "low_level": "0.25",
    }
]


async def test_sensors_success(hass: HomeAssistant) -> None:
    """Test sensors load successfully and show correct states."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "test@example.com", "password": "test_password"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=MOCK_TANK_DATA,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Check Oil Level Sensor
        level_state = hass.states.get("sensor.main_house_tank_oil_level")
        assert level_state is not None
        assert level_state.state == "100.0"
        assert level_state.attributes["unit_of_measurement"] == "gal"
        assert level_state.attributes["icon"] == "mdi:gauge"

        # Check Oil Percentage Sensor
        # (100.0 / 275) * 100.0 = 36.3636... -> rounded to 36.4
        percentage_state = hass.states.get("sensor.main_house_tank_oil_percentage")
        assert percentage_state is not None
        assert percentage_state.state == "36.4"
        assert percentage_state.attributes["unit_of_measurement"] == PERCENTAGE
        assert percentage_state.attributes["icon"] == "mdi:water-percent"

        # Check Daily Usage Rate Sensor
        usage_state = hass.states.get("sensor.main_house_tank_daily_usage_rate")
        assert usage_state is not None
        assert usage_state.state == "0.85"
        assert usage_state.attributes["unit_of_measurement"] == "gal/day"
        assert usage_state.attributes["icon"] == "mdi:chart-line"

        # Check Battery Sensor
        battery_state = hass.states.get("sensor.main_house_tank_battery")
        assert battery_state is not None
        assert battery_state.state == "Excellent"
        assert battery_state.attributes["icon"] == "mdi:battery"

        # Check Last Portal Update Sensor
        last_checked_state = hass.states.get(
            "sensor.main_house_tank_last_portal_update"
        )
        assert last_checked_state is not None
        assert last_checked_state.state != "unknown"
        assert last_checked_state.attributes["device_class"] == "timestamp"
        assert last_checked_state.attributes["icon"] == "mdi:clock-outline"

        # Check Max Level Sensor
        max_level_state = hass.states.get("sensor.main_house_tank_max_level")
        assert max_level_state is not None
        assert max_level_state.state == "275.0"
        assert max_level_state.attributes["unit_of_measurement"] == "gal"
        assert max_level_state.attributes["icon"] == "mdi:gauge-full"

        # Check Max Fill Sensor
        # 250 - 100 = 150
        max_fill_state = hass.states.get("sensor.main_house_tank_max_fill")
        assert max_fill_state is not None
        assert max_fill_state.state == "150.0"
        assert max_fill_state.attributes["unit_of_measurement"] == "gal"
        assert max_fill_state.attributes["icon"] == "mdi:gauge-empty"

        # Check Days to 1/4 Sensor
        # (100.0 - 275 * 0.25) / 0.85 = 31.25 / 0.85 = 36.76... -> 37
        days_quarter_state = hass.states.get("sensor.main_house_tank_days_to_1_4")
        assert days_quarter_state is not None
        assert days_quarter_state.state == "37"
        assert days_quarter_state.attributes["unit_of_measurement"] == "days"
        assert days_quarter_state.attributes["icon"] == "mdi:calendar-clock"

        # Check Days to 1/8 Sensor
        # (100.0 - 275 * 0.125) / 0.85 = 65.625 / 0.85 = 77.205... -> 77
        days_eighth_state = hass.states.get("sensor.main_house_tank_days_to_1_8")
        assert days_eighth_state is not None
        assert days_eighth_state.state == "77"
        assert days_eighth_state.attributes["unit_of_measurement"] == "days"
        assert days_eighth_state.attributes["icon"] == "mdi:calendar-clock"


async def test_sensors_model_fallback(hass: HomeAssistant) -> None:
    """Test level sensor falls back to model_gallons when sensor_gallons is None."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "test@example.com", "password": "test_password"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=MOCK_TANK_DATA_MODEL_FALLBACK,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Level should be 80.0
        level_state = hass.states.get("sensor.main_house_tank_oil_level")
        assert level_state is not None
        assert level_state.state == "80.0"

        # Percentage should be 40.0 (80.0 / 200 * 100)
        percentage_state = hass.states.get("sensor.main_house_tank_oil_percentage")
        assert percentage_state is not None
        assert percentage_state.state == "40.0"

        # Battery icon should change to battery-alert for "Fair" status
        battery_state = hass.states.get("sensor.main_house_tank_battery")
        assert battery_state is not None
        assert battery_state.state == "Fair"
        assert battery_state.attributes["icon"] == "mdi:battery-alert"

        # Max Level should be 200.0
        max_level_state = hass.states.get("sensor.main_house_tank_max_level")
        assert max_level_state is not None
        assert max_level_state.state == "200.0"

        # Since sensor_gallons is None, these should be unknown (None in HA)
        max_fill_state = hass.states.get("sensor.main_house_tank_max_fill")
        assert max_fill_state is not None
        assert max_fill_state.state == "unknown"

        days_quarter_state = hass.states.get("sensor.main_house_tank_days_to_1_4")
        assert days_quarter_state is not None
        assert days_quarter_state.state == "unknown"

        days_eighth_state = hass.states.get("sensor.main_house_tank_days_to_1_8")
        assert days_eighth_state is not None
        assert days_eighth_state.state == "unknown"


async def test_sensors_invalid_data(hass: HomeAssistant) -> None:
    """Test safety checks for division by zero and bad string conversion."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "test@example.com", "password": "test_password"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=MOCK_TANK_DATA_INVALID_CAPACITY,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Percentage should be 'unknown' or None because capacity is 0
        percentage_state = hass.states.get("sensor.main_house_tank_oil_percentage")
        assert percentage_state is not None
        assert percentage_state.state == "unknown"

        # Usage state should be 'unknown' because of bad float cast
        usage_state = hass.states.get("sensor.main_house_tank_daily_usage_rate")
        assert usage_state is not None
        assert usage_state.state == "unknown"

        # Battery icon for "Poor" should be mdi:battery-outline
        battery_state = hass.states.get("sensor.main_house_tank_battery")
        assert battery_state is not None
        assert battery_state.state == "Poor"
        assert battery_state.attributes["icon"] == "mdi:battery-outline"

        # Max Level should be "0.0" (float("0") is valid)
        max_level_state = hass.states.get("sensor.main_house_tank_max_level")
        assert max_level_state is not None
        assert max_level_state.state == "0.0"

        # Max fill should be 'unknown' due to invalid_number in fillable
        max_fill_state = hass.states.get("sensor.main_house_tank_max_fill")
        assert max_fill_state is not None
        assert max_fill_state.state == "unknown"


async def test_sensors_low_usage(hass: HomeAssistant) -> None:
    """Test days remaining return unknown if daily usage is less than 0.2."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "test@example.com", "password": "test_password"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=MOCK_TANK_DATA_LOW_USAGE,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Days to 1/4 and 1/8 should be 'unknown' (usage 0.15 < 0.2)
        days_quarter_state = hass.states.get("sensor.main_house_tank_days_to_1_4")
        assert days_quarter_state is not None
        assert days_quarter_state.state == "unknown"

        days_eighth_state = hass.states.get("sensor.main_house_tank_days_to_1_8")
        assert days_eighth_state is not None
        assert days_eighth_state.state == "unknown"


async def test_sensors_invalid_level(hass: HomeAssistant) -> None:
    """Test sensor handles invalid level strings properly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "test@example.com", "password": "test_password"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=MOCK_TANK_DATA_INVALID_LEVEL,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Level should be 'unknown' due to invalid string
        level_state = hass.states.get("sensor.main_house_tank_oil_level")
        assert level_state is not None
        assert level_state.state == "unknown"

        # Percentage should be 'unknown'
        percentage_state = hass.states.get("sensor.main_house_tank_oil_percentage")
        assert percentage_state is not None
        assert percentage_state.state == "unknown"

        # Max fill should be 'unknown'
        max_fill_state = hass.states.get("sensor.main_house_tank_max_fill")
        assert max_fill_state is not None
        assert max_fill_state.state == "unknown"

        # Days to 1/4 should be 'unknown'
        days_quarter_state = hass.states.get("sensor.main_house_tank_days_to_1_4")
        assert days_quarter_state is not None
        assert days_quarter_state.state == "unknown"

        # Days to 1/8 should be 'unknown'
        days_eighth_state = hass.states.get("sensor.main_house_tank_days_to_1_8")
        assert days_eighth_state is not None
        assert days_eighth_state.state == "unknown"


async def test_sensors_dynamic_discovery_and_availability(
    hass: HomeAssistant,
) -> None:
    """Test dynamic tank discovery and entity availability when tank disappears."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "test@example.com", "password": "test_password"},
    )
    entry.add_to_hass(hass)

    tank1 = {
        "tank_id": "12345",
        "tank_name": "Main Tank",
        "sensor_gallons": "100.0",
        "nominal": "275",
    }
    tank2 = {
        "tank_id": "67890",
        "tank_name": "Garage Tank",
        "sensor_gallons": "50.0",
        "nominal": "150",
    }

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=[tank1],
    ) as mock_get_tanks:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Tank 1 level sensor exists and is available
        t1_level = hass.states.get("sensor.main_tank_oil_level")
        assert t1_level is not None
        assert t1_level.state == "100.0"

        # Tank 2 does not exist yet
        t2_level = hass.states.get("sensor.garage_tank_oil_level")
        assert t2_level is None

        # Simulate update returning both Tank 1 and Tank 2
        mock_get_tanks.return_value = [tank1, tank2]
        coordinator = entry.runtime_data.coordinator
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # Tank 2 level sensor was dynamically discovered and added
        t2_level = hass.states.get("sensor.garage_tank_oil_level")
        assert t2_level is not None
        assert t2_level.state == "50.0"

        # Simulate update where Tank 2 disappears
        mock_get_tanks.return_value = [tank1]
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # Tank 2 level sensor should now be unavailable
        t2_level_after = hass.states.get("sensor.garage_tank_oil_level")
        assert t2_level_after is not None
        assert t2_level_after.state == "unavailable"


async def test_sensors_overflow_arithmetic(hass: HomeAssistant) -> None:
    """Test calculations resulting in non-finite or out-of-range bounds return None."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "test@example.com",
            "password": "test_password",
        },
    )
    entry.add_to_hass(hass)

    tank_overflow = {
        "tank_id": "12345",
        "tank_name": "Overflow Tank",
        "sensor_gallons": "1e308",
        "nominal": "1e-308",
        "sensor_usg": "1e-308",
        "fillable": "1e308",
    }

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=[tank_overflow],
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        # Verify setup with overflow data completes safely without uncaught exceptions
        assert hass.states.get("sensor.overflow_tank_oil_level") is not None


def test_sensor_helper_functions_direct() -> None:
    """Test sensor helper calculation edge cases directly."""
    from custom_components.smart_oil_gauge.sensor import (
        _get_days_to_eighth_value,
        _get_days_to_quarter_value,
        _get_estimated_runout_date_value,
        _get_max_fill_value,
    )

    mock_coord = MagicMock()

    # _get_max_fill_value non-finite difference
    assert (
        _get_max_fill_value(
            {"sensor_gallons": "-1e308", "fillable": "1e308"}, mock_coord
        )
        is None
    )

    # _get_percentage_value overflow
    from custom_components.smart_oil_gauge.sensor import _get_percentage_value

    assert (
        _get_percentage_value(
            {"sensor_gallons": "1e308", "nominal": "1e-308"}, mock_coord
        )
        is None
    )

    # _get_days_to_quarter_value out of range / non-finite
    assert (
        _get_days_to_quarter_value(
            {"sensor_gallons": "1e308", "sensor_usg": "0.5"}, mock_coord
        )
        is None
    )

    # _get_days_to_quarter_value below or at threshold clamps to 0
    assert (
        _get_days_to_quarter_value(
            {
                "sensor_gallons": "20.0",
                "nominal": "275",
                "sensor_usg": "1.0",
                "low_level": "0.25",
            },
            mock_coord,
        )
        == 0
    )
    assert (
        _get_days_to_quarter_value(
            {
                "sensor_gallons": "68.75",
                "nominal": "275",
                "sensor_usg": "1.0",
                "low_level": "0.25",
            },
            mock_coord,
        )
        == 0
    )

    # _get_days_to_eighth_value out of range / non-finite
    assert (
        _get_days_to_eighth_value(
            {"sensor_gallons": "1e308", "sensor_usg": "0.5"}, mock_coord
        )
        is None
    )

    # _get_days_to_eighth_value below or at threshold clamps to 0
    assert (
        _get_days_to_eighth_value(
            {"sensor_gallons": "10.0", "nominal": "275", "sensor_usg": "1.0"},
            mock_coord,
        )
        == 0
    )
    assert (
        _get_days_to_eighth_value(
            {"sensor_gallons": "34.375", "nominal": "275", "sensor_usg": "1.0"},
            mock_coord,
        )
        == 0
    )

    # _get_estimated_runout_date_value out of range
    assert (
        _get_estimated_runout_date_value(
            {"sensor_gallons": "1e308", "sensor_usg": "0.5"}, mock_coord
        )
        is None
    )


async def test_sensors_refill_detection_and_runout_date(
    hass: HomeAssistant,
) -> None:
    """Test estimated runout date and refill detection sensors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "test@example.com", "password": "test_password"},
    )
    entry.add_to_hass(hass)

    tank_initial = {
        "tank_id": "12345",
        "tank_name": "Main Tank",
        "sensor_gallons": "50.0",
        "nominal": "275",
        "sensor_usg": "1.0",
    }
    tank_refilled = {
        "tank_id": "12345",
        "tank_name": "Main Tank",
        "sensor_gallons": "200.0",  # +150 gallons
        "nominal": "275",
        "sensor_usg": "1.0",
    }

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=[tank_initial],
    ) as mock_get_tanks:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Runout date sensor should be valid (50 gal / 1.0 gal/day = 50 days)
        runout_state = hass.states.get("sensor.main_tank_estimated_runout_date")
        assert runout_state is not None
        assert runout_state.state != "unknown"

        # Refill sensors initially unknown
        refill_amount = hass.states.get("sensor.main_tank_last_refill_amount")
        assert refill_amount is not None
        assert refill_amount.state == "unknown"

        # Simulate update with refill
        mock_get_tanks.return_value = [tank_refilled]
        coordinator = entry.runtime_data.coordinator
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        refill_amount = hass.states.get("sensor.main_tank_last_refill_amount")
        assert refill_amount is not None
        assert refill_amount.state == "150.0"

        refill_date = hass.states.get("sensor.main_tank_last_refill_date")
        assert refill_date is not None
        assert refill_date.state != "unknown"


async def test_sensors_edge_case_numeric_exceptions(hass: HomeAssistant) -> None:
    """Test edge cases in numeric parsing for sensor metrics."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "test@example.com", "password": "test_password"},
    )
    entry.add_to_hass(hass)

    tank_edge_cases = {
        "tank_id": "12345",
        "tank_name": "Main Tank",
        "sensor_gallons": "100.0",
        "nominal": "invalid_nominal",
        "low_level": "invalid_low_level",
        "sensor_usg": "0.01",  # Below 0.05 limit for runout date
    }

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=[tank_edge_cases],
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Max level should be unknown due to invalid_nominal
        max_level_state = hass.states.get("sensor.main_tank_max_level")
        assert max_level_state is not None
        assert max_level_state.state == "unknown"

        # Days to quarter should be unknown due to low_level / nominal invalid
        days_quarter_state = hass.states.get("sensor.main_tank_days_to_1_4")
        assert days_quarter_state is not None
        assert days_quarter_state.state == "unknown"

        # Days to eighth should be unknown due to nominal invalid
        days_eighth_state = hass.states.get("sensor.main_tank_days_to_1_8")
        assert days_eighth_state is not None
        assert days_eighth_state.state == "unknown"

        # Runout date should be unknown due to usage <= 0.05
        runout_state = hass.states.get("sensor.main_tank_estimated_runout_date")
        assert runout_state is not None
        assert runout_state.state == "unknown"
