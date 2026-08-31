from datetime import UTC, datetime, timedelta

from powermanager_core.control import SafetyConfig, validate_intent
from powermanager_core.control.policy import ControlIntent
from powermanager_core.models import BatteryState, CommunicationState, EnergyState


def test_safety_rejects_disabled_control() -> None:
    now = datetime.now(UTC)
    energy = EnergyState(
        timestamp=now,
        battery=BatteryState(timestamp=now, communication_state=CommunicationState.ONLINE),
    )
    intent = ControlIntent("rule", 100, 0, now)
    valid, reason = validate_intent(intent, energy, SafetyConfig(), enabled=False, at=now)
    assert not valid
    assert reason == "control is disabled"


def test_safety_rejects_stale_and_out_of_bounds_intents() -> None:
    now = datetime.now(UTC)
    old = now - timedelta(seconds=121)
    energy = EnergyState(
        timestamp=old,
        battery=BatteryState(
            timestamp=old, communication_state=CommunicationState.ONLINE, battery_soc_percent=50
        ),
    )
    intent = ControlIntent("rule", 6000, 0, now)
    valid, reason = validate_intent(intent, energy, SafetyConfig(), enabled=True, at=now)
    assert not valid
    assert reason == "energy telemetry is stale"


def test_safety_respects_dynamic_sunny_island_discharge_floor() -> None:
    now = datetime.now(UTC)
    energy = EnergyState(
        timestamp=now,
        battery=BatteryState(
            timestamp=now,
            communication_state=CommunicationState.ONLINE,
            battery_soc_percent=35,
            discharge_limit_soc_percent=40,
        ),
    )
    intent = ControlIntent("peak", -500, 0, now)
    valid, reason = validate_intent(intent, energy, SafetyConfig(), enabled=True, at=now)
    assert not valid
    assert reason == "battery is at or below effective minimum SoC"
