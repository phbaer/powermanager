"""Deterministic, simulation-only control cycle orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models import EnergyState
from .policy import ControlIntent, ControlRule, evaluate_rules
from .safety import SafetyConfig, validate_intent
from .simulation import SimulationActuator, SimulationRecord
from .watchdog import ControlWatchdog


@dataclass(frozen=True, slots=True)
class ControlDecision:
    """Outcome of one control cycle."""

    intent: ControlIntent | None
    accepted: bool
    reason: str | None
    restore_normal: bool
    simulation_record: SimulationRecord | None = None


class ControlRuntime:
    """Evaluate rules, validate intents, and record accepted simulation actions."""

    def __init__(
        self,
        rules: tuple[ControlRule, ...],
        safety: SafetyConfig | None = None,
        actuator: SimulationActuator | None = None,
        watchdog: ControlWatchdog | None = None,
    ) -> None:
        self._rules = rules
        self._safety = safety or SafetyConfig()
        self._actuator = actuator or SimulationActuator()
        self._watchdog = watchdog or ControlWatchdog()

    async def cycle(
        self, energy: EnergyState, *, at: datetime, enabled: bool
    ) -> ControlDecision:
        """Run one side-effect-free control cycle."""
        watchdog_status = self._watchdog.status(at)
        if watchdog_status.last_heartbeat is not None and watchdog_status.expired:
            return ControlDecision(None, False, "watchdog expired", True)
        intent = evaluate_rules(energy, self._rules, at=at)
        if intent is None:
            return ControlDecision(None, False, "no rule matched", False)
        valid, reason = validate_intent(intent, energy, self._safety, enabled=enabled, at=at)
        if not valid:
            return ControlDecision(intent, False, reason, False)
        self._watchdog.feed(at)
        record = await self._actuator.apply(intent, at=at)
        return ControlDecision(intent, True, None, False, record)

    @property
    def actuator(self) -> SimulationActuator:
        """Expose the simulation trace for inspection."""
        return self._actuator
