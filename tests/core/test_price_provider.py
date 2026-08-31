from __future__ import annotations

from datetime import UTC, datetime, timedelta

from powermanager_core.models import CommunicationState, PriceState


def test_price_state_contract_supports_source_timestamp() -> None:
    timestamp = datetime.now(UTC) - timedelta(seconds=5)
    state = PriceState(timestamp=timestamp, price_per_kwh=0.2, currency="EUR/kWh")
    assert state.communication_state is CommunicationState.UNKNOWN
    assert state.timestamp == timestamp
