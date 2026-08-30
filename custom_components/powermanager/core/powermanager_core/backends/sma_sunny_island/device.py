"""Read-only SMA Sunny Island backend implementation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...contracts import BatteryBackend
from ...exceptions import UnsupportedDeviceError
from ...modbus.client import PymodbusTcpReadOnlyTransport
from ...modbus.decoder import decode_registers
from ...modbus.registers import RegisterDataType, RegisterDefinition, RegisterTable
from ...models import BatteryState, CommunicationState, DeviceInfo

# The device type is the only currently implemented SMA register. It is kept
# deliberately small until every measurement register is checked against the
# SI4.4M-12 documentation and a physical device.
DEVICE_TYPE = RegisterDefinition(
    key="device_type",
    address=30053,
    table=RegisterTable.INPUT,
    data_type=RegisterDataType.U32,
)
SUPPORTED_DEVICE_TYPES: dict[int, str] = {9332: "Sunny Island SI4.4M-12"}


class InputRegisterTransport(Protocol):
    """The narrow read-only transport surface needed by this backend."""

    async def connect(self) -> None:
        """Open the transport."""

    async def close(self) -> None:
        """Close the transport."""

    async def read_input_registers(self, address: int, count: int) -> Sequence[int]:
        """Read consecutive input registers using a PDU address."""


@dataclass(frozen=True, slots=True)
class SunnyIslandConnectionConfig:
    """Connection settings; no host address is ever hard-coded."""

    host: str
    port: int = 502
    unit_id: int = 3
    timeout_seconds: float = 5.0


class SunnyIslandClient(BatteryBackend):
    """A context-managed, read-only Sunny Island client.

    It has no API for writing registers or enabling external control.
    """

    def __init__(
        self,
        config: SunnyIslandConnectionConfig,
        transport: InputRegisterTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or PymodbusTcpReadOnlyTransport(
            config.host, config.port, config.unit_id, config.timeout_seconds
        )

    async def __aenter__(self) -> SunnyIslandClient:
        await self._transport.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._transport.close()

    async def get_device_info(self) -> DeviceInfo:
        """Read and validate the device type using only an input-register request."""
        registers = await self._transport.read_input_registers(
            DEVICE_TYPE.pdu_address, DEVICE_TYPE.width
        )
        device_type = decode_registers(registers, DEVICE_TYPE)
        if not isinstance(device_type, int) or device_type not in SUPPORTED_DEVICE_TYPES:
            raise UnsupportedDeviceError(f"Unsupported SMA device type: {device_type!r}")
        return DeviceInfo(
            backend="sma_sunny_island",
            model=SUPPORTED_DEVICE_TYPES[device_type],
            serial_number=None,
            firmware_version=None,
            device_type=device_type,
            supported=True,
        )

    async def read_battery_state(self) -> BatteryState:
        """Return the safely available monitor-only state.

        Measurement registers are intentionally not queried until their SI4.4M-12
        address, data type, scaling, and sentinel values have been verified.
        """
        return BatteryState(
            timestamp=datetime.now(UTC),
            communication_state=CommunicationState.ONLINE,
        )

    async def read_state(self) -> BatteryState:
        """Convenience alias for the standalone core API."""
        return await self.read_battery_state()
