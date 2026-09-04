"""Home Assistant adapter for optional dynamic electricity prices."""

from __future__ import annotations

from datetime import UTC, datetime

from .core.powermanager_core.models import CommunicationState, PriceState
from .core.powermanager_core.telemetry import (
    communication_state_for_timestamp,
    normalize_price_per_kwh,
)


class HomeAssistantEntityPriceProvider:
    """Read a current price from an existing numeric Home Assistant entity."""

    def __init__(
        self,
        hass: object,
        entity_id: str | None,
        max_age_seconds: int,
        static_price_per_kwh: float | None = None,
    ) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._max_age_seconds = max_age_seconds
        self._static_price_per_kwh = static_price_per_kwh

    @property
    def configured(self) -> bool:
        return bool(self._entity_id) or self._static_price_per_kwh is not None

    async def read_price_state(self) -> PriceState:
        if self._static_price_per_kwh is not None:
            return PriceState(
                timestamp=datetime.now(UTC),
                price_per_kwh=self._static_price_per_kwh,
                currency="EUR/kWh",
                communication_state=CommunicationState.ONLINE,
            )

        state = self._hass.states.get(self._entity_id) if self._entity_id else None
        value = None
        currency = None
        timestamp = datetime.now(UTC)
        communication = CommunicationState.OFFLINE
        if state is not None and state.state not in ("unknown", "unavailable"):
            updated = state.last_updated
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            if (datetime.now(UTC) - updated).total_seconds() <= self._max_age_seconds:
                normalized = normalize_price_per_kwh(
                    state.state, state.attributes.get("unit_of_measurement")
                )
                if normalized is not None:
                    value, currency = normalized
                timestamp = updated
            communication = communication_state_for_timestamp(
                updated, now=datetime.now(UTC), max_age_seconds=self._max_age_seconds
            )
        return PriceState(
            timestamp=timestamp,
            price_per_kwh=value,
            currency=currency,
            communication_state=communication if value is None else CommunicationState.ONLINE,
        )
