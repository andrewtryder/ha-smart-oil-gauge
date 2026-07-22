"""DataUpdateCoordinator for Smart Oil Gauge."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.storage import Store
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
STORAGE_VERSION = 1


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
        entry_id: str = "default",
    ) -> None:
        """Initialize."""
        self.client = client
        self.entry_id = entry_id
        self.issue_id = f"api_breakage_{entry_id}"
        self.last_successful_update: datetime | None = None
        self._previous_levels: dict[str, dict[str, float]] = {}
        self.last_refills: dict[str, dict[str, Any]] = {}
        self._store = Store(hass, STORAGE_VERSION, f"smart_oil_gauge_{entry_id}")
        self._storage_loaded = False

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=update_interval_hours),
        )

    async def _async_load_storage(self) -> None:
        """Load stored refill state and previous levels."""
        if self._storage_loaded:
            return
        self._storage_loaded = True
        try:
            stored = await self._store.async_load()
            if isinstance(stored, dict):
                self._previous_levels = stored.get("previous_levels", {})
                raw_refills = stored.get("last_refills", {})
                for tank_id, refill in raw_refills.items():
                    if isinstance(refill, dict) and "amount" in refill:
                        ts_str = refill.get("timestamp")
                        ts = (
                            dt_util.parse_datetime(ts_str)
                            if isinstance(ts_str, str)
                            else None
                        )
                        self.last_refills[tank_id] = {
                            "amount": refill["amount"],
                            "timestamp": ts or dt_util.utcnow(),
                        }
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.warning("Could not load persistent storage for refills: %s", ex)

    async def _async_save_storage(self) -> None:
        """Save refill state and previous levels to persistent storage."""
        try:
            serialized_refills = {}
            for tank_id, refill in self.last_refills.items():
                ts = refill.get("timestamp")
                serialized_refills[tank_id] = {
                    "amount": refill.get("amount"),
                    "timestamp": ts.isoformat() if isinstance(ts, datetime) else None,
                }
            await self._store.async_save(
                {
                    "previous_levels": self._previous_levels,
                    "last_refills": serialized_refills,
                }
            )
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.warning("Could not save persistent storage for refills: %s", ex)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Update data via client."""
        await self._async_load_storage()
        try:
            data = await self.client.async_get_tanks()

            tanks_dict: dict[str, dict[str, Any]] = {}
            for tank in data:
                raw_id = tank.get("tank_id")
                if raw_id is None:
                    continue
                tank_id = str(raw_id).strip()
                if not tank_id:
                    continue
                tanks_dict[tank_id] = tank
                self._check_refill(tank_id, tank)

            # Validated tanks_dict first before updating timestamp & clearing repairs
            self.last_successful_update = dt_util.utcnow()
            async_delete_issue(self.hass, DOMAIN, self.issue_id)
            await self._async_save_storage()

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
        source = "sensor_gallons"
        gal_str = tank.get("sensor_gallons")
        if gal_str is None:
            source = "model_gallons"
            gal_str = tank.get("model_gallons")

        if gal_str is None:
            return

        try:
            current_level = float(gal_str)
        except (TypeError, ValueError, OverflowError):
            return

        if tank_id not in self._previous_levels:
            self._previous_levels[tank_id] = {}

        tank_levels = self._previous_levels[tank_id]
        if source in tank_levels:
            prev_level = tank_levels[source]
            if prev_level is not None:
                diff = current_level - prev_level
                if diff >= 15.0:
                    _LOGGER.info(
                        "Refill detected for tank %s: %.1f gallons added", tank_id, diff
                    )
                    self.last_refills[tank_id] = {
                        "amount": round(diff, 1),
                        "timestamp": dt_util.utcnow(),
                    }

        tank_levels[source] = current_level

    def _raise_api_breakage_issue(self) -> None:
        """Raise an entry-specific Home Assistant repair issue for API breakage."""
        async_create_issue(
            self.hass,
            DOMAIN,
            self.issue_id,
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=IssueSeverity.ERROR,
            translation_key="api_breakage",
        )
