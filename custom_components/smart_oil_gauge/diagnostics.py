"""Diagnostics support for Smart Oil Gauge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import SmartOilGaugeConfigEntry

TO_REDACT = {"username", "password", "user_pass", "ccf_nonce", "cookie", "cookies"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SmartOilGaugeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator

    tanks_info: dict[str, Any] = {}
    if coordinator.data:
        for tank_id, tank_data in coordinator.data.items():
            tanks_info[tank_id] = {
                "tank_id": tank_id,
                "tank_name": tank_data.get("tank_name"),
                "has_sensor_gallons": tank_data.get("sensor_gallons") is not None,
                "has_model_gallons": tank_data.get("model_gallons") is not None,
                "nominal": tank_data.get("nominal"),
                "battery": tank_data.get("battery"),
                "has_usage_rate": tank_data.get("sensor_usg") is not None,
            }

    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator_last_update_success": coordinator.last_update_success,
        "coordinator_last_successful_update": (
            coordinator.last_successful_update.isoformat()
            if coordinator.last_successful_update
            else None
        ),
        "tanks_count": len(coordinator.data) if coordinator.data else 0,
        "tanks": tanks_info,
    }
