"""Side-effect-free control execution for simulation and dry runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .policy import ControlIntent


@dataclass(frozen=True, slots=True)
class SimulationRecord:
    """A recorded intent that would have been sent to an actuator."""

    intent: ControlIntent
    recorded_at: datetime


class SimulationActuator:
    """Record intents without communicating with an inverter."""

    def __init__(self) -> None:
        self._records: list[SimulationRecord] = []

    async def apply(self, intent: ControlIntent, *, at: datetime) -> SimulationRecord:
        """Record an intent and return its trace entry."""
        record = SimulationRecord(intent=intent, recorded_at=at)
        self._records.append(record)
        return record

    @property
    def records(self) -> tuple[SimulationRecord, ...]:
        """Return an immutable snapshot of recorded intents."""
        return tuple(self._records)
