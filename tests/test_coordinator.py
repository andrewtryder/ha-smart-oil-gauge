"""Tests for Smart Oil Gauge update coordinator."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import async_get as async_get_issue_registry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_oil_gauge.client import CannotConnect
from custom_components.smart_oil_gauge.const import DOMAIN
from custom_components.smart_oil_gauge.coordinator import (
    SmartOilGaugeDataUpdateCoordinator,
)

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


async def test_coordinator_api_breakage_issue(hass: HomeAssistant) -> None:
    """Test repair issue creation on API breakage and deletion on recovery."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "test@example.com",
            "password": "test_password",
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=MOCK_TANK_DATA,
    ) as mock_get_tanks:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator = entry.runtime_data.coordinator
        issue_registry = async_get_issue_registry(hass)
        issue_id = f"api_breakage_{entry.entry_id}"

        # Initially no repair issue
        assert issue_registry.async_get_issue(DOMAIN, issue_id) is None

        # Simulate API breakage
        mock_get_tanks.side_effect = CannotConnect(
            "CSRF token ccf_nonce not found in page HTML"
        )
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # Entry-scoped repair issue created
        assert issue_registry.async_get_issue(DOMAIN, issue_id) is not None

        # Simulate recovery
        mock_get_tanks.side_effect = None
        mock_get_tanks.return_value = MOCK_TANK_DATA
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # Issue resolved/deleted
        assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_coordinator_refill_persistence_and_mode_check(
    hass: HomeAssistant,
) -> None:
    """Test persistent storage loading/saving and mode-aware refill detection."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "test@example.com",
            "password": "test_password",
        },
    )
    entry.add_to_hass(hass)

    tank_sensor_low = {
        "tank_id": "12345",
        "sensor_gallons": "50.0",
        "nominal": "275",
    }
    tank_model_high = {
        "tank_id": "12345",
        "sensor_gallons": None,
        "model_gallons": "150.0",  # Jump from 50 -> 150 but different mode
        "nominal": "275",
    }
    tank_sensor_refilled = {
        "tank_id": "12345",
        "sensor_gallons": "200.0",  # Jump from 50 -> 200 in same mode
        "nominal": "275",
    }

    client_mock = patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks"
    )
    with client_mock as mock_get_tanks:
        mock_get_tanks.return_value = [tank_sensor_low]
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator = entry.runtime_data.coordinator

        # Switch to model mode: should NOT trigger refill
        mock_get_tanks.return_value = [tank_model_high]
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert "12345" not in coordinator.last_refills

        # Switch back to sensor mode with real refill: should trigger refill
        mock_get_tanks.return_value = [tank_sensor_refilled]
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        assert "12345" in coordinator.last_refills
        assert coordinator.last_refills["12345"]["amount"] == 150.0

        # Create new coordinator instance to verify storage persistence
        new_coordinator = SmartOilGaugeDataUpdateCoordinator(
            hass, entry.runtime_data.client, 6, entry.entry_id
        )
        await new_coordinator._async_load_storage()
        assert "12345" in new_coordinator.last_refills
        assert new_coordinator.last_refills["12345"]["amount"] == 150.0
