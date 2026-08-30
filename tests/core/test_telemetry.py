from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from powermanager_core.telemetry import normalize_power_state


def test_normalize_power_state_converts_kw() -> None:
    now = datetime.now(UTC)
    state = SimpleNamespace(state="1.5", attributes={"unit_of_measurement": "kW"}, last_updated=now)
    assert normalize_power_state(state, now=now, max_age_seconds=120) == 1500


def test_normalize_power_state_rejects_stale_and_unavailable() -> None:
    now = datetime.now(UTC)
    stale = SimpleNamespace(state="100", attributes={}, last_updated=now - timedelta(seconds=121))
    unavailable = SimpleNamespace(state="unavailable", attributes={}, last_updated=now)
    assert normalize_power_state(stale, now=now, max_age_seconds=120) is None
    assert normalize_power_state(unavailable, now=now, max_age_seconds=120) is None
