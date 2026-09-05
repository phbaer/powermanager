"""Home Assistant setup for PowerManager."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import PowerManagerCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PowerManager from a config entry."""
    coordinator = PowerManagerCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.start_speedwire_monitor()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await coordinator.stop_speedwire_monitor()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
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
