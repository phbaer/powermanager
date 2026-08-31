"""Read-only commissioning checks for a future Sunny Island controller."""

from __future__ import annotations

from dataclasses import dataclass

from ...modbus.decoder import decode_registers
from ...modbus.registers import RegisterDataType, RegisterDefinition, RegisterTable


def _reg(
    key: str, address: int, data_type: RegisterDataType, scale: float = 1.0
) -> RegisterDefinition:
    return RegisterDefinition(key, address, RegisterTable.HOLDING, data_type, scale=scale)


EXTERNAL_MODE = _reg("external_mode", 40210, RegisterDataType.U32)
FALLBACK_BEHAVIOR = _reg("fallback_behavior", 41193, RegisterDataType.U32)
TIMEOUT = _reg("timeout", 41195, RegisterDataType.U32)
FALLBACK_POWER = _reg("fallback_power", 44037, RegisterDataType.S32, scale=0.01)


@dataclass(frozen=True, slots=True)
class CommissioningReport:
    """Values required before enabling an active controller."""

    external_mode: int | None
    fallback_behavior: int | None
    timeout_seconds: int | None
    fallback_power_w: float | None

    @property
    def ready_for_control(self) -> bool:
        """Return true only when documented fallback settings are present."""
        return (
            self.external_mode == 1079
            and self.fallback_behavior == 2507
            and self.timeout_seconds is not None
            and 1 <= self.timeout_seconds <= 1800
            and self.fallback_power_w is not None
            and 0 <= self.fallback_power_w <= 10000
        )


async def read_commissioning_report(transport: object, unit_id: int = 3) -> CommissioningReport:
    """Read commissioning registers without changing inverter state."""
    read = transport.read_holding_registers
    values: dict[str, float | int | None] = {}
    for definition in (EXTERNAL_MODE, FALLBACK_BEHAVIOR, TIMEOUT, FALLBACK_POWER):
        words = await read(definition.address, definition.width, unit_id)
        values[definition.key] = decode_registers(words, definition)
    return CommissioningReport(
        external_mode=_as_int(values["external_mode"]),
        fallback_behavior=_as_int(values["fallback_behavior"]),
        timeout_seconds=_as_int(values["timeout"]),
        fallback_power_w=_as_float(values["fallback_power"]),
    )


def _as_int(value: float | int | None) -> int | None:
    return int(value) if value is not None else None


def _as_float(value: float | int | None) -> float | None:
    return float(value) if value is not None else None
