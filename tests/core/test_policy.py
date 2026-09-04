from datetime import UTC, datetime

from powermanager_core.control import ControlRule, RuleConditions, evaluate_rules
from powermanager_core.models import BatteryState, EnergyState, ForecastState, GridState, PriceState


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


def test_price_condition_requires_matching_price() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    rule = ControlRule("cheap", 1, RuleConditions(price_below_per_kwh=0.20), 1000)
    priced = energy(-100, soc=60)
    priced = EnergyState(
        timestamp=at,
        battery=priced.battery,
        grid=priced.grid,
        price=PriceState(timestamp=at, price_per_kwh=0.15),
    )
    assert evaluate_rules(priced, (rule,), at=at) is not None


def test_forecast_condition_requires_a_fresh_complete_forecast() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    rule = ControlRule("preserve-headroom", 1, RuleConditions(forecast_surplus_above_kwh=3), 0)
    state = energy(-100, soc=60)
    forecast = ForecastState(
        timestamp=at, remaining_pv_kwh=10, expected_remaining_load_kwh=5
    )
    forecasted = EnergyState(
        timestamp=at, battery=state.battery, grid=state.grid, forecast=forecast
    )
    assert evaluate_rules(forecasted, (rule,), at=at) is not None
