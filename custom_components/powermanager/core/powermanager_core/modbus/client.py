"""Read-only TCP transport built on pymodbus.

This module intentionally exposes no Modbus write operation. A separately reviewed
write layer may be introduced only after physical-device safety validation.
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
