"""Binary sensor platform for Smart Oil Gauge."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import (
    SmartOilGaugeConfigEntry,
    SmartOilGaugeDataUpdateCoordinator,
)
from .entity import SmartOilGaugeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartOilGaugeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary_sensor platform."""
    coordinator = entry.runtime_data.coordinator

    known_tank_ids: set[str] = set()

    @callback
    def _async_add_entities_for_tanks() -> None:
        if not coordinator.data:
            return

        new_entities: list[BinarySensorEntity] = []
        for tank_id, tank in coordinator.data.items():
            if tank_id in known_tank_ids:
                continue
            known_tank_ids.add(tank_id)
            tank_name = tank.get("tank_name", "Oil Tank")
            new_entities.append(
                SmartOilGaugeLowFuelBinarySensor(coordinator, tank_id, tank_name)
            )

        if new_entities:
            async_add_entities(new_entities)

    _async_add_entities_for_tanks()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_entities_for_tanks))


class SmartOilGaugeLowFuelBinarySensor(SmartOilGaugeEntity, BinarySensorEntity):
    """Low fuel alert binary sensor representation."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "low_fuel_alert"

    def __init__(
        self,
        coordinator: SmartOilGaugeDataUpdateCoordinator,
        tank_id: str,
        tank_name: str,
    ) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator, tank_id, tank_name)
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
