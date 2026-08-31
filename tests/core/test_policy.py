from datetime import UTC, datetime

from powermanager_core.control import ControlRule, RuleConditions, evaluate_rules
from powermanager_core.models import BatteryState, EnergyState, GridState


def energy(grid: float | None, soc: float = 50) -> EnergyState:
    now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    return EnergyState(
        timestamp=now,
        battery=BatteryState(timestamp=now, battery_soc_percent=soc),
        grid=GridState(timestamp=now, grid_power_w=grid) if grid is not None else None,
    )


def test_highest_priority_matching_rule_wins() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    rules = (
        ControlRule("fallback", 1, RuleConditions(), 500),
        ControlRule("surplus", 10, RuleConditions(grid_power_below_w=-500), 1500, 300),
    )
    result = evaluate_rules(energy(-800), rules, at=at)
    assert result is not None
    assert result.rule_id == "surplus"
    assert result.target_power_w == 1500


def test_missing_grid_data_does_not_match_grid_rule() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    rule = ControlRule("surplus", 1, RuleConditions(grid_power_below_w=-500), 1500)
    assert evaluate_rules(energy(None), (rule,), at=at) is None


def test_discharge_rule_can_require_high_soc_and_grid_import() -> None:
    at = datetime(2026, 1, 1, 20, tzinfo=UTC)
    rule = ControlRule(
        "peak",
        1,
        RuleConditions(grid_power_above_w=500, battery_soc_above_percent=40),
        -1000,
    )
    result = evaluate_rules(energy(1000, soc=60), (rule,), at=at)
    assert result is not None
    assert result.target_power_w == -1000
