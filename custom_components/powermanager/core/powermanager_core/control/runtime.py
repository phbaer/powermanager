"""Deterministic, simulation-only control cycle orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

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
    held: bool = False


class ControlRuntime:
    """Evaluate rules, validate intents, and record accepted simulation actions."""

    def __init__(
        self,
        rules: tuple[ControlRule, ...],
        safety: SafetyConfig | None = None,
        actuator: SimulationActuator | None = None,
        watchdog: ControlWatchdog | None = None,
        timezone: tzinfo | None = None,
    ) -> None:
        self._rules = rules
        self._safety = safety or SafetyConfig()
        self._actuator = actuator or SimulationActuator()
        self._watchdog = watchdog or ControlWatchdog()
        self._timezone = timezone
        self._held_intent: ControlIntent | None = None
        self._cooldown_until: datetime | None = None

    async def cycle(
        self, energy: EnergyState, *, at: datetime, enabled: bool
    ) -> ControlDecision:
        """Run one side-effect-free control cycle."""
        watchdog_status = self._watchdog.status(at)
        if watchdog_status.last_heartbeat is not None and watchdog_status.expired:
            self._held_intent = None
            self._cooldown_until = None
            self._watchdog.reset()
            return ControlDecision(None, False, "watchdog expired", True)
        if not enabled:
            self._held_intent = None
            self._cooldown_until = None
            return ControlDecision(None, False, "control is disabled", True)
        held = self._held_intent is not None and at < (
            self._held_intent.evaluated_at + timedelta(seconds=self._held_intent.hold_seconds)
        )
        intent = self._held_intent
        if held:
            candidate = evaluate_rules(energy, self._rules, at=at, timezone=self._timezone)
            if candidate is not None and candidate.rule_id != intent.rule_id:
                held_priority = self._priority_for(intent.rule_id)
                candidate_priority = self._priority_for(candidate.rule_id)
                if candidate_priority > held_priority:
                    intent = candidate
                    held = False
                    self._cooldown_until = None
        if not held:
            held = False
            if self._cooldown_until is not None and at < self._cooldown_until:
                return ControlDecision(None, False, "rule cooldown active", False)
            intent = evaluate_rules(energy, self._rules, at=at, timezone=self._timezone)
        if intent is None:
            return ControlDecision(None, False, "no rule matched", False, held=held)
        valid, reason = validate_intent(intent, energy, self._safety, enabled=enabled, at=at)
        if not valid:
            return ControlDecision(intent, False, reason, False, held=held)
        self._watchdog.feed(at)
        record = await self._actuator.apply(intent, at=at)
        self._held_intent = intent if intent.hold_seconds > 0 else None
        self._cooldown_until = (
            at + timedelta(seconds=intent.cooldown_seconds)
            if intent.cooldown_seconds > 0
            else None
        )
        return ControlDecision(intent, True, None, False, record, held=held)

    @property
    def actuator(self) -> SimulationActuator:
        """Expose the simulation trace for inspection."""
        return self._actuator

    def _priority_for(self, rule_id: str) -> int:
        """Return a rule priority for deterministic hold preemption."""
        return next((rule.priority for rule in self._rules if rule.rule_id == rule_id), -2**31)
