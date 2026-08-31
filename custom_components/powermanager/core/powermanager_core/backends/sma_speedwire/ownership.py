"""Passive detection of possible competing SMA controllers."""

from __future__ import annotations

from dataclasses import dataclass, field

from .listener import SpeedwireFrame


@dataclass(slots=True)
class ExternalControllerMonitor:
    """Track non-inverter Speedwire senders as a conservative warning signal."""

    sunny_island_host: str
    observed_sources: set[str] = field(default_factory=set)

    def observe(self, frame: SpeedwireFrame) -> bool:
        """Record a sender and return true if it may be a competing controller."""
        source_host = frame.source[0]
        self.observed_sources.add(source_host)
        return source_host != self.sunny_island_host

    @property
    def possible_external_controller(self) -> bool:
        """Whether a non-Sunny-Island sender has been observed."""
        return any(source != self.sunny_island_host for source in self.observed_sources)
