"""Base SmartOilGaugeEntity class."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmartOilGaugeDataUpdateCoordinator


class SmartOilGaugeEntity(CoordinatorEntity[SmartOilGaugeDataUpdateCoordinator]):
    """Base class for Smart Oil Gauge entities."""

    def __init__(
        self,
        coordinator: SmartOilGaugeDataUpdateCoordinator,
        tank_id: str,
        tank_name: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.tank_id = tank_id
        self.tank_name = tank_name
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry info for this tank."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.tank_id)},
            name=self.tank_name,
            manufacturer="Connected Consumer Fuel",
            model="Smart Oil Gauge",
        )

    def _get_tank_data(self) -> dict[str, Any] | None:
        """Retrieve this entity's tank data from coordinator updates."""
        if not self.coordinator.data:
            return None
        return next(
            (
                tank
                for tank in self.coordinator.data
                if str(tank.get("tank_id")) == self.tank_id
            ),
            None,
        )
