"""Tests for passive Speedwire frame validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from powermanager_core.backends.sma_speedwire import (
    SpeedwireListener,
    decode_energy_meter_records,
    is_sma_frame,
)
from powermanager_core.backends.sma_speedwire.listener import SMA_FRAME_PREFIX


def test_sma_signature_is_required() -> None:
    assert is_sma_frame(SMA_FRAME_PREFIX + b"payload")
    assert not is_sma_frame(b"not an SMA telegram")
    assert not is_sma_frame(SMA_FRAME_PREFIX[:-1])


def test_listener_validates_configuration() -> None:
    with pytest.raises(ValueError):
        SpeedwireListener(port=0)


def test_energy_meter_decoder_rejects_non_meter_frames() -> None:
    with pytest.raises(ValueError, match="0x6069"):
        decode_energy_meter_records(SMA_FRAME_PREFIX + b"\x00" * 64)


def test_energy_meter_decoder_rejects_truncated_record() -> None:
    payload = SMA_FRAME_PREFIX + b"\x00" * 6 + bytes.fromhex("00106069") + b"\x00" * 8
    with pytest.raises(ValueError, match="truncated"):
        decode_energy_meter_records(payload + bytes.fromhex("00010400"))


def test_energy_meter_decoder_handles_captured_home_manager_fixture() -> None:
    fixture = Path("tests/fixtures/speedwire_6069_si44m12.hex").read_text().strip()
    payload = bytes.fromhex(fixture)
    records = decode_energy_meter_records(payload)
    assert len(payload) == 608
    assert len(records) == 59
    assert records[0].obis == 1
    assert records[0].width == 4
    assert records[0].value == 38022
