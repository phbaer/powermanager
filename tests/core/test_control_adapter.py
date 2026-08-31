from __future__ import annotations

import asyncio

import pytest
from powermanager_core.backends.sma_sunny_island import (
    ControlWriteError,
    ControlWriteGuard,
    SunnyIslandControlAdapter,
)


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[int, list[int], int]] = []

    async def write_holding_registers(self, address: int, values: list[int], unit_id: int) -> None:
        self.calls.append((address, values, unit_id))


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
