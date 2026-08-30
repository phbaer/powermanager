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

DEVICE_TYPE = RegisterDefinition(
    key="device_type",
    address=30053,
    table=RegisterTable.INPUT,
    data_type=RegisterDataType.U32,
    invalid_values=frozenset({0xFFFFFFFF}),
)
STATUS = RegisterDefinition(
    "status", 30201, RegisterTable.INPUT, RegisterDataType.U32,
    invalid_values=frozenset({0xFFFFFFFF}),
)
BATTERY_SOC = RegisterDefinition(
    "battery_soc", 30845, RegisterTable.INPUT, RegisterDataType.U32,
    invalid_values=frozenset({0xFFFFFFFF}),
)
BATTERY_POWER = RegisterDefinition(
    "battery_power", 30775, RegisterTable.INPUT, RegisterDataType.S32,
    invalid_values=frozenset({0xFFFFFFFF, 0x80000000}),
)
BATTERY_CURRENT = RegisterDefinition(
    "battery_current", 30843, RegisterTable.INPUT, RegisterDataType.S32, scale=0.001,
    invalid_values=frozenset({0xFFFFFFFF, 0x80000000}),
)
BATTERY_VOLTAGE = RegisterDefinition(
    "battery_voltage", 30851, RegisterTable.INPUT, RegisterDataType.U32, scale=0.01,
    invalid_values=frozenset({0xFFFFFFFF}),
)
DISCHARGE_SOC_LIMIT = RegisterDefinition(
    "discharge_soc_limit", 31009, RegisterTable.INPUT, RegisterDataType.U32,
    invalid_values=frozenset({0xFFFFFFFF}),
)
SUPPORTED_DEVICE_TYPES: dict[int, str] = {9332: "Sunny Island SI4.4M-12"}
STATUS_NAMES = {35: "Error", 303: "Off", 307: "Ok", 455: "Warning"}


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
        """Read the documented SI4.4M-12 battery measurements."""
        values: dict[str, float | int | None] = {}
        for register in (
            STATUS,
            BATTERY_SOC,
            BATTERY_POWER,
            BATTERY_CURRENT,
            BATTERY_VOLTAGE,
            DISCHARGE_SOC_LIMIT,
        ):
            raw = await self._transport.read_input_registers(register.pdu_address, register.width)
            values[register.key] = decode_registers(raw, register)
        return BatteryState(
            timestamp=datetime.now(UTC),
            battery_soc_percent=_as_float(values["battery_soc"]),
            battery_power_w=_as_float(values["battery_power"]),
            battery_voltage_v=_as_float(values["battery_voltage"]),
            battery_current_a=_as_float(values["battery_current"]),
            discharge_limit_soc_percent=_as_float(values["discharge_soc_limit"]),
            operating_state=(
                None
                if values["status"] is None
                else STATUS_NAMES.get(values["status"], f"Unknown ({values['status']})")
            ),
            communication_state=CommunicationState.ONLINE,
        )

    async def read_state(self) -> BatteryState:
        """Convenience alias for the standalone core API."""
        return await self.read_battery_state()


def _as_float(value: float | int | None) -> float | None:
    """Normalize decoded numeric values for the domain model."""
    return float(value) if value is not None else None
