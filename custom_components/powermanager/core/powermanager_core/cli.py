"""Small standalone diagnostic CLI using the same core as Home Assistant."""

from __future__ import annotations

import argparse
import asyncio
import time
from datetime import UTC, datetime

from .backends.sma_speedwire import SpeedwireListener
from .backends.sma_sunny_island import (
    SunnyIslandClient,
    SunnyIslandConnectionConfig,
    read_commissioning_report,
)
from .control import ControlRuntime, load_rules
from .exceptions import PowerManagerError
from .modbus.client import PymodbusTcpReadOnlyTransport
from .models import BatteryState, CommunicationState, EnergyState, GridState


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(prog="powermanager")
    subcommands = parser.add_subparsers(dest="command", required=True)
    status = subcommands.add_parser("status", help="Read a Sunny Island without changing it")
    status.add_argument("--host", required=True, help="Sunny Island host name or IP address")
    status.add_argument("--port", type=int, default=502, help="Modbus TCP port (default: 502)")
    status.add_argument("--unit-id", type=int, default=3, help="Modbus unit ID (default: 3)")
    status.add_argument("--timeout", type=float, default=5.0, help="TCP timeout in seconds")
    commission = subcommands.add_parser(
        "commission", help="Read-only control commissioning preflight"
    )
    commission.add_argument("--host", required=True, help="Sunny Island host name or IP address")
    commission.add_argument("--port", type=int, default=502)
    commission.add_argument("--unit-id", type=int, default=3)
    commission.add_argument("--timeout", type=float, default=5.0)
    capture = subcommands.add_parser(
        "speedwire-capture", help="Passively capture SMA Speedwire multicast frames"
    )
    capture.add_argument("--duration", type=float, default=30.0, help="Capture duration in seconds")
    capture.add_argument("--group", default="239.12.255.254", help="Multicast group")
    capture.add_argument("--port", type=int, default=9522, help="UDP port (default: 9522)")
    capture.add_argument(
        "--interface", default="0.0.0.0", help="Local interface/address for multicast membership"
    )
    simulate = subcommands.add_parser(
        "simulate", help="Evaluate YAML rules without hardware access"
    )
    simulate.add_argument("--rules", required=True, help="YAML rule file")
    simulate.add_argument("--grid-power", type=float, help="Grid power in watts")
    simulate.add_argument("--battery-soc", type=float, default=50.0, help="Battery SoC percent")
    simulate.add_argument("--enabled", action="store_true", help="Enable policy evaluation")
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


async def _commission(args: argparse.Namespace) -> int:
    transport = PymodbusTcpReadOnlyTransport(args.host, args.port, args.unit_id, args.timeout)
    try:
        await transport.connect()
        report = await read_commissioning_report(transport, args.unit_id)
    except PowerManagerError as error:
        print(f"Unable to read commissioning registers: {error}")
        return 2
    finally:
        await transport.close()
    print(f"External mode:       {report.external_mode}")
    print(f"Fallback behavior:   {report.fallback_behavior}")
    print(f"Timeout:             {report.timeout_seconds} s")
    print(f"Fallback power:      {report.fallback_power_w} W")
    print(f"Ready for control:   {report.ready_for_control}")
    return 0 if report.ready_for_control else 1


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


def _simulate(args: argparse.Namespace) -> int:
    try:
        rules = load_rules(args.rules)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Unable to load rules: {error}")
        return 2
    now = datetime.now(UTC)
    energy = EnergyState(
        timestamp=now,
        battery=BatteryState(
            timestamp=now,
            battery_soc_percent=args.battery_soc,
            communication_state=CommunicationState.ONLINE,
        ),
        grid=GridState(timestamp=now, grid_power_w=args.grid_power)
        if args.grid_power is not None
        else None,
    )
    decision = asyncio.run(ControlRuntime(rules).cycle(energy, at=now, enabled=args.enabled))
    print(f"Accepted:       {decision.accepted}")
    print(f"Reason:         {decision.reason or '-'}")
    print(f"Restore normal: {decision.restore_normal}")
    if decision.intent is not None:
        print(f"Rule:           {decision.intent.rule_id}")
        print(f"Target power:   {decision.intent.target_power_w} W")
    return 0


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    if args.command == "status":
        return asyncio.run(_status(args))
    if args.command == "commission":
        return asyncio.run(_commission(args))
    if args.command == "speedwire-capture":
        return asyncio.run(_speedwire_capture(args))
    if args.command == "simulate":
        return _simulate(args)
    raise AssertionError(f"Unhandled command: {args.command}")
