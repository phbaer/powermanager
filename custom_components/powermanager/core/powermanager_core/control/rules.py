"""Load declarative YAML rules into typed policy objects."""

from __future__ import annotations

import math
from datetime import time
from pathlib import Path
from typing import Any

from .policy import ControlRule, RuleConditions


def load_rules(path: str | Path) -> tuple[ControlRule, ...]:
    """Load and validate a versioned YAML rule document."""
    try:
        import yaml
    except ImportError as error:  # pragma: no cover - packaging configuration issue
        raise RuntimeError("YAML rules require the 'rules' optional dependency") from error
    with Path(path).open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    return parse_rules_document(document)


def parse_rules_document(document: Any) -> tuple[ControlRule, ...]:
    """Validate an already-parsed rule document without performing I/O."""
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("rule document must declare version: 1")
    if document.get("enabled", False):
        raise ValueError("control rule execution must remain disabled during simulation")
    raw_rules = document.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("rules must be a list")
    return tuple(_parse_rule(item) for item in raw_rules)


def _parse_rule(raw: Any) -> ControlRule:
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"].strip():
        raise ValueError("each rule requires a string id")
    when = raw.get("when", {})
    action = raw.get("then", {})
    if not isinstance(when, dict) or not isinstance(action, dict):
        raise ValueError(f"rule {raw['id']!r} has invalid when/then sections")
    between = when.get("between")
    window = None
    if between is not None:
        if not isinstance(between, list) or len(between) != 2:
            raise ValueError(f"rule {raw['id']!r} between must contain two times")
        window = (_parse_time(between[0]), _parse_time(between[1]))
    try:
        rule = ControlRule(
            rule_id=raw["id"],
            priority=int(raw.get("priority", 0)),
            conditions=RuleConditions(
                grid_power_below_w=_optional_float(when.get("grid_power_below_w")),
                grid_power_above_w=_optional_float(when.get("grid_power_above_w")),
                battery_soc_below_percent=_optional_float(
                    when.get("battery_soc_below_percent")
                ),
                battery_soc_above_percent=_optional_float(
                    when.get("battery_soc_above_percent")
                ),
                price_below_per_kwh=_optional_float(when.get("price_below_per_kwh")),
                price_above_per_kwh=_optional_float(when.get("price_above_per_kwh")),
                forecast_surplus_above_kwh=_optional_float(
                    when.get("forecast_surplus_above_kwh")
                ),
                between=window,
            ),
            target_power_w=float(action["target_power_w"]),
            hold_seconds=int(raw.get("hold_seconds", 0)),
            cooldown_seconds=int(raw.get("cooldown_seconds", 0)),
        )
        if rule.hold_seconds < 0 or rule.cooldown_seconds < 0:
            raise ValueError("hold_seconds and cooldown_seconds cannot be negative")
        _validate_conditions(rule)
        return rule
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"rule {raw['id']!r} has invalid fields: {error}") from error


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("numeric values must be finite")
    return number


def _validate_conditions(rule: ControlRule) -> None:
    """Reject contradictory or out-of-domain SoC/price conditions."""
    conditions = rule.conditions
    for threshold in (conditions.battery_soc_below_percent, conditions.battery_soc_above_percent):
        if threshold is not None and not 0 <= threshold <= 100:
            raise ValueError("battery SoC thresholds must be between 0 and 100")
    if (
        conditions.battery_soc_below_percent is not None
        and conditions.battery_soc_above_percent is not None
        and conditions.battery_soc_above_percent >= conditions.battery_soc_below_percent
    ):
        raise ValueError("battery SoC thresholds are contradictory")
    for threshold in (conditions.price_below_per_kwh, conditions.price_above_per_kwh):
        if threshold is not None and threshold < 0:
            raise ValueError("price thresholds cannot be negative")
    if (
        conditions.forecast_surplus_above_kwh is not None
        and conditions.forecast_surplus_above_kwh < 0
    ):
        raise ValueError("forecast surplus threshold cannot be negative")


def _parse_time(value: Any) -> time:
    if not isinstance(value, str):
        raise ValueError("rule time must be HH:MM")
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid rule time: {value!r}") from error
