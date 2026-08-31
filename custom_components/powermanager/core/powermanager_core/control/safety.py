"""Pure safety checks for control intents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models import CommunicationState, EnergyState
from .policy import ControlIntent


@dataclass(frozen=True, slots=True)
class SafetyConfig:
    """Bounds and freshness requirements for a future actuator."""

    max_charge_power_w: float = 5000
    max_discharge_power_w: float = 5000
    minimum_soc_percent: float = 10
    max_energy_age_seconds: int = 120


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
    if energy.battery.communication_state is not CommunicationState.ONLINE:
        return False, "battery telemetry is not online"
    if (at - energy.timestamp).total_seconds() > config.max_energy_age_seconds:
        return False, "energy telemetry is stale"
    if intent.target_power_w > config.max_charge_power_w:
        return False, "charge target exceeds configured limit"
    if intent.target_power_w < -config.max_discharge_power_w:
        return False, "discharge target exceeds configured limit"
    if intent.target_power_w < 0 and energy.battery.battery_soc_percent is not None:
        dynamic_floor = energy.battery.discharge_limit_soc_percent
        effective_floor = max(
            config.minimum_soc_percent,
            dynamic_floor if dynamic_floor is not None else config.minimum_soc_percent,
        )
        if energy.battery.battery_soc_percent <= effective_floor:
            return False, "battery is at or below effective minimum SoC"
    return True, None
