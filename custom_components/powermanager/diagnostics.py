"""Diagnostic data for support, including observed local sender addresses."""

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
    """Return monitor-only diagnostics with the configured host redacted."""
    coordinator: PowerManagerCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data
    return {
        "entry": async_redact_data(dict(entry.data), {CONF_HOST}),
        "last_update_success": coordinator.last_update_success,
        "device_info": asdict(data.device_info),
        "battery_state": asdict(data.battery_state),
        "inverters": [asdict(inverter) for inverter in data.inverters],
        "possible_external_controller": data.possible_external_controller,
        "speedwire_source_count": len(data.speedwire_sources),
        "speedwire_external_sources": list(data.speedwire_external_sources),
        "speedwire_observation_state": data.speedwire_observation_state,
        "energy_dashboard_summary": data.energy_dashboard_summary,
        "energy_dashboard_missing": list(data.energy_dashboard_missing),
        "control_ownership_clear": data.control_ownership_clear,
        "simulated_rule_id": data.simulated_rule_id,
        "simulated_target_power_w": data.simulated_target_power_w,
        "simulated_accepted": data.simulated_accepted,
        "simulated_reason": data.simulated_reason,
        "simulated_restore_normal": data.simulated_restore_normal,
        "simulated_held": data.simulated_held,
        "predictive_target_power_w": data.predictive_target_power_w,
        "predictive_target_soc_percent": data.predictive_target_soc_percent,
        "predictive_forecast_surplus_kwh": data.predictive_forecast_surplus_kwh,
        "predictive_headroom_kwh": data.predictive_headroom_kwh,
        "predictive_charge_inhibit": data.predictive_charge_inhibit,
        "predictive_reason": data.predictive_reason,
        "control_mode": data.control_mode,
        "active_control_available": data.active_control_available,
        "control_block_reason": data.control_block_reason,
        "active_control_running": getattr(coordinator, "active_control_running", False),
        "active_control_power_w": getattr(coordinator, "active_control_power_w", None),
        "active_control_last_error": getattr(coordinator, "active_control_last_error", None),
    }
