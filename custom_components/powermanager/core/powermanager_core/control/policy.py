"""Deterministic control policy evaluation without device side effects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from ..models import EnergyState


@dataclass(frozen=True, slots=True)
class RuleConditions:
    """Optional predicates for a control rule."""

    grid_power_below_w: float | None = None
    grid_power_above_w: float | None = None
    battery_soc_below_percent: float | None = None
    battery_soc_above_percent: float | None = None
    price_below_per_kwh: float | None = None
    price_above_per_kwh: float | None = None
    forecast_surplus_above_kwh: float | None = None
    between: tuple[time, time] | None = None


@dataclass(frozen=True, slots=True)
class ControlRule:
    """A prioritized rule that emits a target battery power."""

    rule_id: str
    priority: int
    conditions: RuleConditions
    target_power_w: float
    hold_seconds: int = 0
    cooldown_seconds: int = 0


@dataclass(frozen=True, slots=True)
class ControlIntent:
    """The side-effect-free result of evaluating one matching rule."""

    rule_id: str
    target_power_w: float
    hold_seconds: int
    evaluated_at: datetime
    cooldown_seconds: int = 0


def evaluate_rules(
    energy: EnergyState, rules: tuple[ControlRule, ...], *, at: datetime
) -> ControlIntent | None:
    """Return the highest-priority eligible intent, or ``None``.

    Missing telemetry makes a condition ineligible. Rules with equal priority
    are resolved by their original order, making evaluation deterministic.
    """
    for rule in sorted(enumerate(rules), key=lambda item: (-item[1].priority, item[0])):
        if _matches(rule[1].conditions, energy, at):
            return ControlIntent(
                rule[1].rule_id,
                rule[1].target_power_w,
                rule[1].hold_seconds,
                at,
                rule[1].cooldown_seconds,
            )
    return None


def _matches(conditions: RuleConditions, energy: EnergyState, at: datetime) -> bool:
    battery = energy.battery
    grid = energy.grid
    if conditions.grid_power_below_w is not None:
        if (
            grid is None
            or grid.grid_power_w is None
            or grid.grid_power_w >= conditions.grid_power_below_w
        ):
            return False
    if conditions.grid_power_above_w is not None:
        if (
            grid is None
            or grid.grid_power_w is None
            or grid.grid_power_w <= conditions.grid_power_above_w
        ):
            return False
    if conditions.battery_soc_below_percent is not None:
        if (
            battery.battery_soc_percent is None
            or battery.battery_soc_percent >= conditions.battery_soc_below_percent
        ):
            return False
    if conditions.battery_soc_above_percent is not None:
        if (
            battery.battery_soc_percent is None
            or battery.battery_soc_percent <= conditions.battery_soc_above_percent
        ):
            return False
    price = energy.price
    if conditions.price_below_per_kwh is not None:
        if (
            price is None
            or price.price_per_kwh is None
            or price.price_per_kwh >= conditions.price_below_per_kwh
        ):
            return False
    if conditions.forecast_surplus_above_kwh is not None:
        forecast = energy.forecast
        if (
            forecast is None
            or forecast.expected_surplus_kwh is None
            or forecast.expected_surplus_kwh <= conditions.forecast_surplus_above_kwh
        ):
            return False
    if conditions.price_above_per_kwh is not None:
        if (
            price is None
            or price.price_per_kwh is None
            or price.price_per_kwh <= conditions.price_above_per_kwh
        ):
            return False
    if conditions.between is not None and not _in_time_window(at.time(), conditions.between):
        return False
    return True


def _in_time_window(current: time, window: tuple[time, time]) -> bool:
    start, end = window
    return start <= current < end if start <= end else current >= start or current < end
