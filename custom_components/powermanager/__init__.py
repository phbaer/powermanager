"""Home Assistant setup for PowerManager."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .coordinator import PowerManagerCoordinator
from .core.powermanager_core.backends.sma_sunny_island import ControlWriteError

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Register explicit, bounded control services without opening a device."""

    async def start_control(call: ServiceCall) -> None:
        coordinators = list(hass.data.get(DOMAIN, {}).values())
        if len(coordinators) != 1:
            raise HomeAssistantError("PowerManager must have exactly one configured entry")
        coordinator: PowerManagerCoordinator = coordinators[0]
        try:
            await coordinator.start_active_control(
                float(call.data["power_w"]), int(call.data["duration_seconds"])
            )
        except ControlWriteError as error:
            raise HomeAssistantError(str(error)) from error

    async def stop_control(_call: ServiceCall) -> None:
        coordinators = list(hass.data.get(DOMAIN, {}).values())
        if len(coordinators) != 1:
            raise HomeAssistantError("PowerManager must have exactly one configured entry")
        await coordinators[0].stop_active_control()

    hass.services.async_register(
        DOMAIN,
        "start_control",
        start_control,
        schema=vol.Schema(
            {
                vol.Required("power_w"): vol.Coerce(float),
                vol.Optional("duration_seconds", default=300): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=900)
                ),
            }
        ),
    )
    hass.services.async_register(DOMAIN, "stop_control", stop_control)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PowerManager from a config entry."""
    coordinator = PowerManagerCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.start_speedwire_monitor()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await coordinator.stop_speedwire_monitor()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the coordinator after connection or polling options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a PowerManager config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: PowerManagerCoordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.stop_speedwire_monitor()
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
