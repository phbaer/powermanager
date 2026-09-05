"""SMA Modbus TCP transports built on pymodbus.

Read-only monitoring uses :class:`PymodbusTcpReadOnlyTransport`. The write-capable
transport is a separate type so a monitor cannot accidentally receive a write API.
The write transport is still a low-level primitive and must remain behind the
reviewed command adapter and safety gates.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..exceptions import BackendConnectionError


class PymodbusTcpReadOnlyTransport:
    """A small read-only adapter around :class:`AsyncModbusTcpClient`."""

    def __init__(self, host: str, port: int, unit_id: int, timeout: float = 5.0) -> None:
        self._host = host
        self._port = port
        self._unit_id = unit_id
        self._timeout = timeout
        self._client: object | None = None

    async def connect(self) -> None:
        """Open the TCP connection, importing pymodbus only when needed."""
        try:
            from pymodbus.client import AsyncModbusTcpClient
        except ImportError as error:  # pragma: no cover - exercised in HA dependency setup
            raise BackendConnectionError("pymodbus is not installed") from error

        client = AsyncModbusTcpClient(self._host, port=self._port, timeout=self._timeout)
        try:
            connected = await client.connect()
        except Exception as error:  # pymodbus surfaces transport-specific exceptions.
            message = f"Unable to connect to {self._host}:{self._port}: {error}"
            raise BackendConnectionError(message) from error
        if not connected:
            raise BackendConnectionError(f"Unable to connect to {self._host}:{self._port}")
        self._client = client

    async def close(self) -> None:
        """Close an established client connection."""
        if self._client is not None:
            self._client.close()  # pymodbus deliberately exposes a synchronous close.
            self._client = None

    async def read_input_registers(self, address: int, count: int) -> Sequence[int]:
        """Read input registers or raise a domain-specific connection error."""
        if self._client is None:
            raise BackendConnectionError("Modbus client is not connected")

        try:
            result = await self._client.read_input_registers(
                address, count=count, device_id=self._unit_id
            )
        except Exception as error:  # pymodbus has several transport exception types.
            raise BackendConnectionError(f"Modbus read failed: {error}") from error
        if result.isError() or not hasattr(result, "registers"):
            raise BackendConnectionError(f"Modbus device returned an error for address {address}")
        return result.registers


class PymodbusTcpWriteTransport(PymodbusTcpReadOnlyTransport):
    """Write-capable transport reserved for the guarded control adapter."""

    async def write_holding_registers(
        self, address: int, values: list[int], unit_id: int
    ) -> None:
        """Write registers after the higher-level adapter has authorized it."""
        if self._client is None:
            raise BackendConnectionError("Modbus client is not connected")
        try:
            result = await self._client.write_registers(
                address, values, device_id=unit_id
            )
        except Exception as error:
            raise BackendConnectionError(f"Modbus write failed: {error}") from error
        if result.isError():
            raise BackendConnectionError(f"Modbus device rejected write at address {address}")

    async def read_holding_registers(self, address: int, count: int, unit_id: int) -> list[int]:
        """Read holding registers for guarded control preflight checks."""
        if self._client is None:
            raise BackendConnectionError("Modbus client is not connected")
        try:
            result = await self._client.read_holding_registers(
                address, count=count, device_id=unit_id
            )
        except Exception as error:
            raise BackendConnectionError(f"Modbus read failed: {error}") from error
        if result.isError() or not hasattr(result, "registers"):
            raise BackendConnectionError(f"Modbus device returned an error for address {address}")
        return list(result.registers)
