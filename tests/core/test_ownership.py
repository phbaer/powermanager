from datetime import UTC, datetime, timedelta

from powermanager_core.backends.sma_speedwire import ExternalControllerMonitor
from powermanager_core.backends.sma_speedwire.listener import SpeedwireFrame


def test_non_inverter_speedwire_sender_is_warning_signal() -> None:
    monitor = ExternalControllerMonitor("10.0.1.240")
    frame = SpeedwireFrame(b"frame", ("10.0.1.192", 9522), datetime.now(UTC))
    assert monitor.observe(frame)
    assert monitor.possible_external_controller


def test_silence_failure_and_stale_observation_never_grant_eligibility() -> None:
    now = datetime.now(UTC)
    monitor = ExternalControllerMonitor("10.0.1.240")
    assert monitor.observation_state(now) == "offline"
    monitor.listening = True
    assert monitor.observation_state(now) == "unknown"
    assert not monitor.ownership_eligible(confirmed=True, at=now)
    monitor.observe(SpeedwireFrame(b"frame", ("10.0.1.240", 9522), now))
    assert monitor.ownership_eligible(confirmed=True, at=now)
    assert not monitor.ownership_eligible(confirmed=False, at=now)
    assert monitor.observation_state(now + timedelta(seconds=121)) == "stale"
    assert not monitor.ownership_eligible(confirmed=True, at=now + timedelta(seconds=121))
    assert not monitor.ownership_eligible(confirmed=True, at=now - timedelta(seconds=1))
    monitor.listening = False
    assert not monitor.ownership_eligible(confirmed=True, at=now)


def test_hostname_addresses_are_excluded_but_competing_sender_stays_latched() -> None:
    now = datetime.now(UTC)
    monitor = ExternalControllerMonitor("sunny-island.local")
    monitor.inverter_addresses = {"10.0.1.240"}
    monitor.listening = True
    assert not monitor.observe(SpeedwireFrame(b"frame", ("10.0.1.240", 9522), now))
    assert monitor.ownership_eligible(confirmed=True, at=now)
    monitor.observe(SpeedwireFrame(b"frame", ("10.0.1.192", 9522), now))
    later = now + timedelta(hours=1)
    monitor.observe(SpeedwireFrame(b"frame", ("10.0.1.240", 9522), later))
    assert monitor.possible_external_controller
    assert not monitor.ownership_eligible(confirmed=True, at=later)
