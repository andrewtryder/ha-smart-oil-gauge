"""Tests for Smart Oil Gauge binary sensor entities."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_oil_gauge.const import DOMAIN

MOCK_TANK_DATA_LOW = [
    {
        "tank_id": "12345",
        "tank_name": "Main House Tank",
        "sensor_gallons": "50.0",  # 50 / 275 = 0.18 < 0.25 (low level ratio)
        "nominal": "275",
        "low_level": "0.25",
        "battery": "Excellent",
        "sensor_usg": "0.85",
    }
]

MOCK_TANK_DATA_NORMAL = [
    {
        "tank_id": "12345",
        "tank_name": "Main House Tank",
        "sensor_gallons": "200.0",  # 200 / 275 = 0.72 > 0.25
        "nominal": "275",
        "low_level": "0.25",
        "battery": "Excellent",
        "sensor_usg": "0.85",
    }
]


async def test_binary_sensors_low_fuel(hass: HomeAssistant) -> None:
    """Test low fuel binary sensor turns ON when fuel is low."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "test@example.com", "password": "test_password"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=MOCK_TANK_DATA_LOW,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("binary_sensor.main_house_tank_low_fuel_alert")
        assert state is not None
        assert state.state == "on"


async def test_binary_sensors_normal_fuel(hass: HomeAssistant) -> None:
    """Test low fuel binary sensor stays OFF when fuel is normal."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "test@example.com", "password": "test_password"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=MOCK_TANK_DATA_NORMAL,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("binary_sensor.main_house_tank_low_fuel_alert")
        assert state is not None
        assert state.state == "off"
