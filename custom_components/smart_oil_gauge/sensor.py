"""Support for Smart Oil Gauge sensors."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfVolume
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

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SmartOilGaugeSensorEntityDescription(SensorEntityDescription):
    """Class describing Smart Oil Gauge sensor entities."""

    value_fn: Callable[[dict[str, Any], SmartOilGaugeDataUpdateCoordinator], Any]
    icon_fn: Callable[[dict[str, Any]], str] | None = None


def _get_level_value(
    tank: dict[str, Any], coordinator: SmartOilGaugeDataUpdateCoordinator
) -> float | None:
    sensor_gallons = tank.get("sensor_gallons")
    model_gallons = tank.get("model_gallons")
    val = sensor_gallons if sensor_gallons is not None else model_gallons
    if val is None:
        return None
    res = parse_finite_float(val)
    if res is None:
        _LOGGER.warning("Could not convert level value '%s' to finite float", val)
    return res


def _get_percentage_value(
    tank: dict[str, Any], coordinator: SmartOilGaugeDataUpdateCoordinator
) -> float | None:
    sensor_gallons = tank.get("sensor_gallons")
    model_gallons = tank.get("model_gallons")
    val = sensor_gallons if sensor_gallons is not None else model_gallons
    nominal = tank.get("nominal")
    if val is None or nominal is None:
        return None
    gal_float = parse_finite_float(val)
    nominal_float = parse_finite_float(nominal)
    if gal_float is None or nominal_float is None or nominal_float <= 0:
        _LOGGER.warning(
            "Could not calculate percentage from level '%s' and capacity '%s'",
            val,
            nominal,
        )
        return None
    return round((gal_float / nominal_float) * 100.0, 1)


def _get_battery_value(
    tank: dict[str, Any], coordinator: SmartOilGaugeDataUpdateCoordinator
) -> str | None:
    battery = tank.get("battery")
    if battery is None:
        return None
    return str(battery)


def _get_battery_icon(tank: dict[str, Any]) -> str:
    battery = tank.get("battery")
    status = str(battery) if battery is not None else None
    if status in ("Excellent", "Good"):
        return "mdi:battery"
    if status == "Fair":
        return "mdi:battery-alert"
    if status == "Poor":
        return "mdi:battery-outline"
    return "mdi:battery-unknown"


def _get_daily_usage_value(
    tank: dict[str, Any], coordinator: SmartOilGaugeDataUpdateCoordinator
) -> float | None:
    usg = tank.get("sensor_usg")
    if usg is None:
        return None
    res = parse_finite_float(usg)
    if res is None:
        _LOGGER.warning("Could not convert daily usage rate '%s' to finite float", usg)
        return None
    return round(res, 2)


def _get_last_checked_value(
    tank: dict[str, Any], coordinator: SmartOilGaugeDataUpdateCoordinator
) -> datetime | None:
    return coordinator.last_successful_update


def _get_max_level_value(
    tank: dict[str, Any], coordinator: SmartOilGaugeDataUpdateCoordinator
) -> float | None:
    nominal = tank.get("nominal")
    if nominal is None:
        return None
    res = parse_finite_float(nominal)
    if res is None:
        _LOGGER.warning("Could not convert nominal value '%s' to finite float", nominal)
    return res


def _get_max_fill_value(
    tank: dict[str, Any], coordinator: SmartOilGaugeDataUpdateCoordinator
) -> float | None:
    sensor_gallons = tank.get("sensor_gallons")
    fillable = tank.get("fillable")
    if sensor_gallons is None or fillable is None:
        return None
    gal = parse_finite_float(sensor_gallons)
    fillable_val = parse_finite_float(fillable)
    if gal is None or fillable_val is None:
        _LOGGER.warning(
            "Could not calculate max fill from gallons %s and fillable %s",
            sensor_gallons,
            fillable,
        )
        return None
    return max(0.0, fillable_val - gal)


def _get_days_to_quarter_value(
    tank: dict[str, Any], coordinator: SmartOilGaugeDataUpdateCoordinator
) -> int | None:
    sensor_gallons = tank.get("sensor_gallons")
    usg = tank.get("sensor_usg")
    if sensor_gallons is None or usg is None:
        return None
    gal = parse_finite_float(sensor_gallons)
    daily_usage = parse_finite_float(usg)
    if gal is None or daily_usage is None or abs(daily_usage) < 0.2:
        return None
    nominal = parse_finite_float(tank.get("nominal") or 275)
    low_level = parse_finite_float(tank.get("low_level") or 0.25)
    if nominal is None or low_level is None:
        return None
    dtl = (gal - nominal * low_level) / daily_usage
    return max(0, round(dtl))


def _get_days_to_eighth_value(
    tank: dict[str, Any], coordinator: SmartOilGaugeDataUpdateCoordinator
) -> int | None:
    sensor_gallons = tank.get("sensor_gallons")
    usg = tank.get("sensor_usg")
    if sensor_gallons is None or usg is None:
        return None
    gal = parse_finite_float(sensor_gallons)
    daily_usage = parse_finite_float(usg)
    if gal is None or daily_usage is None or abs(daily_usage) < 0.2:
        return None
    nominal = parse_finite_float(tank.get("nominal") or 275)
    if nominal is None:
        return None
    dte = (gal - nominal * 0.125) / daily_usage
    return max(0, round(dte))


def _get_estimated_runout_date_value(
    tank: dict[str, Any], coordinator: SmartOilGaugeDataUpdateCoordinator
) -> datetime | None:
    sensor_gallons = tank.get("sensor_gallons")
    model_gallons = tank.get("model_gallons")
    val = sensor_gallons if sensor_gallons is not None else model_gallons
    usg = tank.get("sensor_usg")
    if val is None or usg is None:
        return None
    gal = parse_finite_float(val)
    daily_usage = parse_finite_float(usg)
    if gal is None or daily_usage is None or daily_usage <= 0.05:
        return None
    days_left = gal / daily_usage
    return dt_util.utcnow() + timedelta(days=days_left)


def _get_last_refill_amount_value(
    tank: dict[str, Any], coordinator: SmartOilGaugeDataUpdateCoordinator
) -> float | None:
    raw_id = tank.get("tank_id")
    if raw_id is None:
        return None
    tank_id = str(raw_id).strip()
    refill = coordinator.last_refills.get(tank_id)
    if not refill:
        return None
    return refill.get("amount")


def _get_last_refill_date_value(
    tank: dict[str, Any], coordinator: SmartOilGaugeDataUpdateCoordinator
) -> datetime | None:
    raw_id = tank.get("tank_id")
    if raw_id is None:
        return None
    tank_id = str(raw_id).strip()
    refill = coordinator.last_refills.get(tank_id)
    if not refill:
        return None
    return refill.get("timestamp")


SENSOR_TYPES: tuple[SmartOilGaugeSensorEntityDescription, ...] = (
    SmartOilGaugeSensorEntityDescription(
        key="oil_level",
        translation_key="oil_level",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        value_fn=_get_level_value,
    ),
    SmartOilGaugeSensorEntityDescription(
        key="oil_percentage",
        translation_key="oil_percentage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value_fn=_get_percentage_value,
    ),
    SmartOilGaugeSensorEntityDescription(
        key="battery",
        translation_key="battery",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_get_battery_value,
        icon_fn=_get_battery_icon,
    ),
    SmartOilGaugeSensorEntityDescription(
        key="daily_usage_rate",
        translation_key="daily_usage_rate",
        native_unit_of_measurement="gal/day",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
        value_fn=_get_daily_usage_value,
    ),
    SmartOilGaugeSensorEntityDescription(
        key="last_checked",
        translation_key="last_portal_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-outline",
        value_fn=_get_last_checked_value,
    ),
    SmartOilGaugeSensorEntityDescription(
        key="max_level",
        translation_key="max_level",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge-full",
        value_fn=_get_max_level_value,
    ),
    SmartOilGaugeSensorEntityDescription(
        key="max_fill",
        translation_key="max_fill",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge-empty",
        value_fn=_get_max_fill_value,
    ),
    SmartOilGaugeSensorEntityDescription(
        key="days_to_quarter",
        translation_key="days_to_quarter",
        native_unit_of_measurement="days",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-clock",
        value_fn=_get_days_to_quarter_value,
    ),
    SmartOilGaugeSensorEntityDescription(
        key="days_to_eighth",
        translation_key="days_to_eighth",
        native_unit_of_measurement="days",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-clock",
        value_fn=_get_days_to_eighth_value,
    ),
    SmartOilGaugeSensorEntityDescription(
        key="estimated_runout_date",
        translation_key="estimated_runout_date",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-alert",
        value_fn=_get_estimated_runout_date_value,
    ),
    SmartOilGaugeSensorEntityDescription(
        key="last_refill_amount",
        translation_key="last_refill_amount",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fuel",
        value_fn=_get_last_refill_amount_value,
    ),
    SmartOilGaugeSensorEntityDescription(
        key="last_refill_date",
        translation_key="last_refill_date",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-check",
        value_fn=_get_last_refill_date_value,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartOilGaugeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Oil Gauge sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator

    known_tank_ids: set[str] = set()

    @callback
    def _async_add_entities_for_tanks() -> None:
        if not coordinator.data:
            return

        new_entities: list[SensorEntity] = []
        for tank_id, tank in coordinator.data.items():
            if tank_id in known_tank_ids:
                continue
            known_tank_ids.add(tank_id)
            tank_name = tank.get("tank_name", "Oil Tank")

            _LOGGER.debug("Setting up sensors for tank %s (%s)", tank_name, tank_id)
            for description in SENSOR_TYPES:
                new_entities.append(
                    SmartOilGaugeSensor(coordinator, tank_id, tank_name, description)
                )

        if new_entities:
            async_add_entities(new_entities)

    _async_add_entities_for_tanks()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_entities_for_tanks))


class SmartOilGaugeSensor(SmartOilGaugeEntity, SensorEntity):
    """Representation of a Smart Oil Gauge sensor."""

    entity_description: SmartOilGaugeSensorEntityDescription

    def __init__(
        self,
        coordinator: SmartOilGaugeDataUpdateCoordinator,
        tank_id: str,
        tank_name: str,
        description: SmartOilGaugeSensorEntityDescription,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, tank_id, tank_name)
        self.entity_description = description
        self._attr_unique_id = f"{tank_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        tank = self._get_tank_data()
        if not tank:
            return None
        return self.entity_description.value_fn(tank, self.coordinator)

    @property
    def icon(self) -> str | None:
        """Return dynamic or static icon."""
        tank = self._get_tank_data()
        if self.entity_description.icon_fn and tank:
            return self.entity_description.icon_fn(tank)
        return self.entity_description.icon
