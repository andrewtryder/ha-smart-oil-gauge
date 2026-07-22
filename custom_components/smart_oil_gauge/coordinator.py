"""DataUpdateCoordinator for Smart Oil Gauge."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
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


@dataclass
class SmartOilGaugeData:
    """Data stored in ConfigEntry.runtime_data."""

    client: SmartOilGaugeClient
    coordinator: SmartOilGaugeDataUpdateCoordinator


type SmartOilGaugeConfigEntry = ConfigEntry[SmartOilGaugeData]


class SmartOilGaugeDataUpdateCoordinator(
    DataUpdateCoordinator[dict[str, dict[str, Any]]]
):
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
        self._previous_levels: dict[str, float] = {}
        self.last_refills: dict[str, dict[str, Any]] = {}
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=update_interval_hours),
        )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Update data via client."""
        try:
            # Fetch tanks list. The client handles automatic login
            # and retries if needed.
            data = await self.client.async_get_tanks()
            self.last_successful_update = dt_util.utcnow()
            async_delete_issue(self.hass, DOMAIN, "api_breakage")

            tanks_dict: dict[str, dict[str, Any]] = {}
            for tank in data:
                tank_id = str(tank["tank_id"])
                tanks_dict[tank_id] = tank
                self._check_refill(tank_id, tank)

            return tanks_dict
        except CannotConnect as err:
            if "not found" in str(err).lower() or "invalid json" in str(err).lower():
                self._raise_api_breakage_issue()
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(f"Authentication error: {err}") from err
        except SmartOilGaugeException as err:
            self._raise_api_breakage_issue()
            raise UpdateFailed(f"Error fetching data: {err}") from err

    def _check_refill(self, tank_id: str, tank: dict[str, Any]) -> None:
        """Detect upward level changes indicating a refill."""
        gal_str = tank.get("sensor_gallons") or tank.get("model_gallons")
        if gal_str is None:
            return

        try:
            current_level = float(gal_str)
        except ValueError:
            return

        if tank_id in self._previous_levels:
            prev_level = self._previous_levels[tank_id]
            diff = current_level - prev_level
            if diff >= 15.0:
                _LOGGER.info(
                    "Refill detected for tank %s: %.1f gallons added", tank_id, diff
                )
                self.last_refills[tank_id] = {
                    "amount": round(diff, 1),
                    "timestamp": dt_util.utcnow(),
                }

        self._previous_levels[tank_id] = current_level

    def _raise_api_breakage_issue(self) -> None:
        """Raise a Home Assistant repair issue for API structure breakage."""
        async_create_issue(
            self.hass,
            DOMAIN,
            "api_breakage",
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=IssueSeverity.ERROR,
            translation_key="api_breakage",
        )
