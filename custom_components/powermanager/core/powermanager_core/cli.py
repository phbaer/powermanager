"""Small standalone diagnostic CLI using the same core as Home Assistant."""

from __future__ import annotations

import argparse
import asyncio
import time

from .backends.sma_speedwire import SpeedwireListener
from .backends.sma_sunny_island import SunnyIslandClient, SunnyIslandConnectionConfig
from .exceptions import PowerManagerError


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(prog="powermanager")
    subcommands = parser.add_subparsers(dest="command", required=True)
    status = subcommands.add_parser("status", help="Read a Sunny Island without changing it")
    status.add_argument("--host", required=True, help="Sunny Island host name or IP address")
    status.add_argument("--port", type=int, default=502, help="Modbus TCP port (default: 502)")
    status.add_argument("--unit-id", type=int, default=3, help="Modbus unit ID (default: 3)")
    status.add_argument("--timeout", type=float, default=5.0, help="TCP timeout in seconds")
    capture = subcommands.add_parser(
        "speedwire-capture", help="Passively capture SMA Speedwire multicast frames"
    )
    capture.add_argument("--duration", type=float, default=30.0, help="Capture duration in seconds")
    capture.add_argument("--group", default="239.12.255.254", help="Multicast group")
    capture.add_argument("--port", type=int, default=9522, help="UDP port (default: 9522)")
    capture.add_argument(
        "--interface", default="0.0.0.0", help="Local interface/address for multicast membership"
    )
    capture.add_argument("--show-hex", action="store_true", help="Print full frame payloads as hex")
    return parser


async def _status(args: argparse.Namespace) -> int:
    config = SunnyIslandConnectionConfig(args.host, args.port, args.unit_id, args.timeout)
    try:
        async with SunnyIslandClient(config) as client:
            info = await client.get_device_info()
            state = await client.read_state()
    except PowerManagerError as error:
        print(f"Unable to read Sunny Island: {error}")
        return 2

    print(info.model or "SMA Sunny Island")
    print(f"Device type:      {info.device_type}")
    print(f"Communication:   {state.communication_state}")
    print(f"Operating state: {state.operating_state}")
    print(f"Battery SoC:      {state.battery_soc_percent} %")
    print(f"Battery power:    {state.battery_power_w} W")
    print(f"Battery current:  {state.battery_current_a} A")
    print(f"Battery voltage:  {state.battery_voltage_v} V")
    print(f"Discharge floor:  {state.discharge_limit_soc_percent} % SoC")
    return 0


async def _speedwire_capture(args: argparse.Namespace) -> int:
    if args.duration <= 0:
        print("Capture duration must be positive")
        return 2
    listener = SpeedwireListener(group=args.group, port=args.port, interface=args.interface)
    try:
        listener.start()
        print(f"Listening on {args.group}:{args.port} for {args.duration:g}s")
        deadline = time.monotonic() + args.duration
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                frame = await listener.receive(timeout=remaining)
            except TimeoutError:
                break
            print(
                f"{frame.received_at.isoformat()} {frame.source[0]}:{frame.source[1]} "
                f"{len(frame.payload)} bytes"
            )
            if args.show_hex:
                print(frame.payload.hex())
    except OSError as error:
        print(f"Unable to listen for Speedwire frames: {error}")
        return 2
    finally:
        listener.close()
    return 0


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    if args.command == "status":
        return asyncio.run(_status(args))
    if args.command == "speedwire-capture":
        return asyncio.run(_speedwire_capture(args))
    raise AssertionError(f"Unhandled command: {args.command}")
