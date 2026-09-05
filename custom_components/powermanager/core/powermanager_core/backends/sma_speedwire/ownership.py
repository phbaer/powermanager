"""Passive detection of possible competing SMA controllers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ...models import CommunicationState
from .listener import SpeedwireFrame


@dataclass(slots=True)
class ExternalControllerMonitor:
    """Track non-inverter Speedwire senders as a conservative warning signal."""

    sunny_island_host: str
    observed_sources: set[str] = field(default_factory=set)
    inverter_addresses: set[str] = field(default_factory=set)
    listening: bool = False
    last_received_at: datetime | None = None
    max_age_seconds: int = 120

    def observe(self, frame: SpeedwireFrame) -> bool:
        """Record a sender and return true if it may be a competing controller."""
        source_host = frame.source[0]
        self.observed_sources.add(source_host)
        self.last_received_at = frame.received_at
        return source_host not in self._inverter_sources

    @property
    def _inverter_sources(self) -> set[str]:
        return self.inverter_addresses | {self.sunny_island_host}

    def observation_state(self, at: datetime) -> CommunicationState:
        """Distinguish failed observation, silence, and fresh received traffic."""
        if not self.listening:
            return CommunicationState.OFFLINE
        if self.last_received_at is None:
            return CommunicationState.UNKNOWN
        age = (at - self.last_received_at).total_seconds()
        if not 0 <= age <= self.max_age_seconds:
            return CommunicationState.STALE
        return CommunicationState.ONLINE

    def ownership_eligible(self, *, confirmed: bool, at: datetime) -> bool:
        """Require confirmation and fresh observation; silence proves nothing.

        This is only an indicator, never authorization to control hardware.
        Possible competing senders remain latched for the monitor's lifetime.
        """
        return (
            confirmed
            and self.observation_state(at) is CommunicationState.ONLINE
            and not self.possible_external_controller
        )

    @property
    def possible_external_controller(self) -> bool:
        """Whether a non-Sunny-Island sender has been observed."""
        return bool(self.external_sources)

    @property
    def external_sources(self) -> tuple[str, ...]:
        """Return observed sender addresses that are not the configured inverter."""
        return tuple(sorted(self.observed_sources - self._inverter_sources))
