"""Unit-normalised models shared by every backend and controller policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .inverters import InverterRole


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
    discharge_limit_soc_percent: float | None = None
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
class PriceState:
    """Current electricity market price in currency units per kWh."""

    timestamp: datetime
    price_per_kwh: float | None = None
    currency: str | None = None
    communication_state: CommunicationState = CommunicationState.UNKNOWN


@dataclass(frozen=True, slots=True)
class ForecastState:
    """Remaining local energy forecast, normalized to kWh.

    These are optional planning inputs only.  A missing or stale forecast never
    causes a policy to infer a value or issue a command.
    """

    timestamp: datetime
    remaining_pv_kwh: float | None = None
    expected_remaining_load_kwh: float | None = None
    communication_state: CommunicationState = CommunicationState.UNKNOWN

    @property
    def expected_surplus_kwh(self) -> float | None:
        """Return forecast PV less forecast load when both are available."""
        if self.remaining_pv_kwh is None or self.expected_remaining_load_kwh is None:
            return None
        return self.remaining_pv_kwh - self.expected_remaining_load_kwh


@dataclass(frozen=True, slots=True)
class InverterState:
    """Normalized telemetry for one PV, battery, or hybrid inverter source."""

    source_id: str
    role: InverterRole
    timestamp: datetime
    generation_power_w: float | None = None
    battery_power_w: float | None = None
    remaining_pv_forecast_kwh: float | None = None
    communication_state: CommunicationState = CommunicationState.UNKNOWN


@dataclass(frozen=True, slots=True)
class EnergyState:
    """Merged, timestamped energy state consumed by later control policies."""

    timestamp: datetime
    battery: BatteryState
    grid: GridState | None = None
    price: PriceState | None = None
    forecast: ForecastState | None = None
