"""Typed, read-only Modbus utilities."""

from .decoder import decode_registers
from .registers import RegisterDataType, RegisterDefinition, RegisterTable

__all__ = ["RegisterDataType", "RegisterDefinition", "RegisterTable", "decode_registers"]
