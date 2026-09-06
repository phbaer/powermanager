from datetime import UTC, datetime, timedelta

from powermanager_core.control import SafetyConfig, validate_intent
from powermanager_core.control.policy import ControlIntent
from powermanager_core.models import BatteryState, CommunicationState, EnergyState, GridState


def test_safety_rejects_disabled_control() -> None:
    now = datetime.now(UTC)
    energy = EnergyState(
        timestamp=now,
        battery=BatteryState(
            timestamp=now,
            battery_soc_percent=50,
            operating_state="Ok",
            communication_state=CommunicationState.ONLINE,
        ),
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
            timestamp=old,
            communication_state=CommunicationState.ONLINE,
            battery_soc_percent=50,
            operating_state="Ok",
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
            operating_state="Ok",
        ),
    )
    intent = ControlIntent("peak", -500, 0, now)
    valid, reason = validate_intent(intent, energy, SafetyConfig(), enabled=True, at=now)
    assert not valid
    assert reason == "battery is at or below effective minimum SoC"


def _online_energy(now: datetime, **battery_kwargs: object) -> EnergyState:
    """Build a complete state suitable for testing an accepted action."""
    values: dict[str, object] = {
        "timestamp": now,
        "communication_state": CommunicationState.ONLINE,
        "battery_soc_percent": 50,
        "operating_state": "Ok",
    }
    values.update(battery_kwargs)
    return EnergyState(
        timestamp=now,
        battery=BatteryState(**values),
        grid=GridState(
            timestamp=now,
            grid_power_w=-1000,
            pv_power_w=2000,
            load_power_w=1000,
            communication_state=CommunicationState.ONLINE,
        ),
    )


def test_safety_rejects_actions_without_soc_and_limits_warning_operation() -> None:
    now = datetime.now(UTC)
    for target, expected in (
        (500, "battery SoC is unavailable"),
        (-500, "battery SoC is unavailable"),
    ):
        energy = _online_energy(now, battery_soc_percent=None)
        valid, reason = validate_intent(
            ControlIntent("rule", target, 0, now), energy, SafetyConfig(), enabled=True, at=now
        )
        assert not valid and reason == expected
    energy = _online_energy(now, operating_state="Warning", event_code=7613)
    valid, reason = validate_intent(
        ControlIntent("rule", 500, 0, now), energy, SafetyConfig(), enabled=True, at=now
    )
    assert valid and reason is None
    valid, reason = validate_intent(
        ControlIntent("rule", -500, 0, now), energy, SafetyConfig(), enabled=True, at=now
    )
    assert not valid and reason == "battery operating state is not allowed"


def test_safety_rejects_unknown_warning_even_for_charge() -> None:
    now = datetime.now(UTC)
    energy = _online_energy(now, operating_state="Warning", event_code=1234)
    valid, reason = validate_intent(
        ControlIntent("rule", 500, 0, now), energy, SafetyConfig(), enabled=True, at=now
    )
    assert not valid and reason == "battery operating state is not allowed"


def test_safety_rejects_max_soc_and_charge_limit() -> None:
    now = datetime.now(UTC)
    for battery_kwargs, expected in (
        ({"battery_soc_percent": 98}, "battery is at or above maximum SoC"),
        ({"charge_limit_w": 100}, "charge target exceeds battery limit"),
    ):
        energy = _online_energy(now, **battery_kwargs)
        valid, reason = validate_intent(
            ControlIntent("rule", 500, 0, now), energy, SafetyConfig(), enabled=True, at=now
        )
        assert not valid and reason == expected


def test_safety_rejects_charge_above_current_pv_surplus() -> None:
    now = datetime.now(UTC)
    energy = EnergyState(
        timestamp=now,
        battery=BatteryState(
            timestamp=now,
            communication_state=CommunicationState.ONLINE,
            battery_soc_percent=50,
            operating_state="Ok",
        ),
        grid=GridState(
            timestamp=now,
            grid_power_w=-1200,
            pv_power_w=3000,
            load_power_w=1000,
            communication_state=CommunicationState.ONLINE,
        ),
    )
    accepted, reason = validate_intent(
        ControlIntent("rule", 1200, 0, now), energy, SafetyConfig(), enabled=True, at=now
    )
    assert accepted and reason is None
    accepted, reason = validate_intent(
        ControlIntent("rule", 1201, 0, now), energy, SafetyConfig(), enabled=True, at=now
    )
    assert not accepted and reason == "charge target exceeds currently available PV surplus"


def test_safety_requires_pv_surplus_telemetry_for_charge() -> None:
    now = datetime.now(UTC)
    energy = _online_energy(now)
    energy = EnergyState(
        timestamp=now,
        battery=energy.battery,
        grid=GridState(
            timestamp=now,
            grid_power_w=-1000,
            communication_state=CommunicationState.ONLINE,
        ),
    )
    accepted, reason = validate_intent(
        ControlIntent("rule", 100, 0, now), energy, SafetyConfig(), enabled=True, at=now
    )
    assert not accepted and reason == "PV surplus telemetry is unavailable"


def test_safety_rejects_stale_optional_sources_and_future_timestamps() -> None:
    now = datetime.now(UTC)
    stale_grid = EnergyState(
        timestamp=now,
        battery=_online_energy(now).battery,
        grid=GridState(
            timestamp=now - timedelta(seconds=121),
            grid_power_w=-500,
            communication_state=CommunicationState.ONLINE,
        ),
    )
    valid, reason = validate_intent(
        ControlIntent("rule", 500, 0, now), stale_grid, SafetyConfig(), enabled=True, at=now
    )
    assert not valid and reason == "grid telemetry is stale"
    future = _online_energy(now + timedelta(seconds=10))
    valid, reason = validate_intent(
        ControlIntent("rule", 500, 0, now), future, SafetyConfig(), enabled=True, at=now
    )
    assert not valid and reason == "energy telemetry timestamp is in the future"


def test_safety_rejects_invalid_configuration() -> None:
    now = datetime.now(UTC)
    energy = _online_energy(now)
    valid, reason = validate_intent(
        ControlIntent("rule", 500, 0, now),
        energy,
        SafetyConfig(minimum_soc_percent=90, maximum_soc_percent=80),
        enabled=True,
        at=now,
    )
    assert not valid and reason == "safety SoC limits are invalid"
