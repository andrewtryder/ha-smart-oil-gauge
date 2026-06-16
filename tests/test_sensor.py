"""Tests for Smart Oil Gauge sensor entities."""

from unittest.mock import patch

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

        # Check Last Checked Sensor
        last_checked_state = hass.states.get("sensor.main_house_tank_last_checked")
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
