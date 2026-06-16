"""Support for Smart Oil Gauge sensors."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SmartOilGaugeDataUpdateCoordinator
from .entity import SmartOilGaugeEntity

_LOGGER = logging.getLogger(__name__)

# Fallback compatibility for older Home Assistant versions
try:
    from homeassistant.const import UnitOfVolume

    GALLONS = UnitOfVolume.GALLONS
except ImportError:
    GALLONS = "gal"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Oil Gauge sensors from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    if not coordinator.data:
        _LOGGER.warning("No tank data found to set up sensors")
        return

    entities: list[SensorEntity] = []
    for tank in coordinator.data:
        tank_id = str(tank.get("tank_id"))
        tank_name = tank.get("tank_name", "Oil Tank")

        _LOGGER.debug("Setting up sensors for tank %s (%s)", tank_name, tank_id)
        entities.extend(
            [
                SmartOilGaugeLevelSensor(coordinator, tank_id, tank_name),
                SmartOilGaugePercentageSensor(coordinator, tank_id, tank_name),
                SmartOilGaugeBatterySensor(coordinator, tank_id, tank_name),
                SmartOilGaugeDailyUsageRateSensor(coordinator, tank_id, tank_name),
                SmartOilGaugeLastCheckedSensor(coordinator, tank_id, tank_name),
            ]
        )

    async_add_entities(entities)


class SmartOilGaugeLevelSensor(SmartOilGaugeEntity, SensorEntity):
    """Sensor for remaining gallons of oil."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = GALLONS
    _attr_icon = "mdi:gauge"

    def __init__(
        self,
        coordinator: SmartOilGaugeDataUpdateCoordinator,
        tank_id: str,
        tank_name: str,
    ) -> None:
        """Initialize level sensor."""
        super().__init__(coordinator, tank_id, tank_name)
        self._attr_name = "Oil Level"
        self._attr_unique_id = f"{tank_id}_oil_level"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        tank = self._get_tank_data()
        if not tank:
            return None

        # Prefer physical sensor reading, fall back to model estimation
        sensor_gallons = tank.get("sensor_gallons")
        model_gallons = tank.get("model_gallons")

        val = sensor_gallons if sensor_gallons is not None else model_gallons
        if val is None:
            return None

        try:
            return float(val)
        except ValueError:
            _LOGGER.warning("Could not convert level value '%s' to float", val)
            return None


class SmartOilGaugePercentageSensor(SmartOilGaugeEntity, SensorEntity):
    """Sensor for oil tank percentage fill."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:water-percent"

    def __init__(
        self,
        coordinator: SmartOilGaugeDataUpdateCoordinator,
        tank_id: str,
        tank_name: str,
    ) -> None:
        """Initialize percentage sensor."""
        super().__init__(coordinator, tank_id, tank_name)
        self._attr_name = "Oil Percentage"
        self._attr_unique_id = f"{tank_id}_oil_percentage"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        tank = self._get_tank_data()
        if not tank:
            return None

        sensor_gallons = tank.get("sensor_gallons")
        model_gallons = tank.get("model_gallons")

        val = sensor_gallons if sensor_gallons is not None else model_gallons
        nominal = tank.get("nominal")

        if val is None or not nominal:
            return None

        try:
            gal_float = float(val)
            nominal_float = float(nominal)
            if nominal_float <= 0:
                return None
            return round((gal_float / nominal_float) * 100.0, 1)
        except ValueError:
            _LOGGER.warning(
                "Could not calculate percentage from level '%s' and capacity '%s'",
                val,
                nominal,
            )
            return None


class SmartOilGaugeBatterySensor(SmartOilGaugeEntity, SensorEntity):
    """Sensor for gauge battery status."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: SmartOilGaugeDataUpdateCoordinator,
        tank_id: str,
        tank_name: str,
    ) -> None:
        """Initialize battery sensor."""
        super().__init__(coordinator, tank_id, tank_name)
        self._attr_name = "Battery"
        self._attr_unique_id = f"{tank_id}_battery"

    @property
    def native_value(self) -> str | None:
        """Return the battery status string."""
        tank = self._get_tank_data()
        if not tank:
            return None

        battery = tank.get("battery")
        if battery is None:
            return None
        return str(battery)

    @property
    def icon(self) -> str:
        """Return dynamic battery icon based on status."""
        status = self.native_value
        if status in ("Excellent", "Good"):
            return "mdi:battery"
        if status == "Fair":
            return "mdi:battery-alert"
        if status == "Poor":
            return "mdi:battery-outline"
        return "mdi:battery-unknown"


class SmartOilGaugeDailyUsageRateSensor(SmartOilGaugeEntity, SensorEntity):
    """Sensor for daily oil usage rate (rolling average)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-line"

    def __init__(
        self,
        coordinator: SmartOilGaugeDataUpdateCoordinator,
        tank_id: str,
        tank_name: str,
    ) -> None:
        """Initialize daily usage rate sensor."""
        super().__init__(coordinator, tank_id, tank_name)
        self._attr_name = "Daily Usage Rate"
        self._attr_unique_id = f"{tank_id}_daily_usage_rate"
        self._attr_native_unit_of_measurement = "gal/day"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        tank = self._get_tank_data()
        if not tank:
            return None

        usg = tank.get("sensor_usg")
        if usg is None:
            return None

        try:
            return round(float(usg), 2)
        except ValueError:
            _LOGGER.warning("Could not convert daily usage rate '%s' to float", usg)
            return None


class SmartOilGaugeLastCheckedSensor(SmartOilGaugeEntity, SensorEntity):
    """Sensor for the last time the gauge was successfully checked."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        coordinator: SmartOilGaugeDataUpdateCoordinator,
        tank_id: str,
        tank_name: str,
    ) -> None:
        """Initialize last checked sensor."""
        super().__init__(coordinator, tank_id, tank_name)
        self._attr_name = "Last Checked"
        self._attr_unique_id = f"{tank_id}_last_checked"

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        return self.coordinator.last_successful_update
