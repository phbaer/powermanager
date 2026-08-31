"""Guarded Sunny Island active-power command adapter.

This module provides command encoding and transport boundaries for a future
controller. It deliberately requires explicit opt-in and a clean external-
controller ownership check; constructing it never writes to the inverter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...exceptions import PowerManagerError


class ControlWriteError(PowerManagerError):
    """A command was rejected before or during transport."""


class HoldingRegisterWriteTransport(Protocol):
    """Minimal transport surface for guarded writes."""

    async def write_holding_registers(
        self, address: int, values: list[int], unit_id: int
    ) -> None:
        """Write consecutive holding registers."""


@dataclass(frozen=True, slots=True)
class ControlWriteGuard:
    """Explicit gates required before any physical command is allowed."""

    enabled: bool = False
    ownership_confirmed: bool = False
    home_manager_detected: bool = False

    @property
    def allowed(self) -> bool:
        """Return whether all software gates permit a write."""
        return self.enabled and self.ownership_confirmed and not self.home_manager_detected


class SunnyIslandControlAdapter:
    """Encode and send active-power setpoints behind an explicit safety guard."""

    def __init__(
        self,
        transport: HoldingRegisterWriteTransport,
        *,
        unit_id: int = 3,
        max_power_w: float = 5000,
        guard: ControlWriteGuard | None = None,
    ) -> None:
        self._transport = transport
        self._unit_id = unit_id
        self._max_power_w = max_power_w
        self._guard = guard or ControlWriteGuard()

    async def set_active_power(self, power_w: float) -> None:
        """Send one signed-watt setpoint to register 40149.

        The caller remains responsible for the documented cyclic heartbeat and
        inverter-side timeout. This method is intentionally not integrated into
        the Home Assistant coordinator yet.
        """
        if not self._guard.allowed:
            raise ControlWriteError(
                "active control is locked: enablement, ownership confirmation, "
                "and Home Manager exclusion are required"
            )
        if not -self._max_power_w <= power_w <= self._max_power_w:
            raise ControlWriteError("active-power setpoint exceeds configured bounds")
        raw = int(round(power_w))
        encoded = raw & 0xFFFFFFFF
        await self._transport.write_holding_registers(
            40149, [(encoded >> 16) & 0xFFFF, encoded & 0xFFFF], self._unit_id
        )
