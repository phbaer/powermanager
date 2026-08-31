import asyncio
from datetime import UTC, datetime, timedelta

from powermanager_core.control import ControlRule, ControlRuntime, ControlWatchdog, RuleConditions
from powermanager_core.models import BatteryState, CommunicationState, EnergyState, GridState


def test_runtime_records_accepted_simulation_cycle() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    energy = EnergyState(
        timestamp=at,
        battery=BatteryState(timestamp=at, communication_state=CommunicationState.ONLINE),
        grid=GridState(timestamp=at, grid_power_w=-800),
    )
    runtime = ControlRuntime(
        (ControlRule("surplus", 1, RuleConditions(grid_power_below_w=-500), 1500),)
    )
    decision = asyncio.run(runtime.cycle(energy, at=at, enabled=True))
    assert decision.accepted
    assert decision.simulation_record is not None


def test_runtime_requires_heartbeat_before_cycle() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    energy = EnergyState(timestamp=at, battery=BatteryState(timestamp=at))
    watchdog = ControlWatchdog()
    watchdog.feed(at)
    runtime = ControlRuntime((), watchdog=watchdog)
    decision = asyncio.run(runtime.cycle(energy, at=at + timedelta(seconds=31), enabled=False))
    assert decision.restore_normal


def test_runtime_holds_accepted_intent_until_hold_period_expires() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    energy = EnergyState(
        timestamp=at,
        battery=BatteryState(timestamp=at, communication_state=CommunicationState.ONLINE),
        grid=GridState(timestamp=at, grid_power_w=-800),
    )
    rule = ControlRule("surplus", 1, RuleConditions(grid_power_below_w=-500), 1500, hold_seconds=60)
    runtime = ControlRuntime((rule,))
    first = asyncio.run(runtime.cycle(energy, at=at, enabled=True))
    assert first.accepted
    no_surplus = EnergyState(
        timestamp=at + timedelta(seconds=10),
        battery=BatteryState(
            timestamp=at + timedelta(seconds=10), communication_state=CommunicationState.ONLINE
        ),
        grid=GridState(timestamp=at + timedelta(seconds=10), grid_power_w=100),
    )
    held = asyncio.run(runtime.cycle(no_surplus, at=at + timedelta(seconds=10), enabled=True))
    assert held.accepted
    assert held.intent is not None and held.intent.rule_id == "surplus"


def test_runtime_applies_rule_cooldown() -> None:
    at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    energy = EnergyState(
        timestamp=at,
        battery=BatteryState(timestamp=at, communication_state=CommunicationState.ONLINE),
    )
    rule = ControlRule("always", 1, RuleConditions(), 100, cooldown_seconds=60)
    runtime = ControlRuntime((rule,))
    assert asyncio.run(runtime.cycle(energy, at=at, enabled=True)).accepted
    blocked = asyncio.run(runtime.cycle(energy, at=at + timedelta(seconds=10), enabled=True))
    assert not blocked.accepted and blocked.reason == "rule cooldown active"
