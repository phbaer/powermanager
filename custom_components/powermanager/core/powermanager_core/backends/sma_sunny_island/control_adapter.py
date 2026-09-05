"""Guarded Sunny Island active-power command adapter.

This module provides command encoding and transport boundaries for a future
controller. It deliberately requires explicit opt-in and a clean external-
controller ownership check; constructing it never writes to the inverter.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
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

    async def read_holding_registers(self, address: int, count: int, unit_id: int) -> list[int]:
        """Read consecutive holding registers."""


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


@dataclass(frozen=True, slots=True)
class ControlBaseline:
    """Operating values captured before a bounded external-control session."""

    external_setpoint_mode: int
    communication_control: int


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

    async def enable_external_setpoint_mode(self) -> None:
        """Select external active-power setpoint mode (40210 = 1079)."""
        await self._write_u32(40210, 1079)

    async def set_communication_control(self, enabled: bool) -> None:
        """Enable or disable communication control (40151 = 802/803)."""
        await self._write_u32(40151, 802 if enabled else 803)

    async def capture_baseline(self) -> ControlBaseline:
        """Read operating values that a session must restore afterwards."""
        return ControlBaseline(
            external_setpoint_mode=await self._read_u32(40210),
            communication_control=await self._read_u32(40151),
        )

    async def restore_baseline(self, baseline: ControlBaseline) -> None:
        """Restore and read back the captured operating values.

        Recovery intentionally bypasses the active-control guard: revoking control
        ownership must never prevent the cleanup needed to stop external commands.
        """
        await self._write_u32(40151, baseline.communication_control, require_guard=False)
        await self._write_u32(40210, baseline.external_setpoint_mode, require_guard=False)
        restored_control = await self._read_u32(40151)
        restored_mode = await self._read_u32(40210)
        if (restored_control, restored_mode) != (
            baseline.communication_control,
            baseline.external_setpoint_mode,
        ):
            raise ControlWriteError("Sunny Island operating state did not restore")

    async def restore_normal_operation(self) -> None:
        """Stop external commands and return active-power mode to Off."""
        await self.restore_baseline(ControlBaseline(303, 803))

    async def set_power_bounds(self, minimum_percent: float, maximum_percent: float) -> None:
        """Set documented min/max active-power bounds as percent of nominal power."""
        if not -100 <= minimum_percent <= maximum_percent <= 100:
            raise ControlWriteError("power bounds must satisfy -100 <= min <= max <= 100")
        await self._write_s32(44041, minimum_percent, scale=100)
        await self._write_s32(44039, maximum_percent, scale=100)

    async def configure_failsafe(self, *, timeout_seconds: int, fallback_power_w: float) -> None:
        """Configure apply-fallback behavior and timeout on the inverter."""
        if not 1 <= timeout_seconds <= 1800:
            raise ControlWriteError("fallback timeout must be between 1 and 1800 seconds")
        if not 0 <= fallback_power_w <= 10000:
            raise ControlWriteError("fallback power must be between 0 and 10000 W")
        await self._write_u32(41193, 2507)
        await self._write_u32(41195, timeout_seconds)
        await self._write_s32(44037, fallback_power_w, scale=100)

    async def verify_failsafe(self) -> bool:
        """Verify external mode and apply-fallback settings without writing."""
        mode = await self._read_u32(40210)
        fallback = await self._read_u32(41193)
        timeout = await self._read_u32(41195)
        fallback_power = await self._read_s32(44037, scale=100)
        return (
            mode == 1079
            and fallback == 2507
            and 1 <= timeout <= 1800
            and 0 <= fallback_power <= 10000
        )

    async def _read_u32(self, address: int) -> int:
        values = await self._transport.read_holding_registers(address, 2, self._unit_id)
        if len(values) != 2:
            raise ControlWriteError(f"invalid read length at register {address}")
        return (values[0] << 16) | values[1]

    async def _read_s32(self, address: int, *, scale: float) -> float:
        raw = await self._read_u32(address)
        signed = raw - 2**32 if raw & 0x80000000 else raw
        return signed / scale

    async def _write_u32(self, address: int, value: int, *, require_guard: bool = True) -> None:
        if require_guard and not self._guard.allowed:
            raise ControlWriteError("active control is locked")
        if not 0 <= value <= 0xFFFFFFFF:
            raise ControlWriteError("unsigned register value is out of range")
        await self._transport.write_holding_registers(
            address, [(value >> 16) & 0xFFFF, value & 0xFFFF], self._unit_id
        )

    async def _write_s32(self, address: int, value: float, *, scale: float) -> None:
        if not self._guard.allowed:
            raise ControlWriteError("active control is locked")
        raw = int(round(value * scale))
        if not -(2**31) <= raw <= 2**31 - 1:
            raise ControlWriteError("signed register value is out of range")
        encoded = raw & 0xFFFFFFFF
        await self._transport.write_holding_registers(
            address, [(encoded >> 16) & 0xFFFF, encoded & 0xFFFF], self._unit_id
        )


class ControlCommandSession:
    """Maintain a cyclic setpoint heartbeat until stopped by the caller."""

    def __init__(
        self,
        adapter: SunnyIslandControlAdapter,
        *,
        interval_seconds: float = 0.25,
        max_duration_seconds: float = 900,
        validate_command: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if not 0 < interval_seconds <= 0.5:
            raise ValueError("heartbeat interval must be greater than 0 and at most 0.5 seconds")
        if max_duration_seconds <= 0:
            raise ValueError("maximum command duration must be positive")
        self._adapter = adapter
        self._interval = interval_seconds
        self._max_duration = max_duration_seconds
        self._validate_command = validate_command
        self._active = False

    async def run(self, power_w: float, stop: asyncio.Event) -> None:
        """Run a preflighted session until stopped, then restore the baseline."""
        if self._active:
            raise ControlWriteError("another control command session is already active")
        self._active = True
        baseline: ControlBaseline | None = None
        primary_error: BaseException | None = None
        try:
            if not await self._adapter.verify_failsafe():
                raise ControlWriteError("Sunny Island failsafe preflight did not pass")
            baseline = await self._adapter.capture_baseline()
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self._max_duration
            while not stop.is_set():
                if self._validate_command is not None:
                    await self._validate_command(power_w)
                try:
                    await self._adapter.set_active_power(power_w)
                except TimeoutError as error:
                    raise ControlWriteError("setpoint heartbeat transport timed out") from error
                try:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        return
                    await asyncio.wait_for(stop.wait(), timeout=min(self._interval, remaining))
                except TimeoutError:
                    if loop.time() >= deadline:
                        return
                    continue
        except BaseException as error:
            primary_error = error
            raise
        finally:
            if baseline is not None:
                try:
                    await self._adapter.restore_baseline(baseline)
                except Exception as restore_error:
                    if primary_error is None:
                        raise
                    primary_error.add_note(f"control restoration failed: {restore_error}")
            self._active = False

    async def run_for(self, power_w: float, duration_seconds: float) -> None:
        """Run a bounded command session and restore normal operation afterwards."""
        if not 0 < duration_seconds <= self._max_duration:
            raise ValueError("command duration exceeds the configured safety bound")
        stop = asyncio.Event()
        try:
            await asyncio.wait_for(self.run(power_w, stop), timeout=duration_seconds)
        except TimeoutError:
            return
