"""Load declarative YAML rules into typed policy objects."""

from __future__ import annotations

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
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("rule document must declare version: 1")
    if document.get("enabled", False):
        raise ValueError("control rule execution must remain disabled during simulation")
    raw_rules = document.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("rules must be a list")
    return tuple(_parse_rule(item) for item in raw_rules)


def _parse_rule(raw: Any) -> ControlRule:
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
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
        return ControlRule(
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
                between=window,
            ),
            target_power_w=float(action["target_power_w"]),
            hold_seconds=int(raw.get("hold_seconds", 0)),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"rule {raw['id']!r} has invalid numeric fields") from error


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _parse_time(value: Any) -> time:
    if not isinstance(value, str):
        raise ValueError("rule time must be HH:MM")
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid rule time: {value!r}") from error
