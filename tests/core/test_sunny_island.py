from __future__ import annotations

import asyncio
from collections.abc import Sequence
import unittest

from powermanager_core.backends.sma_sunny_island import SunnyIslandClient, SunnyIslandConnectionConfig
from powermanager_core.exceptions import UnsupportedDeviceError
from powermanager_core.models import CommunicationState


class FakeTransport:
    def __init__(self, registers: Sequence[int]) -> None:
        self.registers = registers
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.connected = False

    async def read_input_registers(self, address: int, count: int) -> Sequence[int]:
        assert address == 52
        assert count == 2
        return self.registers


class SunnyIslandTest(unittest.TestCase):
    def test_reads_supported_device_identity(self) -> None:
        async def read() -> tuple[object, object]:
            async with SunnyIslandClient(
                SunnyIslandConnectionConfig("battery"), FakeTransport([0, 9332])
            ) as client:
                return await client.get_device_info(), await client.read_state()

        info, state = asyncio.run(read())
        self.assertEqual(info.model, "Sunny Island SI4.4M-12")
        self.assertIs(state.communication_state, CommunicationState.ONLINE)

    def test_rejects_unsupported_device_identity(self) -> None:
        async def read() -> None:
            async with SunnyIslandClient(
                SunnyIslandConnectionConfig("battery"), FakeTransport([0, 1])
            ) as client:
                with self.assertRaises(UnsupportedDeviceError):
                    await client.get_device_info()

        asyncio.run(read())
