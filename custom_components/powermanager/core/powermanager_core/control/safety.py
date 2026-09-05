"""Pure safety checks for control intents."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from ..models import BatteryState, CommunicationState, EnergyState
from .policy import ControlIntent


@dataclass(frozen=True, slots=True)
class SafetyConfig:
    """Bounds and freshness requirements for a future actuator."""

    max_charge_power_w: float = 5000
    max_discharge_power_w: float = 5000
    minimum_soc_percent: float = 10
    maximum_soc_percent: float = 98
    max_energy_age_seconds: int = 120
    max_future_skew_seconds: int = 5
    allowed_operating_states: frozenset[str] = frozenset({"Ok", "OK"})
    charge_warning_event_codes: frozenset[int] = frozenset({7613})


def validate_intent(
    intent: ControlIntent,
    energy: EnergyState,
    config: SafetyConfig,
    *,
    enabled: bool,
    at: datetime,
) -> tuple[bool, str | None]:
    """Validate an intent without communicating with any device."""
    if not enabled:
        return False, "control is disabled"
    config_error = _validate_config(config)
    if config_error is not None:
        return False, config_error
    if not math.isfinite(intent.target_power_w):
        return False, "target power is not finite"
    if energy.battery.communication_state is not CommunicationState.ONLINE:
        return False, "battery telemetry is not online"
    freshness_error = _validate_timestamp(
        energy.timestamp, at, config, source="energy telemetry"
    )
    if freshness_error is not None:
        return False, freshness_error
    freshness_error = _validate_timestamp(
        energy.battery.timestamp, at, config, source="battery telemetry"
    )
    if freshness_error is not None:
        return False, freshness_error
    for name, state in (
        ("grid telemetry", energy.grid),
        ("price telemetry", energy.price),
        ("forecast telemetry", energy.forecast),
    ):
        if state is not None:
            if state.communication_state is not CommunicationState.ONLINE:
                return False, f"{name} is not online"
            freshness_error = _validate_timestamp(state.timestamp, at, config, source=name)
            if freshness_error is not None:
                return False, freshness_error
    battery = energy.battery
    if not _operating_state_allows_intent(intent.target_power_w, battery, config):
        return False, "battery operating state is not allowed"
    soc = battery.battery_soc_percent
    if soc is not None and (not math.isfinite(soc) or not 0 <= soc <= 100):
        return False, "battery SoC is invalid"
    if intent.target_power_w > config.max_charge_power_w:
        return False, "charge target exceeds configured limit"
    if intent.target_power_w < -config.max_discharge_power_w:
        return False, "discharge target exceeds configured limit"
    if intent.target_power_w == 0:
        return True, None
    if soc is None:
        return False, "battery SoC is unavailable"
    if intent.target_power_w > 0:
        if soc >= config.maximum_soc_percent:
            return False, "battery is at or above maximum SoC"
        if battery.charge_limit_w is not None:
            if not math.isfinite(battery.charge_limit_w) or battery.charge_limit_w < 0:
                return False, "battery charge limit is invalid"
            if intent.target_power_w > battery.charge_limit_w:
                return False, "charge target exceeds battery limit"
    if intent.target_power_w < 0:
        dynamic_floor = battery.discharge_limit_soc_percent
        if dynamic_floor is not None and (
            not math.isfinite(dynamic_floor) or not 0 <= dynamic_floor <= 100
        ):
            return False, "battery discharge limit is invalid"
        effective_floor = max(
            config.minimum_soc_percent,
            dynamic_floor if dynamic_floor is not None else config.minimum_soc_percent,
        )
        if soc <= effective_floor:
            return False, "battery is at or below effective minimum SoC"
    return True, None


def _validate_config(config: SafetyConfig) -> str | None:
    """Reject unsafe or nonsensical safety configuration before an action."""
    numeric = (
        config.max_charge_power_w,
        config.max_discharge_power_w,
        config.minimum_soc_percent,
        config.maximum_soc_percent,
    )
    if any(not math.isfinite(value) for value in numeric):
        return "safety configuration is not finite"
    if config.max_charge_power_w < 0 or config.max_discharge_power_w < 0:
        return "safety power limits cannot be negative"
    if not 0 <= config.minimum_soc_percent <= config.maximum_soc_percent <= 100:
        return "safety SoC limits are invalid"
    if config.max_energy_age_seconds < 0 or config.max_future_skew_seconds < 0:
        return "safety freshness limits cannot be negative"
    if not config.allowed_operating_states:
        return "allowed operating states cannot be empty"
    if any(not isinstance(code, int) or code < 0 for code in config.charge_warning_event_codes):
        return "charge warning event codes are invalid"
    return None


def _operating_state_allows_intent(
    target_power_w: float, battery: BatteryState, config: SafetyConfig
) -> bool:
    """Allow charging through the documented meter warning, never discharge."""
    if battery.operating_state in config.allowed_operating_states:
        return True
    return (
        target_power_w > 0
        and battery.operating_state == "Warning"
        and battery.event_code in config.charge_warning_event_codes
    )


def _validate_timestamp(
    timestamp: datetime, at: datetime, config: SafetyConfig, *, source: str
) -> str | None:
    """Reject stale, future, or timezone-incompatible source timestamps."""
    try:
        age = (at - timestamp).total_seconds()
    except TypeError:
        return f"{source} timestamp is invalid"
    if age < -config.max_future_skew_seconds:
        return f"{source} timestamp is in the future"
    if age > config.max_energy_age_seconds:
        return f"{source} is stale"
    return None
