"""Upload interval select for the Smart Oil Gauge integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import SmartOilGaugeException
from .const import DOMAIN
from .coordinator import SmartOilGaugeConfigEntry
from .entity import SmartOilGaugeEntity

PARALLEL_UPDATES = 1
OPTIONS = [str(h) for h in range(1, 25)]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartOilGaugeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the upload interval select for each tank.

    Only when the experimental option to change the interval is turned on.
    """
    coordinator = entry.runtime_data.coordinator
    if not coordinator.allow_interval_change:
        return
    known: set[str] = set()

    @callback
    def _add() -> None:
        new = []
        for tank_id, tank in (coordinator.data or {}).items():
            if tank_id in known or coordinator.active_registration_id(tank) is None:
                continue
            known.add(tank_id)
            new.append(
                SmartOilGaugeUploadIntervalSelect(
                    coordinator, tank_id, tank.get("tank_name", "Oil Tank")
                )
            )
        if new:
            async_add_entities(new)

    _add()
    entry.async_on_unload(coordinator.async_add_listener(_add))


class SmartOilGaugeUploadIntervalSelect(SmartOilGaugeEntity, SelectEntity):
    """The gauge's upload interval in hours, as set on the portal.

    The gauge picks up a new interval at its next upload, so a change shows
    as pending until then.
    """

    _attr_translation_key = "upload_interval"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:timer-cog-outline"
    _attr_options = OPTIONS
    _attr_unit_of_measurement = "h"

    def __init__(self, coordinator, tank_id: str, tank_name: str) -> None:
        """Initialize the select."""
        super().__init__(coordinator, tank_id, tank_name)
        self._attr_unique_id = f"{tank_id}_upload_interval"

    @property
    def current_option(self) -> str | None:
        """The interval currently set on the portal."""
        sched = self.coordinator.schedules.get(self.tank_id)
        if sched is None or sched.configured_h is None:
            return None
        return str(sched.configured_h)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """What the gauge is using now, and whether a change is pending."""
        sched = self.coordinator.schedules.get(self.tank_id)
        if sched is None:
            return None
        hours, source = sched.interval()
        return {
            "effective_interval_hours": round(hours, 2) if hours else None,
            "pending": sched.pending,
            "interval_source": source,
            "number_of_tanks": sched.num_tanks,
        }

    async def async_select_option(self, option: str) -> None:
        """Change the upload interval on the portal."""
        try:
            await self.coordinator.async_set_upload_interval(self.tank_id, int(option))
        except SmartOilGaugeException as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_interval_failed",
                translation_placeholders={"error": str(err)},
            ) from err
