"""Passive SMA Speedwire multicast listener.

The listener deliberately exposes validated raw frames only. SMA telegram
layouts vary by device and firmware; decoding measurements belongs in a
separate, fixture-backed layer once captures from the target installation are
available.
"""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from datetime import UTC, datetime

DEFAULT_MULTICAST_GROUP = "239.12.255.254"
DEFAULT_MULTICAST_PORT = 9522

# SMA's documented Speedwire discovery response signature (first 18 bytes).
SMA_DISCOVERY_SIGNATURE = bytes.fromhex("534d4100000402a000000001000200000001")


@dataclass(frozen=True, slots=True)
class SpeedwireFrame:
    """A received Speedwire datagram with its source and reception time."""

    payload: bytes
    source: tuple[str, int]
    received_at: datetime


def is_sma_frame(payload: bytes) -> bool:
    """Return whether a datagram starts with SMA's known protocol signature."""
    return payload.startswith(SMA_DISCOVERY_SIGNATURE)


class SpeedwireListener:
    """Receive SMA multicast datagrams without transmitting or modifying data."""

    def __init__(
        self,
        group: str = DEFAULT_MULTICAST_GROUP,
        port: int = DEFAULT_MULTICAST_PORT,
        interface: str = "0.0.0.0",
        queue_size: int = 256,
    ) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if queue_size < 1:
            raise ValueError("queue_size must be positive")
        self._group = group
        self._port = port
        self._interface = interface
        self._queue: asyncio.Queue[SpeedwireFrame] = asyncio.Queue(maxsize=queue_size)
        self._socket: socket.socket | None = None

    async def __aenter__(self) -> SpeedwireListener:
        self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self.close()

    def start(self) -> None:
        """Bind the UDP socket and join the configured multicast group."""
        if self._socket is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self._interface, self._port))
            membership = socket.inet_aton(self._group) + socket.inet_aton(self._interface)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
            sock.setblocking(False)
        except Exception:
            sock.close()
            raise
        self._socket = sock

    def close(self) -> None:
        """Leave the multicast group and close the socket."""
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    async def receive(self, timeout: float | None = None) -> SpeedwireFrame:
        """Receive the next validated SMA frame, ignoring unrelated datagrams."""
        if self._socket is None:
            raise RuntimeError("listener is not started")
        loop = asyncio.get_running_loop()

        async def _receive() -> SpeedwireFrame:
            while True:
                payload, source = await loop.sock_recvfrom(self._socket, 65535)
                if is_sma_frame(payload):
                    return SpeedwireFrame(payload, source, datetime.now(UTC))

        if timeout is None:
            return await _receive()
        return await asyncio.wait_for(_receive(), timeout)
