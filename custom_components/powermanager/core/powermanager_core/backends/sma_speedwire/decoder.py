"""Fixture-backed structural decoding for SMA `0x6069` meter telegrams.

The framing and record sizes are observed from the supported Home Manager.
OBIS semantic names intentionally remain outside this module until they are
verified against a documented record mapping.
"""

from __future__ import annotations

from dataclasses import dataclass

from .listener import SMA_FRAME_PREFIX

ENERGY_METER_PROTOCOL = 0x6069
_PROTOCOL_OFFSET = 16
_RECORDS_OFFSET = 28
_TRAILER_SIZE = 12


@dataclass(frozen=True, slots=True)
class SpeedwireMeterRecord:
    """One unsigned meter record, keyed by its two-byte OBIS identifier."""

    obis: int
    value: int
    width: int


def decode_energy_meter_records(payload: bytes) -> tuple[SpeedwireMeterRecord, ...]:
    """Decode the measured records from a complete SMA `0x6069` telegram.

    The decoder validates exact record boundaries and rejects non-meter or
    truncated payloads.  It does not invent physical units or value meanings.
    """
    if not payload.startswith(SMA_FRAME_PREFIX) or len(payload) < _RECORDS_OFFSET:
        raise ValueError("not a complete SMA Speedwire frame")
    protocol = int.from_bytes(payload[_PROTOCOL_OFFSET : _PROTOCOL_OFFSET + 2], "big")
    if protocol != ENERGY_METER_PROTOCOL:
        raise ValueError("not an SMA 0x6069 energy-meter frame")
    records: list[SpeedwireMeterRecord] = []
    records_end = len(payload) - _TRAILER_SIZE
    if records_end <= _RECORDS_OFFSET:
        raise ValueError("truncated SMA meter payload")
    offset = _RECORDS_OFFSET
    while offset < records_end:
        if records_end - offset < 4:
            raise ValueError("truncated SMA meter record header")
        obis = int.from_bytes(payload[offset : offset + 2], "big")
        width = payload[offset + 2]
        reserved = payload[offset + 3]
        offset += 4
        if width not in (4, 8) or reserved != 0 or records_end - offset < width:
            raise ValueError("invalid or truncated SMA meter record")
        value = int.from_bytes(payload[offset : offset + width], "big")
        records.append(SpeedwireMeterRecord(obis, value, width))
        offset += width
    if offset != records_end:
        raise ValueError("truncated SMA meter record")
    return tuple(records)
