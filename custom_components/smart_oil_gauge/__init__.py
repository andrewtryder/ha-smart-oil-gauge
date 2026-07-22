"""The Smart Oil Gauge integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .client import SmartOilGaugeClient
from .const import (
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    USER_AGENT,
)
from .coordinator import (
    SmartOilGaugeConfigEntry,
    SmartOilGaugeData,
    SmartOilGaugeDataUpdateCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(
    hass: HomeAssistant, entry: SmartOilGaugeConfigEntry
) -> bool:
    """Set up Smart Oil Gauge from a config entry."""
    session = async_create_clientsession(hass, headers={"User-Agent": USER_AGENT})
    client = SmartOilGaugeClient(
        session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )

    update_interval_hours = entry.options.get(
        CONF_UPDATE_INTERVAL_HOURS,
        entry.data.get(CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS),
    )

    coordinator = SmartOilGaugeDataUpdateCoordinator(
        hass, client, update_interval_hours, entry.entry_id
    )

    try:
        # Initial data fetch during setup
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = SmartOilGaugeData(client=client, coordinator=coordinator)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await client.async_close()
        raise

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SmartOilGaugeConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.async_close()
    return unload_ok
