"""Tests for Smart Oil Gauge update coordinator."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import async_get as async_get_issue_registry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_oil_gauge.client import CannotConnect
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

        # Initially no repair issue
        assert issue_registry.async_get_issue(DOMAIN, "api_breakage") is None

        # Simulate API breakage
        mock_get_tanks.side_effect = CannotConnect(
            "CSRF token ccf_nonce not found in page HTML"
        )
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # Issue created
        assert issue_registry.async_get_issue(DOMAIN, "api_breakage") is not None

        # Simulate recovery
        mock_get_tanks.side_effect = None
        mock_get_tanks.return_value = MOCK_TANK_DATA
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # Issue resolved/deleted
        assert issue_registry.async_get_issue(DOMAIN, "api_breakage") is None
