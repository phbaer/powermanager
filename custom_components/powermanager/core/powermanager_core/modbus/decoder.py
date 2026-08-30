"""Decode typed Modbus register values without leaking sentinels into models."""

from __future__ import annotations

from collections.abc import Sequence

from ..exceptions import RegisterDecodeError
from .registers import RegisterDataType, RegisterDefinition


def decode_registers(
    registers: Sequence[int], definition: RegisterDefinition
) -> float | int | None:
    """Decode one definition from consecutive 16-bit registers.

    SMA invalid sentinels are compared before scaling and always become ``None``.
    """
    if len(registers) < definition.width:
        raise RegisterDecodeError(
            f"{definition.key} needs {definition.width} registers, got {len(registers)}"
        )
    words = registers[: definition.width]
    if any(word < 0 or word > 0xFFFF for word in words):
        raise RegisterDecodeError(f"{definition.key} contains a non-16-bit register value")

    raw_unsigned = words[0] if definition.width == 1 else (words[0] << 16) | words[1]
    if raw_unsigned in definition.invalid_values:
        return None

    raw = raw_unsigned
    if definition.data_type in (RegisterDataType.S16, RegisterDataType.S32):
        bits = 16 if definition.data_type is RegisterDataType.S16 else 32
        if raw & (1 << (bits - 1)):
            raw -= 1 << bits
    value = raw * definition.scale
    return int(value) if definition.scale == 1 else value
