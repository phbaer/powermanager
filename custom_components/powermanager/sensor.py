"""Read-only PowerManager sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo as HaDeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PowerManagerCoordinator


@dataclass(frozen=True, kw_only=True)
class PowerManagerSensorDescription(SensorEntityDescription):
    """Describe a read-only value in coordinator data."""

    value_fn: Callable[[PowerManagerCoordinator], Any]


SENSORS: tuple[PowerManagerSensorDescription, ...] = (
    PowerManagerSensorDescription(
        key="device_type",
        translation_key="device_type",
        value_fn=lambda coordinator: coordinator.data.device_info.device_type,
    ),
    PowerManagerSensorDescription(
        key="communication_state",
        translation_key="communication_state",
        value_fn=lambda coordinator: coordinator.data.battery_state.communication_state,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up monitor-only sensors for a config entry."""
    coordinator: PowerManagerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PowerManagerSensor(coordinator, entry, description) for description in SENSORS
    )


class PowerManagerSensor(CoordinatorEntity[PowerManagerCoordinator], SensorEntity):
    """A state value supplied by the shared coordinator."""

    entity_description: PowerManagerSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PowerManagerCoordinator,
        entry: ConfigEntry,
        description: PowerManagerSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{description.key}"
        device = coordinator.data.device_info
        self._attr_device_info = HaDeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            manufacturer="SMA",
            model=device.model,
            serial_number=device.serial_number,
        )

    @property
    def native_value(self) -> Any:
        """Return the latest read-only value."""
        return self.entity_description.value_fn(self.coordinator)
