"""Deterministic predictive charging plans without device side effects.

The planner produces an explainable shadow recommendation. It does not issue a
command and does not replace :mod:`control.safety`; any future actuator must
validate the resulting intent again with fresh telemetry.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime


class PredictivePlanningError(ValueError):
    """Predictive inputs cannot produce a safe plan."""


@dataclass(frozen=True, slots=True)
class PredictiveInputs:
    """Inputs required for one forecast-based planning decision."""

    timestamp: datetime
    horizon_end: datetime
    usable_capacity_kwh: float
    battery_soc_percent: float
    end_soc_target_percent: float
    reserve_soc_percent: float
    remaining_pv_kwh: float
    remaining_load_kwh: float
    forecast_uncertainty_kwh: float = 0.0
    export_capacity_kwh: float = 0.0
    max_charge_power_w: float = 0.0
    reported_charge_limit_w: float | None = None
    grid_charge_allowed: bool = False


@dataclass(frozen=True, slots=True)
class PredictivePlan:
    """Explainable recommendation for shadow mode or later policy review."""

    timestamp: datetime
    target_power_w: float
    target_soc_percent: float
    required_charge_kwh: float
    forecast_surplus_kwh: float
    headroom_kwh: float
    charge_inhibit: bool
    reason: str


def plan_predictive_charge(inputs: PredictiveInputs) -> PredictivePlan:
    """Build one bounded plan from forecast and battery constraints.

    Positive power is charging. A zero target is accompanied by
    ``charge_inhibit`` so callers do not confuse "defer charging" with a
    general inverter mode. The planner never recommends discharge.
    """
    _validate_inputs(inputs)
    horizon_hours = (inputs.horizon_end - inputs.timestamp).total_seconds() / 3600
    current_energy = inputs.usable_capacity_kwh * inputs.battery_soc_percent / 100
    target_energy = inputs.usable_capacity_kwh * inputs.end_soc_target_percent / 100
    required_charge = max(target_energy - current_energy, 0.0)
    forecast_surplus = max(
        inputs.remaining_pv_kwh
        - inputs.remaining_load_kwh
        - inputs.forecast_uncertainty_kwh,
        0.0,
    )
    export_capacity = min(inputs.export_capacity_kwh, forecast_surplus)
    absorbable_surplus = max(forecast_surplus - export_capacity, 0.0)
    headroom = max(inputs.usable_capacity_kwh - current_energy, 0.0)
    desired_headroom = min(absorbable_surplus, headroom)
    target_soc = 100 - desired_headroom / inputs.usable_capacity_kwh * 100
    target_soc = round(max(inputs.reserve_soc_percent, min(100.0, target_soc)), 6)

    if absorbable_surplus > 0 and inputs.battery_soc_percent + 1e-9 >= target_soc:
        return PredictivePlan(
            inputs.timestamp,
            0.0,
            target_soc,
            required_charge,
            forecast_surplus,
            headroom,
            True,
            "preserve_forecast_headroom",
        )

    if required_charge <= absorbable_surplus:
        return PredictivePlan(
            inputs.timestamp,
            0.0,
            target_soc,
            required_charge,
            forecast_surplus,
            headroom,
            False,
            "defer_to_forecast_surplus",
        )

    if not inputs.grid_charge_allowed:
        return PredictivePlan(
            inputs.timestamp,
            0.0,
            target_soc,
            required_charge,
            forecast_surplus,
            headroom,
            False,
            "grid_charging_disabled",
        )

    deficit = required_charge - absorbable_surplus
    power = min(inputs.max_charge_power_w, deficit / horizon_hours * 1000)
    if inputs.reported_charge_limit_w is not None:
        power = min(power, inputs.reported_charge_limit_w)
    return PredictivePlan(
        inputs.timestamp,
        max(0.0, power),
        target_soc,
        required_charge,
        forecast_surplus,
        headroom,
        False,
        "charge_to_end_target",
    )


def replay_predictive_plans(inputs: Iterable[PredictiveInputs]) -> tuple[PredictivePlan, ...]:
    """Replay timestamped inputs deterministically for backtests and shadow mode."""
    return tuple(plan_predictive_charge(item) for item in inputs)


def _validate_inputs(inputs: PredictiveInputs) -> None:
    if inputs.horizon_end <= inputs.timestamp:
        raise PredictivePlanningError("planning horizon must end after the input timestamp")
    finite_values = (
        inputs.usable_capacity_kwh,
        inputs.battery_soc_percent,
        inputs.end_soc_target_percent,
        inputs.reserve_soc_percent,
        inputs.remaining_pv_kwh,
        inputs.remaining_load_kwh,
        inputs.forecast_uncertainty_kwh,
        inputs.export_capacity_kwh,
        inputs.max_charge_power_w,
    )
    if inputs.reported_charge_limit_w is not None:
        finite_values += (inputs.reported_charge_limit_w,)
    if not all(math.isfinite(value) for value in finite_values):
        raise PredictivePlanningError("planning inputs must be finite")
    if inputs.usable_capacity_kwh <= 0:
        raise PredictivePlanningError("usable capacity must be positive")
    if not 0 <= inputs.reserve_soc_percent <= inputs.end_soc_target_percent <= 100:
        raise PredictivePlanningError(
            "reserve and target SoC must satisfy 0 <= reserve <= target <= 100"
        )
    if not 0 <= inputs.battery_soc_percent <= 100:
        raise PredictivePlanningError("battery SoC must be between 0 and 100 percent")
    if inputs.remaining_pv_kwh < 0 or inputs.remaining_load_kwh < 0:
        raise PredictivePlanningError("forecast energies cannot be negative")
    if inputs.forecast_uncertainty_kwh < 0 or inputs.export_capacity_kwh < 0:
        raise PredictivePlanningError("forecast uncertainty and export capacity cannot be negative")
    if inputs.max_charge_power_w < 0 or (
        inputs.reported_charge_limit_w is not None and inputs.reported_charge_limit_w < 0
    ):
        raise PredictivePlanningError("charge limits cannot be negative")
