from __future__ import annotations

import asyncio
import math

import pytest
from powermanager_core.backends.sma_sunny_island import (
    ControlCommandSession,
    ControlWriteError,
    ControlWriteGuard,
    SunnyIslandControlAdapter,
)
from powermanager_core.exceptions import BackendConnectionError


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


class RestoreFailureTransport(FakeTransport):
    """Fail the first recovery write while allowing the second to proceed."""

    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    async def write_holding_registers(self, address: int, values: list[int], unit_id: int) -> None:
        if address == 40151 and not self.failed:
            self.failed = True
            raise TimeoutError("simulated recovery timeout")
        await super().write_holding_registers(address, values, unit_id)


class DisconnectTransport(FakeTransport):
    """Fail the first active-power write while keeping recovery available."""

    async def write_holding_registers(self, address: int, values: list[int], unit_id: int) -> None:
        if address == 40149:
            raise BackendConnectionError("simulated TCP disconnect")
        await super().write_holding_registers(address, values, unit_id)


class WriteOnlyControlTransport(FakeTransport):
    """Expose SMA's write-only communication-control sentinel on readback."""

    def __init__(self) -> None:
        super().__init__()
        self.reads[40151] = [0xFFFF, 0xFFFD]


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
        guard=ControlWriteGuard(
            enabled=True,
            ownership_confirmed=True,
            home_manager_detected=True,
            failsafe_verified=True,
        ),
    )
    with pytest.raises(ControlWriteError):
        asyncio.run(adapter.set_active_power(100))


def test_signed_setpoint_is_encoded_as_two_registers() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True, failsafe_verified=True),
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


def test_setpoint_requires_successful_failsafe_preflight() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    with pytest.raises(ControlWriteError, match="locked"):
        asyncio.run(adapter.set_active_power(100))
    assert asyncio.run(adapter.verify_failsafe())
    asyncio.run(adapter.set_active_power(100))


def test_bounded_session_restores_normal_operation() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    asyncio.run(ControlCommandSession(adapter, interval_seconds=0.5).run_for(100, 0.001))
    assert transport.calls[0][0] == 40149
    assert transport.calls[-1:] == [(40151, [0, 802], 3)]


def test_bounded_session_does_not_rewrite_write_only_control_state() -> None:
    transport = WriteOnlyControlTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    asyncio.run(ControlCommandSession(adapter, interval_seconds=0.5).run_for(100, 0.001))
    assert all(address == 40149 for address, _, _ in transport.calls)


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


def test_session_events_are_bounded_and_sanitized() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    session = ControlCommandSession(adapter, max_duration_seconds=0.001, max_events=2)
    asyncio.run(session.run(100, asyncio.Event()))
    assert len(session.events) == 2
    assert [event.kind for event in session.events] == ["session_expired", "baseline_restored"]
    assert all(event.reason in {None, "max_duration"} for event in session.events)


def test_failed_preflight_is_recorded_without_transport_details() -> None:
    transport = FakeTransport()
    transport.reads[41193] = [0, 2506]
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    session = ControlCommandSession(adapter)
    with pytest.raises(ControlWriteError, match="preflight"):
        asyncio.run(session.run(100, asyncio.Event()))
    assert [(event.kind, event.reason) for event in session.events] == [
        ("session_failed", "preflight")
    ]


def test_session_events_drop_nonfinite_power_values() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    session = ControlCommandSession(adapter)
    with pytest.raises(ControlWriteError, match="exceeds configured bounds"):
        asyncio.run(session.run(math.nan, asyncio.Event()))
    assert session.events[0].kind == "session_started"
    assert session.events[0].power_w is None


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
    assert transport.calls[-1:] == [(40151, [0, 802], 3)]


def test_disconnected_transport_fails_session_and_restores_baseline() -> None:
    transport = DisconnectTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    session = ControlCommandSession(adapter, max_duration_seconds=1)
    with pytest.raises(BackendConnectionError, match="disconnect"):
        asyncio.run(session.run(100, asyncio.Event()))
    assert transport.calls[-1:] == [(40151, [0, 802], 3)]
    assert [(event.kind, event.reason) for event in session.events[-2:]] == [
        ("session_failed", "heartbeat"),
        ("baseline_restored", None),
    ]


def test_unbounded_run_is_stopped_by_maximum_duration() -> None:
    transport = FakeTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    asyncio.run(
        ControlCommandSession(adapter, interval_seconds=0.001, max_duration_seconds=0.002).run(
            100, asyncio.Event()
        )
    )
    assert transport.calls[0][0] == 40149
    assert transport.calls[-1:] == [(40151, [0, 802], 3)]


def test_restore_attempts_mode_after_communication_write_failure() -> None:
    transport = RestoreFailureTransport()
    adapter = SunnyIslandControlAdapter(transport)
    with pytest.raises(ControlWriteError, match="restoration write failed"):
        asyncio.run(adapter.restore_normal_operation())
    assert transport.calls == [(40210, [0, 303], 3)]


def test_restoration_failure_is_recorded_without_exception_text() -> None:
    transport = RestoreFailureTransport()
    adapter = SunnyIslandControlAdapter(
        transport,
        guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
    )
    session = ControlCommandSession(adapter, max_duration_seconds=0.001)
    with pytest.raises(ControlWriteError, match="restoration write failed"):
        asyncio.run(session.run(100, asyncio.Event()))
    assert session.events[-1].kind == "restoration_failed"
    assert session.events[-1].reason == "transport"
    assert "simulated" not in repr(session.events)


def test_overlapping_sessions_are_rejected_and_first_session_restores() -> None:
    async def run_test() -> None:
        transport = FakeTransport()
        adapter = SunnyIslandControlAdapter(
            transport,
            guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
        )
        entered = asyncio.Event()
        release = asyncio.Event()

        async def validate(_: float) -> None:
            entered.set()
            await release.wait()

        session = ControlCommandSession(adapter, validate_command=validate)
        first = asyncio.create_task(session.run(100, asyncio.Event()))
        await entered.wait()
        with pytest.raises(ControlWriteError, match="already active"):
            await session.run_for(100, 0.001)
        release.set()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert transport.calls[-1:] == [(40151, [0, 802], 3)]

    asyncio.run(run_test())


def test_cancellation_restores_baseline() -> None:
    async def run_test() -> None:
        transport = FakeTransport()
        adapter = SunnyIslandControlAdapter(
            transport,
            guard=ControlWriteGuard(enabled=True, ownership_confirmed=True),
        )
        stop = asyncio.Event()
        session = ControlCommandSession(adapter, interval_seconds=0.5)
        task = asyncio.create_task(session.run(100, stop))
        for _ in range(100):
            if transport.calls:
                break
            await asyncio.sleep(0)
        assert transport.calls
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert transport.calls[-1:] == [(40151, [0, 802], 3)]

    asyncio.run(run_test())
