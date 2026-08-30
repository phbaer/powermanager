import asyncio
from datetime import UTC, datetime

from powermanager_core.control import ControlIntent, SimulationActuator


def test_simulation_actuator_records_without_side_effects() -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    intent = ControlIntent("surplus", 1500, 300, at)
    actuator = SimulationActuator()
    record = asyncio.run(actuator.apply(intent, at=at))
    assert record.intent == intent
    assert actuator.records == (record,)
