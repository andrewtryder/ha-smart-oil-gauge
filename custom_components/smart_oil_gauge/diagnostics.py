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
                "has_last_read": tank_data.get("last_read") is not None,
                "has_data_servers": bool(tank_data.get("data_servers")),
                "sensor_registrations": len(tank_data.get("sensors") or []),
            }

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": async_redact_data(dict(entry.options), TO_REDACT),
        "coordinator_last_update_success": coordinator.last_update_success,
        "coordinator_last_successful_update": (
            coordinator.last_successful_update.isoformat()
            if coordinator.last_successful_update
            else None
        ),
        "tanks_count": len(coordinator.data) if coordinator.data else 0,
        "tanks": tanks_info,
        "history": {
            f"tank_{idx}": {
                "hourly_points": len(coordinator.series.get(tank_id, [])),
                "last_read": coordinator.last_read.get(tank_id),
                "backfilled_until": coordinator.backfilled_until.get(tank_id),
                "history_imported": coordinator.history_imported.get(tank_id, False),
                "last_backfill": coordinator.backfill_status.get(tank_id),
            }
            for idx, tank_id in enumerate(coordinator.data or {}, start=1)
        },
        "schedule": {
            "mode": coordinator.schedule_mode,
            "next_sync": coordinator.next_poll_at.isoformat()
            if coordinator.next_poll_at
            else None,
            **{
                f"tank_{idx}": _schedule_info(coordinator, tank_id)
                for idx, tank_id in enumerate(coordinator.data or {}, start=1)
            },
        },
    }


def _schedule_info(coordinator, tank_id: str) -> dict[str, Any] | None:
    """Upload schedule details for one tank."""
    sched = coordinator.schedules.get(tank_id)
    if sched is None:
        return None
    hours, source = sched.interval()
    expected = coordinator.next_expected_upload(tank_id)
    return {
        "portal_interval_hours": sched.configured_h,
        "gauge_interval_hours": sched.effective_h,
        "pending": sched.pending,
        "pending_since": sched.pending_since,
        "interval_confirmed_by_uploads": sched.confirmed,
        "possible_uploads": [
            t.isoformat() for t in coordinator.possible_uploads(tank_id)
        ],
        "overdue": coordinator.upload_overdue(tank_id),
        "interval_used_hours": hours,
        "interval_source": source,
        "measured_interval_hours": sched.measured_h(),
        "recent_uploads": len(sched.upload_times),
        "next_expected_upload": expected.isoformat() if expected else None,
        "config_error": sched.config_error,
        "number_of_tanks": sched.num_tanks,
    }
