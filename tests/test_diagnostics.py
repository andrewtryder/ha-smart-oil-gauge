"""Tests for Smart Oil Gauge diagnostics."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_oil_gauge.const import DOMAIN
from custom_components.smart_oil_gauge.diagnostics import (
    async_get_config_entry_diagnostics,
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


async def test_async_get_config_entry_diagnostics(hass: HomeAssistant) -> None:
    """Test diagnostics output generation and redaction."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "test@example.com",
            "password": "secret_password",
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=MOCK_TANK_DATA,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        diag = await async_get_config_entry_diagnostics(hass, entry)

        assert diag["entry"]["data"]["password"] == "**REDACTED**"
        assert diag["entry"]["data"]["username"] == "**REDACTED**"
        assert diag["tanks_count"] == 1
        assert "12345" in diag["tanks"]
        assert diag["tanks"]["12345"]["tank_name"] == "Main House Tank"
