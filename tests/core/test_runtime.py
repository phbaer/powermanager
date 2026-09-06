import asyncio
from datetime import UTC, datetime, timedelta

from powermanager_core.control import ControlRule, ControlRuntime, ControlWatchdog, RuleConditions
from powermanager_core.models import BatteryState, CommunicationState, EnergyState, GridState


def test_runtime_records_accepted_simulation_cycle() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    energy = EnergyState(
        timestamp=at,
        battery=BatteryState(
            timestamp=at,
            battery_soc_percent=50,
            operating_state="Ok",
            communication_state=CommunicationState.ONLINE,
        ),
        grid=GridState(
            timestamp=at,
            grid_power_w=-1500,
            pv_power_w=2500,
            load_power_w=1000,
            communication_state=CommunicationState.ONLINE,
        ),
    )
    runtime = ControlRuntime(
        (ControlRule("surplus", 1, RuleConditions(grid_power_below_w=-500), 1500),)
    )
    decision = asyncio.run(runtime.cycle(energy, at=at, enabled=True))
    assert decision.accepted
    assert decision.simulation_record is not None


def test_runtime_requires_heartbeat_before_cycle() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    energy = EnergyState(
        timestamp=at,
        battery=BatteryState(timestamp=at, battery_soc_percent=50, operating_state="Ok"),
    )
    watchdog = ControlWatchdog()
    watchdog.feed(at)
    runtime = ControlRuntime((), watchdog=watchdog)
    decision = asyncio.run(runtime.cycle(energy, at=at + timedelta(seconds=31), enabled=False))
    assert decision.restore_normal


def test_runtime_holds_accepted_intent_until_hold_period_expires() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    energy = EnergyState(
        timestamp=at,
        battery=BatteryState(
            timestamp=at,
            battery_soc_percent=50,
            operating_state="Ok",
            communication_state=CommunicationState.ONLINE,
        ),
        grid=GridState(
            timestamp=at,
            grid_power_w=-1500,
            pv_power_w=2500,
            load_power_w=1000,
            communication_state=CommunicationState.ONLINE,
        ),
    )
    rule = ControlRule("surplus", 1, RuleConditions(grid_power_below_w=-500), 1500, hold_seconds=60)
    runtime = ControlRuntime((rule,))
    first = asyncio.run(runtime.cycle(energy, at=at, enabled=True))
    assert first.accepted
    no_surplus = EnergyState(
        timestamp=at + timedelta(seconds=10),
        battery=BatteryState(
            timestamp=at + timedelta(seconds=10),
            battery_soc_percent=50,
            operating_state="Ok",
            communication_state=CommunicationState.ONLINE,
        ),
        grid=GridState(
            timestamp=at + timedelta(seconds=10),
            grid_power_w=100,
            pv_power_w=1000,
            load_power_w=1000,
            communication_state=CommunicationState.ONLINE,
        ),
    )
    held = asyncio.run(runtime.cycle(no_surplus, at=at + timedelta(seconds=10), enabled=True))
    assert not held.accepted
    assert held.reason == "charge target exceeds currently available PV surplus"
    assert held.held
    assert held.intent is not None and held.intent.rule_id == "surplus"


def test_runtime_applies_rule_cooldown() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    energy = EnergyState(
        timestamp=at,
        battery=BatteryState(
            timestamp=at,
            battery_soc_percent=50,
            operating_state="Ok",
            communication_state=CommunicationState.ONLINE,
        ),
        grid=GridState(
            timestamp=at,
            grid_power_w=-1000,
            pv_power_w=2000,
            load_power_w=1000,
            communication_state=CommunicationState.ONLINE,
        ),
    )
    rule = ControlRule("always", 1, RuleConditions(), 100, cooldown_seconds=60)
    runtime = ControlRuntime((rule,))
    assert asyncio.run(runtime.cycle(energy, at=at, enabled=True)).accepted
    blocked = asyncio.run(runtime.cycle(energy, at=at + timedelta(seconds=10), enabled=True))
    assert not blocked.accepted and blocked.reason == "rule cooldown active"


def test_higher_priority_rule_preempts_a_held_rule() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    battery = BatteryState(
        timestamp=at,
        battery_soc_percent=50,
        operating_state="Ok",
        communication_state=CommunicationState.ONLINE,
    )
    rules = (
        ControlRule("low", 10, RuleConditions(grid_power_below_w=-500), 500, hold_seconds=60),
        ControlRule("high", 20, RuleConditions(grid_power_below_w=-1000), 1500, hold_seconds=60),
    )
    runtime = ControlRuntime(rules)
    first = EnergyState(
        timestamp=at,
        battery=battery,
        grid=GridState(
            timestamp=at,
            grid_power_w=-800,
            pv_power_w=1800,
            load_power_w=1000,
            communication_state=CommunicationState.ONLINE,
        ),
    )
    assert asyncio.run(runtime.cycle(first, at=at, enabled=True)).intent.rule_id == "low"
    second_at = at + timedelta(seconds=10)
    second = EnergyState(
        timestamp=second_at,
        battery=BatteryState(
            timestamp=second_at,
            battery_soc_percent=50,
            operating_state="Ok",
            communication_state=CommunicationState.ONLINE,
        ),
        grid=GridState(
            timestamp=second_at,
            grid_power_w=-1500,
            pv_power_w=2500,
            load_power_w=1000,
            communication_state=CommunicationState.ONLINE,
        ),
    )
    decision = asyncio.run(runtime.cycle(second, at=second_at, enabled=True))
    assert decision.intent is not None and decision.intent.rule_id == "high"
    assert not decision.held


def test_disabling_runtime_requests_restore_and_clears_hold() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    energy = EnergyState(
        timestamp=at,
        battery=BatteryState(
            timestamp=at,
            battery_soc_percent=50,
            operating_state="Ok",
            communication_state=CommunicationState.ONLINE,
        ),
        grid=GridState(
            timestamp=at,
            grid_power_w=-1000,
            pv_power_w=2000,
            load_power_w=1000,
            communication_state=CommunicationState.ONLINE,
        ),
    )
    runtime = ControlRuntime((ControlRule("always", 1, RuleConditions(), 100, hold_seconds=60),))
    assert asyncio.run(runtime.cycle(energy, at=at, enabled=True)).accepted
    disabled = asyncio.run(runtime.cycle(energy, at=at + timedelta(seconds=1), enabled=False))
    assert disabled.restore_normal and disabled.reason == "control is disabled"
    recovered = asyncio.run(runtime.cycle(energy, at=at + timedelta(seconds=2), enabled=True))
    assert recovered.accepted


def test_watchdog_expiry_recovers_on_next_cycle() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    energy = EnergyState(
        timestamp=at,
        battery=BatteryState(
            timestamp=at,
            battery_soc_percent=50,
            operating_state="Ok",
            communication_state=CommunicationState.ONLINE,
        ),
        grid=GridState(
            timestamp=at,
            grid_power_w=-1000,
            pv_power_w=2000,
            load_power_w=1000,
            communication_state=CommunicationState.ONLINE,
        ),
    )
    runtime = ControlRuntime(
        (ControlRule("always", 1, RuleConditions(), 100),),
        watchdog=ControlWatchdog(timeout_seconds=30),
    )
    assert asyncio.run(runtime.cycle(energy, at=at, enabled=True)).accepted
    expired = asyncio.run(runtime.cycle(energy, at=at + timedelta(seconds=31), enabled=True))
    assert expired.restore_normal
    recovered = asyncio.run(runtime.cycle(energy, at=at + timedelta(seconds=32), enabled=True))
    assert recovered.accepted
