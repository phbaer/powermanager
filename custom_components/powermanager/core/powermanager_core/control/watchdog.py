"""Fail-safe watchdog state for future control actuators."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class WatchdogStatus:
    """Observable watchdog state."""

    last_heartbeat: datetime | None
    expires_at: datetime | None
    expired: bool


class ControlWatchdog:
    """Track control heartbeats and request restore-normal on expiry."""

    def __init__(self, timeout_seconds: int = 30) -> None:
        if timeout_seconds < 1:
            raise ValueError("watchdog timeout must be positive")
        self._timeout = timedelta(seconds=timeout_seconds)
        self._last_heartbeat: datetime | None = None

    def feed(self, at: datetime) -> None:
        """Record a successful control cycle heartbeat."""
        self._last_heartbeat = at

    def status(self, at: datetime) -> WatchdogStatus:
        """Return status and whether a restore-normal action is required."""
        expires_at = (
            None if self._last_heartbeat is None else self._last_heartbeat + self._timeout
        )
        return WatchdogStatus(
            last_heartbeat=self._last_heartbeat,
            expires_at=expires_at,
            expired=expires_at is None or at >= expires_at,
        )

    def requires_restore_normal(self, at: datetime) -> bool:
        """Return true when control must fall back to normal inverter behavior."""
        return self.status(at).expired
