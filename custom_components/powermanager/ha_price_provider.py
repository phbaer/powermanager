"""Home Assistant adapter for optional dynamic electricity prices."""

from __future__ import annotations

from datetime import UTC, datetime

from .core.powermanager_core.models import CommunicationState, PriceState


class HomeAssistantEntityPriceProvider:
    """Read a current price from an existing numeric Home Assistant entity."""

    def __init__(self, hass: object, entity_id: str | None, max_age_seconds: int) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._max_age_seconds = max_age_seconds

    @property
    def configured(self) -> bool:
        return bool(self._entity_id)

    async def read_price_state(self) -> PriceState:
        state = self._hass.states.get(self._entity_id) if self._entity_id else None
        value = None
        currency = None
        if state is not None and state.state not in ("unknown", "unavailable"):
            updated = state.last_updated
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            if (datetime.now(UTC) - updated).total_seconds() <= self._max_age_seconds:
                try:
                    value = float(state.state)
                except (TypeError, ValueError):
                    value = None
                currency = state.attributes.get("unit_of_measurement")
        return PriceState(
            timestamp=datetime.now(UTC),
            price_per_kwh=value,
            currency=currency,
            communication_state=(
                CommunicationState.ONLINE if value is not None else CommunicationState.OFFLINE
            ),
        )
