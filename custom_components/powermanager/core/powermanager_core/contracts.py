"""Protocols implemented by battery and telemetry backends."""

from __future__ import annotations

from typing import Protocol

from .models import BatteryState, DeviceInfo, GridState, PriceState


class BatteryBackend(Protocol):
    """A local, read-only battery device backend."""

    async def get_device_info(self) -> DeviceInfo:
        """Return stable identity and compatibility information."""

    async def read_battery_state(self) -> BatteryState:
        """Read the latest battery state without changing the device."""


class GridTelemetryProvider(Protocol):
    """An optional local source of grid, PV, and load telemetry."""

    async def read_grid_state(self) -> GridState:
        """Return the latest grid-side telemetry."""


class PriceTelemetryProvider(Protocol):
    """An optional source of current electricity market prices."""

    async def read_price_state(self) -> PriceState:
        """Return the latest market price."""
