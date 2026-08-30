"""Tests for passive Speedwire frame validation."""

from __future__ import annotations

import pytest
from powermanager_core.backends.sma_speedwire import SpeedwireListener, is_sma_frame
from powermanager_core.backends.sma_speedwire.listener import SMA_FRAME_PREFIX


def test_sma_signature_is_required() -> None:
    assert is_sma_frame(SMA_FRAME_PREFIX + b"payload")
    assert not is_sma_frame(b"not an SMA telegram")
    assert not is_sma_frame(SMA_FRAME_PREFIX[:-1])


def test_listener_validates_configuration() -> None:
    with pytest.raises(ValueError):
        SpeedwireListener(port=0)
