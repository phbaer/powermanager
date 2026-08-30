from datetime import UTC, datetime, timedelta

import pytest
from powermanager_core.control import ControlWatchdog


def test_watchdog_expires_without_heartbeat() -> None:
    watchdog = ControlWatchdog(timeout_seconds=30)
    at = datetime(2026, 1, 1, tzinfo=UTC)
    assert watchdog.requires_restore_normal(at)
    watchdog.feed(at)
    assert not watchdog.requires_restore_normal(at + timedelta(seconds=29))
    assert watchdog.requires_restore_normal(at + timedelta(seconds=30))


def test_watchdog_rejects_invalid_timeout() -> None:
    with pytest.raises(ValueError):
        ControlWatchdog(timeout_seconds=0)
