"""Redacted diagnostic data for support without exposing LAN addresses."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_HOST, DOMAIN
from .coordinator import PowerManagerCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return current monitor-only diagnostics with the host redacted."""
    coordinator: PowerManagerCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data
    return {
        "entry": async_redact_data(dict(entry.data), {CONF_HOST}),
        "last_update_success": coordinator.last_update_success,
        "device_info": asdict(data.device_info),
        "battery_state": asdict(data.battery_state),
        "possible_external_controller": data.possible_external_controller,
        "speedwire_source_count": len(data.speedwire_sources),
        "speedwire_observation_state": data.speedwire_observation_state,
        "control_ownership_clear": data.control_ownership_clear,
        "simulated_rule_id": data.simulated_rule_id,
        "simulated_target_power_w": data.simulated_target_power_w,
        "simulated_accepted": data.simulated_accepted,
        "simulated_reason": data.simulated_reason,
        "simulated_restore_normal": data.simulated_restore_normal,
        "simulated_held": data.simulated_held,
        "control_mode": data.control_mode,
        "active_control_available": data.active_control_available,
        "control_block_reason": data.control_block_reason,
    }
