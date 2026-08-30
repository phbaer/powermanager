"""Unit-normalised models shared by every backend and controller policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CommunicationState(StrEnum):
    """Availability of a backend's most recent update."""

    ONLINE = "online"
    OFFLINE = "offline"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Stable backend device identity."""

    backend: str
    model: str | None
    serial_number: str | None
    firmware_version: str | None
    device_type: int | None
    supported: bool


@dataclass(frozen=True, slots=True)
class BatteryState:
    """Battery measurements in SI units, with SoC expressed as percent."""

    timestamp: datetime
    battery_soc_percent: float | None = None
    battery_power_w: float | None = None
    battery_voltage_v: float | None = None
    battery_current_a: float | None = None
    charge_limit_w: float | None = None
    discharge_limit_w: float | None = None
    operating_state: str | None = None
    communication_state: CommunicationState = CommunicationState.UNKNOWN


@dataclass(frozen=True, slots=True)
class GridState:
    """Grid-side measurements in watts; import is positive, export negative."""

    timestamp: datetime
    grid_power_w: float | None = None
    pv_power_w: float | None = None
    load_power_w: float | None = None
    communication_state: CommunicationState = CommunicationState.UNKNOWN


@dataclass(frozen=True, slots=True)
class EnergyState:
    """Merged, timestamped energy state consumed by later control policies."""

    timestamp: datetime
    battery: BatteryState
    grid: GridState | None = None
