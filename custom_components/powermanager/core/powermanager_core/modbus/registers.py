"""Register definitions expressed using their human-facing Modbus addresses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RegisterTable(StrEnum):
    """Supported read-only Modbus tables."""

    INPUT = "input"
    HOLDING = "holding"


class RegisterDataType(StrEnum):
    """Primitive scalar values used in SMA register maps."""

    U16 = "u16"
    S16 = "s16"
    U32 = "u32"
    S32 = "s32"

    @property
    def width(self) -> int:
        """Number of 16-bit Modbus registers occupied by this type."""
        return 1 if self in (self.U16, self.S16) else 2


@dataclass(frozen=True, slots=True)
class RegisterDefinition:
    """A typed register definition.

    SMA assignment tables use ``address`` directly as the register offset accepted
    by its Modbus server. It is therefore intentionally not converted using the
    usual 3xxxx/4xxxx table prefix convention.
    """

    key: str
    address: int
    table: RegisterTable
    data_type: RegisterDataType
    scale: float = 1.0
    unit: str | None = None
    invalid_values: frozenset[int] = frozenset()

    @property
    def width(self) -> int:
        return self.data_type.width

    @property
    def pdu_address(self) -> int:
        """Return the address accepted by an SMA Modbus client."""
        if self.address < 0:
            raise ValueError(f"{self.address} is not a valid register address")
        return self.address
