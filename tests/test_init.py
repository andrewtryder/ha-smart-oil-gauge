"""Tests for Smart Oil Gauge integration lifecycle setup, unload, and removal."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_oil_gauge import (
    async_remove_entry,
    async_setup_entry,
)
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

        client = entry.runtime_data.client
        client.async_close = AsyncMock()

        coordinator = entry.runtime_data.coordinator
        assert list(coordinator.data.values()) == MOCK_TANK_DATA

        # Test unloading closes client session
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED
        assert client.async_close.called


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

    with (
        patch(
            "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
            side_effect=exception,
        ),
        patch(
            "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_close",
            new_callable=AsyncMock,
        ) as mock_close,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is expected_state
        assert mock_close.called


async def test_setup_entry_cancelled(hass: HomeAssistant) -> None:
    """Test setup cancellation triggers client.async_close."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "test@example.com",
            "password": "test_password",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.smart_oil_gauge.coordinator.SmartOilGaugeDataUpdateCoordinator.async_config_entry_first_refresh",
            side_effect=asyncio.CancelledError,
        ),
        patch(
            "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_close",
            new_callable=AsyncMock,
        ) as mock_close,
    ):
        with pytest.raises(asyncio.CancelledError):
            await async_setup_entry(hass, entry)

        assert mock_close.called


async def test_remove_entry(hass: HomeAssistant) -> None:
    """Test removing an entry cleans up storage file and repair issue."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "test@example.com",
            "password": "test_password",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "homeassistant.helpers.storage.Store.async_remove", new_callable=AsyncMock
        ) as mock_remove_store,
        patch(
            "custom_components.smart_oil_gauge.async_delete_issue"
        ) as mock_delete_issue,
    ):
        await async_remove_entry(hass, entry)
        assert mock_remove_store.called
        mock_delete_issue.assert_called_once_with(
            hass, DOMAIN, f"api_breakage_{entry.entry_id}"
        )
