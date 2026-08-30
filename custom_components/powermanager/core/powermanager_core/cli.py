"""Small standalone diagnostic CLI using the same core as Home Assistant."""

from __future__ import annotations

import argparse
import asyncio

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
    print("Measurements:    pending register-map verification")
    return 0


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    if args.command == "status":
        return asyncio.run(_status(args))
    raise AssertionError(f"Unhandled command: {args.command}")
