from __future__ import annotations

import asyncio

import pytest
from powermanager_core.backends.sma_sunny_island import (
    ControlCommandSession,
    ControlWriteError,
    ControlWriteGuard,
    SunnyIslandControlAdapter,
)


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[int, list[int], int]] = []
        self.reads = {
            40151: [0, 802],
            40210: [0, 1079],
            41193: [0, 2507],
            41195: [0, 300],
            44037: [9, 10176],
        }

    async def write_holding_registers(self, address: int, values: list[int], unit_id: int) -> None:
        self.calls.append((address, values, unit_id))
        self.reads[address] = values

    async def read_holding_registers(self, address: int, count: int, unit_id: int) -> list[int]:
        return self.reads[address]


def test_control_is_locked_by_default() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(transport)
    with pytest.raises(ControlWriteError):
        asyncio.run(adapter.set_active_power(100))
    assert transport.calls == []


def test_home_manager_detection_blocks_write() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True, home_manager_detected=True),
    )
    with pytest.raises(ControlWriteError):
        asyncio.run(adapter.set_active_power(100))


def test_signed_setpoint_is_encoded_as_two_registers() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    asyncio.run(adapter.set_active_power(-1500))
    assert transport.calls == [(40149, [0xFFFF, 0xFA24], 3)]


def test_mode_and_bounds_use_documented_registers() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    asyncio.run(adapter.enable_external_setpoint_mode())
    asyncio.run(adapter.set_communication_control(True))
    asyncio.run(adapter.set_power_bounds(-50, 75))
    assert transport.calls == [
        (40210, [0, 1079], 3),
        (40151, [0, 802], 3),
        (44041, [0xFFFF, 0xEC78], 3),
        (44039, [0, 7500], 3),
    ]


def test_restore_normal_disables_communication_before_mode() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    asyncio.run(adapter.restore_normal_operation())
    assert transport.calls == [(40151, [0, 803], 3), (40210, [0, 303], 3)]


def test_failsafe_configuration_is_validated_and_guarded() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    asyncio.run(adapter.configure_failsafe(timeout_seconds=300, fallback_power_w=6000))
    assert transport.calls == [
        (41193, [0, 2507], 3),
        (41195, [0, 300], 3),
        (44037, [9, 10176], 3),
    ]
    with pytest.raises(ControlWriteError):
        asyncio.run(adapter.configure_failsafe(timeout_seconds=0, fallback_power_w=0))


def test_failsafe_preflight_is_read_only() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(transport)
    assert asyncio.run(adapter.verify_failsafe())
    assert transport.calls == []


def test_bounded_session_restores_normal_operation() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    asyncio.run(ControlCommandSession(adapter, interval_seconds=0.5).run_for(100, 0.001))
    assert transport.calls[0][0] == 40149
    assert transport.calls[-2:] == [(40151, [0, 802], 3), (40210, [0, 1079], 3)]


def test_session_rejects_failed_failsafe_preflight() -> None:
    transport = FakeTransport()
    transport.reads[41193] = [0, 2506]
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    with pytest.raises(ControlWriteError, match="preflight"):
        asyncio.run(ControlCommandSession(adapter).run_for(100, 0.001))
    assert transport.calls == []


def test_session_revalidates_before_each_heartbeat() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    calls = 0

    async def validate(_: float) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ControlWriteError("telemetry became stale")

    with pytest.raises(ControlWriteError, match="stale"):
        asyncio.run(
            ControlCommandSession(adapter, interval_seconds=0.001, validate_command=validate)
            .run_for(100, 0.01)
        )
    assert calls == 2
    assert transport.calls[-2:] == [(40151, [0, 802], 3), (40210, [0, 1079], 3)]
