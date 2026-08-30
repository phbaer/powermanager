"""Read-only PowerManager sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
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
    PowerManagerSensorDescription(
        key="operating_state",
        translation_key="operating_state",
        value_fn=lambda coordinator: coordinator.data.battery_state.operating_state,
    ),
    PowerManagerSensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.battery_state.battery_soc_percent,
    ),
    PowerManagerSensorDescription(
        key="battery_power",
        translation_key="battery_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.battery_state.battery_power_w,
    ),
    PowerManagerSensorDescription(
        key="battery_current",
        translation_key="battery_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement="A",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.battery_state.battery_current_a,
    ),
    PowerManagerSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement="V",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.battery_state.battery_voltage_v,
    ),
    PowerManagerSensorDescription(
        key="discharge_soc_limit",
        translation_key="discharge_soc_limit",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.battery_state.discharge_limit_soc_percent,
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
