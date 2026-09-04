from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from powermanager_core.models import CommunicationState
from powermanager_core.telemetry import (
    communication_state_for_timestamp,
    normalize_power_state,
    normalize_price_per_kwh,
)


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


def test_freshness_distinguishes_offline_from_stale() -> None:
    now = datetime.now(UTC)
    assert (
        communication_state_for_timestamp(None, now=now, max_age_seconds=120)
        is CommunicationState.OFFLINE
    )
    assert (
        communication_state_for_timestamp(
            now - timedelta(seconds=121), now=now, max_age_seconds=120
        )
        is CommunicationState.STALE
    )


def test_price_normalization_requires_an_explicit_energy_unit() -> None:
    assert normalize_price_per_kwh("150", "EUR/MWh") == (0.15, "EUR/kWh")
    assert normalize_price_per_kwh("0.15", "EUR/kWh") == (0.15, "EUR/kWh")
    assert normalize_price_per_kwh("0.15", "EUR") is None
