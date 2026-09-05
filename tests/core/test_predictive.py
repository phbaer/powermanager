from datetime import UTC, datetime

import pytest
from powermanager_core.control import (
    PredictiveBacktestSample,
    PredictiveInputs,
    PredictivePlanningError,
    backtest_predictive_day,
    plan_predictive_charge,
    replay_predictive_plans,
)


def _inputs(**overrides: object) -> PredictiveInputs:
    values: dict[str, object] = {
        "timestamp": datetime(2026, 6, 1, 8, tzinfo=UTC),
        "horizon_end": datetime(2026, 6, 1, 20, tzinfo=UTC),
        "usable_capacity_kwh": 9.0,
        "battery_soc_percent": 50.0,
        "end_soc_target_percent": 80.0,
        "reserve_soc_percent": 30.0,
        "remaining_pv_kwh": 10.0,
        "remaining_load_kwh": 4.0,
        "forecast_uncertainty_kwh": 1.0,
        "export_capacity_kwh": 0.0,
        "max_charge_power_w": 3000.0,
    }
    values.update(overrides)
    return PredictiveInputs(**values)


def test_planner_defers_when_forecast_can_reach_target() -> None:
    plan = plan_predictive_charge(_inputs())
    assert plan.target_power_w == 0
    assert plan.forecast_surplus_kwh == 5
    assert plan.reason == "preserve_forecast_headroom"
    assert plan.charge_inhibit


def test_planner_preserves_headroom_when_surplus_exceeds_capacity() -> None:
    plan = plan_predictive_charge(_inputs(battery_soc_percent=95.0, remaining_pv_kwh=20.0))
    assert plan.target_power_w == 0
    assert plan.charge_inhibit
    assert plan.reason == "preserve_forecast_headroom"
    assert plan.target_soc_percent <= 95


def test_planner_bounds_grid_charge_by_horizon_and_reported_limit() -> None:
    plan = plan_predictive_charge(
        _inputs(
            battery_soc_percent=30.0,
            end_soc_target_percent=90.0,
            horizon_end=datetime(2026, 6, 1, 10, tzinfo=UTC),
            remaining_pv_kwh=2.0,
            remaining_load_kwh=2.0,
            grid_charge_allowed=True,
            max_charge_power_w=3000.0,
            reported_charge_limit_w=1200.0,
        )
    )
    assert plan.reason == "charge_to_end_target"
    assert plan.target_power_w == 1200


def test_planner_accounts_for_export_capacity_and_uncertainty() -> None:
    plan = plan_predictive_charge(
        _inputs(export_capacity_kwh=4.0, forecast_uncertainty_kwh=0.0)
    )
    assert plan.forecast_surplus_kwh == 6
    assert plan.reason == "grid_charging_disabled"


def test_replay_is_deterministic_and_validates_horizon() -> None:
    inputs = [_inputs(), _inputs(timestamp=datetime(2026, 6, 1, 9, tzinfo=UTC))]
    first = replay_predictive_plans(inputs)
    assert first == replay_predictive_plans(inputs)
    with pytest.raises(PredictivePlanningError, match="horizon"):
        plan_predictive_charge(_inputs(horizon_end=datetime(2026, 6, 1, 8, tzinfo=UTC)))


def test_planner_rejects_nonfinite_inputs() -> None:
    with pytest.raises(PredictivePlanningError, match="finite"):
        plan_predictive_charge(_inputs(remaining_pv_kwh=float("nan")))


def test_backtest_reports_soc_reserve_and_curtailment_outcomes() -> None:
    samples = [
        PredictiveBacktestSample(_inputs(battery_soc_percent=50), 5, 1, 1),
        PredictiveBacktestSample(_inputs(battery_soc_percent=90), 0, 2, 1),
    ]
    result = backtest_predictive_day(samples)
    assert len(result.plans) == 2
    assert result.final_soc_percent >= result.minimum_soc_percent
    assert result.reserve_breaches == 0
    assert result.total_curtailed_surplus_kwh >= 0


def test_backtest_rejects_mismatched_capacity_or_missing_samples() -> None:
    with pytest.raises(PredictivePlanningError, match="at least one"):
        backtest_predictive_day([])
    with pytest.raises(PredictivePlanningError, match="capacity"):
        backtest_predictive_day(
            [
                PredictiveBacktestSample(_inputs(), 0, 0, 1),
                PredictiveBacktestSample(_inputs(usable_capacity_kwh=10), 0, 0, 1),
            ]
        )
