"""Placeholder binary_sensor platform for Smart Oil Gauge."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up binary_sensor platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    # Setup Low Fuel alert binary sensors dynamically per tank
    if not coordinator.data:
        return

    entities: list[BinarySensorEntity] = []
    for tank in coordinator.data:
        tank_id = str(tank.get("tank_id"))
        tank_name = tank.get("tank_name", "Oil Tank")
        entities.append(
            SmartOilGaugeLowFuelBinarySensor(coordinator, tank_id, tank_name)
        )

    async_add_entities(entities)


class SmartOilGaugeLowFuelBinarySensor(SmartOilGaugeEntity, BinarySensorEntity):
    """Low fuel alert binary sensor representation."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: SmartOilGaugeDataUpdateCoordinator,
        tank_id: str,
        tank_name: str,
    ) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator, tank_id, tank_name)
        self._attr_name = "Low Fuel Alert"
        self._attr_unique_id = f"{tank_id}_low_fuel_alert"

    @property
    def is_on(self) -> bool | None:
        """Return true if fuel level is below low threshold."""
        tank = self._get_tank_data()
        if not tank:
            return None

        try:
            gal_str = tank.get("sensor_gallons") or tank.get("model_gallons")
            if gal_str is None:
                return None
            gal = float(gal_str)
            nominal = float(tank.get("nominal") or 1)
            low_level = float(tank.get("low_level") or 0.25)
            if nominal <= 0:
                return None
            return (gal / nominal) < low_level
        except ValueError:
            return None
