from datetime import UTC, datetime

from powermanager_core.backends.sma_speedwire import ExternalControllerMonitor
from powermanager_core.backends.sma_speedwire.listener import SpeedwireFrame


def test_non_inverter_speedwire_sender_is_warning_signal() -> None:
    monitor = ExternalControllerMonitor("10.0.1.240")
    frame = SpeedwireFrame(b"frame", ("10.0.1.192", 9522), datetime.now(UTC))
    assert monitor.observe(frame)
    assert monitor.possible_external_controller
