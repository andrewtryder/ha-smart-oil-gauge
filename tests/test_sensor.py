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
