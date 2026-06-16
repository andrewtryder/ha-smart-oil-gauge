"""The Smart Oil Gauge integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .client import SmartOilGaugeClient
from .const import DOMAIN, USER_AGENT
from .coordinator import SmartOilGaugeDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Oil Gauge from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_create_clientsession(hass, headers={"User-Agent": USER_AGENT})
    client = SmartOilGaugeClient(
        session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )

    coordinator = SmartOilGaugeDataUpdateCoordinator(hass, client)

    # Initial data fetch during setup
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
