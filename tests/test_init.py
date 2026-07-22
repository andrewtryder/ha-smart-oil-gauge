"""Tests for Smart Oil Gauge integration lifecycle setup and unload."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_oil_gauge.client import (
    CannotConnect,
    InvalidAuth,
    SmartOilGaugeException,
)
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


async def test_setup_unload_entry(hass: HomeAssistant) -> None:
    """Test setting up and unloading the config entry."""
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
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Check if the entry is loaded successfully
        assert entry.state is ConfigEntryState.LOADED
        assert entry.runtime_data is not None

        coordinator = entry.runtime_data.coordinator
        assert list(coordinator.data.values()) == MOCK_TANK_DATA

        # Test unloading
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize(
    ("exception", "expected_state"),
    [
        (CannotConnect("Connection failed"), ConfigEntryState.SETUP_RETRY),
        (InvalidAuth("Auth failed"), ConfigEntryState.SETUP_ERROR),
        (SmartOilGaugeException("Unknown API error"), ConfigEntryState.SETUP_RETRY),
    ],
)
async def test_setup_entry_failures(
    hass: HomeAssistant, exception: Exception, expected_state: ConfigEntryState
) -> None:
    """Test setup errors inside coordinator update."""
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
        side_effect=exception,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is expected_state
