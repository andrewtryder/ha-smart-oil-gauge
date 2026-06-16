"""Tests for Smart Oil Gauge switch entities."""

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant

from custom_components.smart_oil_gauge.coordinator import (
    SmartOilGaugeDataUpdateCoordinator,
)
from custom_components.smart_oil_gauge.switch import SmartOilGaugeSwitch


async def test_switch_toggle(hass: HomeAssistant) -> None:
    """Test switch toggle methods directly."""
    coordinator = MagicMock(spec=SmartOilGaugeDataUpdateCoordinator)
    coordinator.data = []

    switch = SmartOilGaugeSwitch(coordinator, "12345", "Test Tank")
    assert switch.name == "Virtual Toggle"
    assert switch.unique_id == "12345_virtual_toggle"
    assert switch.is_on is False

    # Mock async_write_ha_state
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_on()
    assert switch.is_on is True
    assert switch.async_write_ha_state.call_count == 1

    await switch.async_turn_off()
    assert switch.is_on is False
    assert switch.async_write_ha_state.call_count == 2
