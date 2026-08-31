import asyncio

from powermanager_core.backends.sma_sunny_island import read_commissioning_report


class FakeTransport:
    values = {40210: [0, 1079], 41193: [0, 2507], 41195: [0, 300], 44037: [9, 10176]}

    async def read_holding_registers(self, address: int, count: int, unit_id: int) -> list[int]:
        return self.values[address]


def test_commissioning_report_is_ready_without_writes() -> None:
    report = asyncio.run(read_commissioning_report(FakeTransport()))
    assert report.ready_for_control
    assert report.fallback_power_w == 6000
