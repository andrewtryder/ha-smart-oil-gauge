"""Diagnostics support for Smart Oil Gauge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import SmartOilGaugeConfigEntry

TO_REDACT = {
    CONF_USERNAME,
    CONF_PASSWORD,
    "user_pass",
    "ccf_nonce",
    "cookie",
    "cookies",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SmartOilGaugeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator

    tanks_info: dict[str, Any] = {}
    if coordinator.data:
        for idx, tank_data in enumerate(coordinator.data.values(), start=1):
            tanks_info[f"tank_{idx}"] = {
                "has_sensor_gallons": tank_data.get("sensor_gallons") is not None,
                "has_model_gallons": tank_data.get("model_gallons") is not None,
                "has_nominal": tank_data.get("nominal") is not None,
                "battery_status_available": tank_data.get("battery") is not None,
                "has_usage_rate": tank_data.get("sensor_usg") is not None,
            }

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        "coordinator_last_update_success": coordinator.last_update_success,
        "coordinator_last_successful_update": (
            coordinator.last_successful_update.isoformat()
            if coordinator.last_successful_update
            else None
        ),
        "tanks_count": len(coordinator.data) if coordinator.data else 0,
        "tanks": tanks_info,
    }
