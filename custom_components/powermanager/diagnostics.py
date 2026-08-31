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
        "speedwire_sources": list(data.speedwire_sources),
    }
