"""Switch platform skeleton for Smart Oil Gauge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SmartOilGaugeDataUpdateCoordinator
from .entity import SmartOilGaugeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    # Since Smart Oil Gauge is read-only, we do not register any switches.
    # This remains as a skeleton class definition to adhere to the blueprint template.
    _ = coordinator  # Unused
    _ = async_add_entities  # Unused


class SmartOilGaugeSwitch(SmartOilGaugeEntity, SwitchEntity):
    """Example switch representation."""

    def __init__(
        self,
        coordinator: SmartOilGaugeDataUpdateCoordinator,
        tank_id: str,
        tank_name: str,
    ) -> None:
        """Initialize switch."""
        super().__init__(coordinator, tank_id, tank_name)
        self._attr_name = "Virtual Toggle"
        self._attr_unique_id = f"{tank_id}_virtual_toggle"
        self._is_on = False

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        self._is_on = False
        self.async_write_ha_state()
