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
from .core.powermanager_core.models import InverterState


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
        key="firmware_version",
        translation_key="firmware_version",
        value_fn=lambda coordinator: coordinator.data.device_info.firmware_version or "unknown",
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
        key="event_code",
        translation_key="event_code",
        value_fn=lambda coordinator: coordinator.data.battery_state.event_code,
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
    PowerManagerSensorDescription(
        key="grid_power",
        translation_key="grid_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.energy_state.grid.grid_power_w
        if coordinator.data.energy_state.grid
        else None,
    ),
    PowerManagerSensorDescription(
        key="pv_power",
        translation_key="pv_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.energy_state.grid.pv_power_w
        if coordinator.data.energy_state.grid
        else None,
    ),
    PowerManagerSensorDescription(
        key="load_power",
        translation_key="load_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.energy_state.grid.load_power_w
        if coordinator.data.energy_state.grid
        else None,
    ),
    PowerManagerSensorDescription(
        key="price",
        translation_key="price",
        native_unit_of_measurement="/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.energy_state.price.price_per_kwh
        if coordinator.data.energy_state.price
        else None,
    ),
    PowerManagerSensorDescription(
        key="remaining_pv_forecast",
        translation_key="remaining_pv_forecast",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.energy_state.forecast.remaining_pv_kwh
        if coordinator.data.energy_state.forecast
        else None,
    ),
    PowerManagerSensorDescription(
        key="expected_remaining_load",
        translation_key="expected_remaining_load",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: (
            coordinator.data.energy_state.forecast.expected_remaining_load_kwh
            if coordinator.data.energy_state.forecast
            else None
        ),
    ),
    PowerManagerSensorDescription(
        key="forecast_pv_power_now",
        translation_key="forecast_pv_power_now",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: (
            coordinator.data.energy_state.forecast.pv_power_forecast_w
            if coordinator.data.energy_state.forecast
            else None
        ),
    ),
    PowerManagerSensorDescription(
        key="forecast_load_power_now",
        translation_key="forecast_load_power_now",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: (
            coordinator.data.energy_state.forecast.load_power_forecast_w
            if coordinator.data.energy_state.forecast
            else None
        ),
    ),
    PowerManagerSensorDescription(
        key="forecast_pv_error",
        translation_key="forecast_pv_error",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: _forecast_error(coordinator, "pv"),
    ),
    PowerManagerSensorDescription(
        key="forecast_load_error",
        translation_key="forecast_load_error",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: _forecast_error(coordinator, "load"),
    ),
    PowerManagerSensorDescription(
        key="predictive_target_power",
        translation_key="predictive_target_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.predictive_target_power_w,
    ),
    PowerManagerSensorDescription(
        key="predictive_target_soc",
        translation_key="predictive_target_soc",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.predictive_target_soc_percent,
    ),
    PowerManagerSensorDescription(
        key="predictive_forecast_surplus",
        translation_key="predictive_forecast_surplus",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.predictive_forecast_surplus_kwh,
    ),
    PowerManagerSensorDescription(
        key="predictive_headroom",
        translation_key="predictive_headroom",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.predictive_headroom_kwh,
    ),
    PowerManagerSensorDescription(
        key="predictive_charge_inhibit",
        translation_key="predictive_charge_inhibit",
        value_fn=lambda coordinator: (
            None
            if coordinator.data.predictive_charge_inhibit is None
            else "on"
            if coordinator.data.predictive_charge_inhibit
            else "off"
        ),
    ),
    PowerManagerSensorDescription(
        key="predictive_reason",
        translation_key="predictive_reason",
        value_fn=lambda coordinator: coordinator.data.predictive_reason,
    ),
    PowerManagerSensorDescription(
        key="planned_charge_power",
        translation_key="planned_charge_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: max(coordinator.data.predictive_target_power_w or 0, 0),
    ),
    PowerManagerSensorDescription(
        key="planned_discharge_power",
        translation_key="planned_discharge_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: max(-(coordinator.data.simulated_target_power_w or 0), 0),
    ),
    PowerManagerSensorDescription(
        key="simulated_rule",
        translation_key="simulated_rule",
        value_fn=lambda coordinator: coordinator.data.simulated_rule_id or "No matching rule",
    ),
    PowerManagerSensorDescription(
        key="simulated_target_power",
        translation_key="simulated_target_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.simulated_target_power_w,
    ),
    PowerManagerSensorDescription(
        key="simulated_decision",
        translation_key="simulated_decision",
        value_fn=lambda coordinator: (
            "accepted"
            if coordinator.data.simulated_accepted
            else "rejected"
            if coordinator.data.simulated_accepted is False
            else "unknown"
        ),
    ),
    PowerManagerSensorDescription(
        key="simulated_reason",
        translation_key="simulated_reason",
        value_fn=lambda coordinator: coordinator.data.simulated_reason or "none",
    ),
    PowerManagerSensorDescription(
        key="control_mode",
        translation_key="control_mode",
        value_fn=lambda coordinator: coordinator.data.control_mode,
    ),
    PowerManagerSensorDescription(
        key="control_block_reason",
        translation_key="control_block_reason",
        value_fn=lambda coordinator: coordinator.data.control_block_reason,
    ),
    PowerManagerSensorDescription(
        key="active_control_power",
        translation_key="active_control_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.active_control_power_w,
    ),
    PowerManagerSensorDescription(
        key="active_control_last_error",
        translation_key="active_control_last_error",
        value_fn=lambda coordinator: coordinator.active_control_last_error or "none",
    ),
    PowerManagerSensorDescription(
        key="speedwire_source_count",
        translation_key="speedwire_source_count",
        value_fn=lambda coordinator: len(coordinator.data.speedwire_sources),
    ),
    PowerManagerSensorDescription(
        key="speedwire_source_addresses",
        translation_key="speedwire_source_addresses",
        value_fn=lambda coordinator: ", ".join(coordinator.data.speedwire_sources)
        or "none",
    ),
    PowerManagerSensorDescription(
        key="energy_dashboard_summary",
        translation_key="energy_dashboard_summary",
        value_fn=lambda coordinator: (
            "ready" if not coordinator.data.energy_dashboard_missing else "incomplete"
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up monitor-only sensors for a config entry."""
    coordinator: PowerManagerCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        PowerManagerSensor(coordinator, entry, description) for description in SENSORS
    ]
    async_add_entities(entities)

    added_sources: set[tuple[str, str]] = set()

    def add_inverter_entities() -> None:
        """Expose imported dashboard sources when their topology is first available."""
        new_entities: list[SensorEntity] = []
        for source in coordinator.inverter_sources:
            configured = {
                "generation_power": source.generation_power_entity,
                "battery_power": source.battery_power_entity,
                "remaining_pv_forecast": source.remaining_pv_forecast_entity,
            }
            for metric, source_entity in configured.items():
                key = (source.source_id, metric)
                if source_entity and key not in added_sources:
                    added_sources.add(key)
                    new_entities.append(
                        InverterTelemetrySensor(coordinator, entry, source.source_id, metric)
                    )
        if new_entities:
            async_add_entities(new_entities)

    add_inverter_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_inverter_entities))


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
        identifiers = {(DOMAIN, entry.unique_id or entry.entry_id)}
        if device.serial_number:
            identifiers.add((DOMAIN, f"serial:{device.serial_number}"))
        self._attr_device_info = HaDeviceInfo(
            identifiers=identifiers,
            manufacturer="SMA",
            model=device.model,
            serial_number=device.serial_number,
        )

    @property
    def native_value(self) -> Any:
        """Return the latest read-only value."""
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose sender addresses on the Speedwire count sensor for debugging."""
        if self.entity_description.key in {"forecast_pv_power_now", "forecast_load_power_now"}:
            forecast = self.coordinator.data.energy_state.forecast
            if forecast is None:
                return None
            profile = (
                forecast.pv_power_forecast_profile
                if self.entity_description.key == "forecast_pv_power_now"
                else forecast.load_power_forecast_profile
            )
            return {
                "forecast_profile": [
                    {"time": timestamp.isoformat(), "power_w": round(power_w, 3)}
                    for timestamp, power_w in profile
                ],
                "forecast_timestamp": forecast.timestamp.isoformat(),
            }
        if self.entity_description.key in {"planned_charge_power", "planned_discharge_power"}:
            data = self.coordinator.data
            return {
                "planner_reason": data.predictive_reason,
                "target_soc_percent": data.predictive_target_soc_percent,
                "forecast_surplus_kwh": data.predictive_forecast_surplus_kwh,
                "charge_inhibit": data.predictive_charge_inhibit,
                "rule_target_power_w": data.simulated_target_power_w,
            }
        if self.entity_description.key not in {
            "speedwire_source_count",
            "speedwire_source_addresses",
        }:
            if self.entity_description.key != "energy_dashboard_summary":
                return None
            data = self.coordinator.data
            return {
                "summary": data.energy_dashboard_summary,
                "missing": list(data.energy_dashboard_missing),
            }
        data = self.coordinator.data
        return {
            "observation_state": data.speedwire_observation_state,
            "observed_sources": list(data.speedwire_sources),
            "external_sources": list(data.speedwire_external_sources),
        }


def _forecast_error(coordinator: PowerManagerCoordinator, kind: str) -> float | None:
    """Return actual minus predicted power for recorder-based validation."""
    forecast = coordinator.data.energy_state.forecast
    grid = coordinator.data.energy_state.grid
    if forecast is None or grid is None:
        return None
    predicted = (
        forecast.pv_power_forecast_w if kind == "pv" else forecast.load_power_forecast_w
    )
    actual = grid.pv_power_w if kind == "pv" else grid.load_power_w
    if predicted is None or actual is None:
        return None
    return actual - predicted


class InverterTelemetrySensor(CoordinatorEntity[PowerManagerCoordinator], SensorEntity):
    """Expose one configured inverter telemetry value as a read-only sensor."""

    _attr_has_entity_name = False
    _METADATA = {
        "generation_power": ("generation power", "W", SensorDeviceClass.POWER),
        "battery_power": ("battery power", "W", SensorDeviceClass.POWER),
        "remaining_pv_forecast": ("remaining PV forecast", "kWh", None),
    }

    def __init__(
        self,
        coordinator: PowerManagerCoordinator,
        entry: ConfigEntry,
        source_id: str,
        metric: str,
    ) -> None:
        super().__init__(coordinator)
        label, unit, device_class = self._METADATA[metric]
        self._source_id = source_id
        self._metric = metric
        self._attr_name = f"{source_id} {label}"
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_inverter_{source_id}_{metric}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_info = HaDeviceInfo(
            identifiers={(DOMAIN, f"{entry.unique_id or entry.entry_id}:inverter:{source_id}")},
            manufacturer="PowerManager",
            model=source_id,
        )

    @property
    def native_value(self) -> float | None:
        """Return the configured inverter metric in normalized units."""
        state = next(
            (item for item in self.coordinator.data.inverters if item.source_id == self._source_id),
            None,
        )
        return _inverter_metric_value(state, self._metric) if state else None

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Expose the source role and freshness alongside each metric."""
        state = next(
            (item for item in self.coordinator.data.inverters if item.source_id == self._source_id),
            None,
        )
        if state is None:
            return None
        return {
            "source_id": state.source_id,
            "role": state.role,
            "communication_state": state.communication_state,
        }


def _inverter_metric_value(state: InverterState, metric: str) -> float | None:
    """Select a normalized metric from one inverter state."""
    if metric == "remaining_pv_forecast":
        return state.remaining_pv_forecast_kwh
    return getattr(state, f"{metric}_w")
