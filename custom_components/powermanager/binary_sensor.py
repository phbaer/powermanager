"""Safety warnings derived from passive telemetry observation."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PowerManagerCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Expose a warning when another SMA sender appears on Speedwire."""
    async_add_entities([ExternalControllerWarning(hass.data[DOMAIN][entry.entry_id], entry)])
    async_add_entities([ControlOwnershipClear(hass.data[DOMAIN][entry.entry_id], entry)])
    async_add_entities([ActiveControlAvailability(hass.data[DOMAIN][entry.entry_id], entry)])


class ExternalControllerWarning(CoordinatorEntity[PowerManagerCoordinator], BinarySensorEntity):
    """Possible competing controller detected from passive Speedwire traffic."""

    _attr_has_entity_name = True
    _attr_translation_key = "external_controller_warning"

    def __init__(self, coordinator: PowerManagerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_external_controller_warning"

    @property
    def is_on(self) -> bool | None:
        """Return true when a non-Sunny-Island sender has been observed."""
        data = self.coordinator.data
        if data.possible_external_controller:
            return True
        if data.speedwire_observation_state != "online":
            return None
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose observation health and sender addresses for local debugging."""
        data = self.coordinator.data
        return {
            "observation_state": data.speedwire_observation_state,
            "observed_sources": list(data.speedwire_sources),
            "external_sources": list(data.speedwire_external_sources),
        }


class ControlOwnershipClear(CoordinatorEntity[PowerManagerCoordinator], BinarySensorEntity):
    """Show whether the future control gate has passed ownership checks only."""

    _attr_has_entity_name = True
    _attr_translation_key = "control_ownership_clear"

    def __init__(self, coordinator: PowerManagerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_control_ownership_clear"

    @property
    def is_on(self) -> bool:
        """Return ownership eligibility; this never enables a write path."""
        return self.coordinator.data.control_ownership_clear


class ActiveControlAvailability(CoordinatorEntity[PowerManagerCoordinator], BinarySensorEntity):
    """Expose the hard monitor-only boundary as an explicit status entity."""

    _attr_has_entity_name = True
    _attr_translation_key = "active_control_available"

    def __init__(self, coordinator: PowerManagerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_active_control_available"

    @property
    def is_on(self) -> bool:
        """Return whether a commissioned active-control path is available."""
        return self.coordinator.data.active_control_available

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Explain why active control is unavailable."""
        return {
            "control_mode": self.coordinator.data.control_mode,
            "reason": self.coordinator.data.control_block_reason,
        }
