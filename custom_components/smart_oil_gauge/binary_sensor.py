"""Binary sensor platform for Smart Oil Gauge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import (
    SmartOilGaugeConfigEntry,
    SmartOilGaugeDataUpdateCoordinator,
)
from .entity import SmartOilGaugeEntity
from .util import parse_finite_float

PARALLEL_UPDATES = 0


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
            if coordinator.active_registration_id(tank) is not None:
                new_entities.append(
                    SmartOilGaugeIntervalPendingBinarySensor(
                        coordinator, tank_id, tank_name
                    )
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

        gal_val = tank.get("sensor_gallons")
        if gal_val is None:
            gal_val = tank.get("model_gallons")
        if gal_val is None:
            return None
        gal = parse_finite_float(gal_val)
        nominal = parse_finite_float(tank.get("nominal") or 1)
        low_level = parse_finite_float(tank.get("low_level") or 0.25)
        if gal is None or nominal is None or low_level is None or nominal <= 0:
            return None
        return (gal / nominal) < low_level


class SmartOilGaugeIntervalPendingBinarySensor(SmartOilGaugeEntity, BinarySensorEntity):
    """On while a new upload interval waits for the gauge's next upload.

    The gauge only fetches its settings when it uploads, so a change made on
    the portal (or from Home Assistant) is not used until then.
    """

    _attr_translation_key = "upload_interval_pending"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator, tank_id: str, tank_name: str) -> None:
        """Initialize."""
        super().__init__(coordinator, tank_id, tank_name)
        self._attr_unique_id = f"{tank_id}_upload_interval_pending"

    @property
    def is_on(self) -> bool | None:
        """True while the portal setting differs from the one in use."""
        sched = self.coordinator.schedules.get(self.tank_id)
        return sched.pending if sched else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """The interval set on the portal and the one the gauge uses now."""
        sched = self.coordinator.schedules.get(self.tank_id)
        if sched is None:
            return None
        return {
            "portal_interval_hours": sched.configured_h,
            "gauge_interval_hours": sched.effective_h,
            "pending_since": dt_util.utc_from_timestamp(sched.pending_since).isoformat()
            if sched.pending_since
            else None,
        }
