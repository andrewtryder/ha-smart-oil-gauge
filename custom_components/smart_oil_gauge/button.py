"""Buttons for the Smart Oil Gauge integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SmartOilGaugeConfigEntry
from .entity import SmartOilGaugeEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartOilGaugeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Import history button for each tank."""
    coordinator = entry.runtime_data.coordinator
    known_tank_ids: set[str] = set()

    @callback
    def _async_add_entities_for_tanks() -> None:
        if not coordinator.data:
            return
        new_entities: list[ButtonEntity] = []
        for tank_id, tank in coordinator.data.items():
            if tank_id in known_tank_ids:
                continue
            known_tank_ids.add(tank_id)
            new_entities.append(
                SmartOilGaugeImportHistoryButton(
                    coordinator, tank_id, tank.get("tank_name", "Oil Tank")
                )
            )
        if new_entities:
            async_add_entities(new_entities)

    _async_add_entities_for_tanks()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_entities_for_tanks))


class SmartOilGaugeImportHistoryButton(SmartOilGaugeEntity, ButtonEntity):
    """Re-import the tank's full hourly history from the portal."""

    _attr_translation_key = "import_history"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:database-import"

    def __init__(self, coordinator, tank_id: str, tank_name: str) -> None:
        """Initialize the button."""
        super().__init__(coordinator, tank_id, tank_name)
        self._attr_unique_id = f"{tank_id}_import_history"

    async def async_press(self) -> None:
        """Start the import in the background."""
        coordinator = self.coordinator
        coordinator.config_entry.async_create_background_task(
            self.hass,
            coordinator.async_import_history(self.tank_id),
            f"smart_oil_gauge import history {self.tank_id}",
        )
