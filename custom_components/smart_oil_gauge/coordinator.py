"""DataUpdateCoordinator for Smart Oil Gauge."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import (
    CannotConnect,
    InvalidAuth,
    SmartOilGaugeClient,
    SmartOilGaugeException,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class SmartOilGaugeDataUpdateCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Class to manage fetching Smart Oil Gauge data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SmartOilGaugeClient,
        update_interval_hours: int,
    ) -> None:
        """Initialize."""
        self.client = client
        self.last_successful_update = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=update_interval_hours),
        )


    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Update data via client."""
        try:
            # Fetch tanks list. The client handles automatic login
            # and retries if needed.
            data = await self.client.async_get_tanks()
            self.last_successful_update = dt_util.utcnow()
            return data
        except CannotConnect as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except InvalidAuth as err:
            raise UpdateFailed(f"Authentication error: {err}") from err
        except SmartOilGaugeException as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err
