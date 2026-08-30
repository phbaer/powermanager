#!/usr/bin/env python3
"""Forward SMA Speedwire multicast datagrams to a unicast UDP endpoint.

This intentionally forwards validated SMA frames unchanged. It does not decode,
modify, or generate Speedwire traffic.
"""

from __future__ import annotations

import argparse
import socket
import sys

SMA_SIGNATURE = bytes.fromhex("534d4100000402a0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default="239.12.255.254")
    parser.add_argument("--port", type=int, default=9522)
    parser.add_argument("--interface", default="0.0.0.0")
    parser.add_argument("--destination-host", required=True)
    parser.add_argument("--destination-port", type=int, default=19522)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.port <= 65535 or not 1 <= args.destination_port <= 65535:
        print("Ports must be between 1 and 65535", file=sys.stderr)
        return 2

    receive = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    receive.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        receive.bind((args.interface, args.port))
        membership = socket.inet_aton(args.group) + socket.inet_aton(args.interface)
        receive.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError as error:
        receive.close()
        print(f"Unable to start relay: {error}", file=sys.stderr)
        return 2

    target = (args.destination_host, args.destination_port)
    print(f"Relaying {args.group}:{args.port} to {target[0]}:{target[1]}", flush=True)
    try:
        while True:
            payload, source = receive.recvfrom(65535)
            if payload.startswith(SMA_SIGNATURE):
                send.sendto(payload, target)
                print(f"Forwarded {len(payload)} bytes from {source[0]}", flush=True)
    except KeyboardInterrupt:
        return 0
    finally:
        send.close()
        receive.close()


if __name__ == "__main__":
    raise SystemExit(main())
