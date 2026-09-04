"""Home Assistant adapter for optional remaining-energy forecasts."""

from __future__ import annotations

from datetime import UTC, datetime

from .core.powermanager_core.models import CommunicationState, ForecastState
from .core.powermanager_core.telemetry import (
    communication_state_for_timestamp,
    normalize_energy_kwh,
)


class HomeAssistantEntityForecastProvider:
    """Read remaining PV and expected remaining load from HA energy entities."""

    def __init__(
        self,
        hass: object,
        remaining_pv_entity: str | None,
        remaining_load_entity: str | None,
        max_age_seconds: int,
    ) -> None:
        self._hass = hass
        self._remaining_pv_entity = remaining_pv_entity
        self._remaining_load_entity = remaining_load_entity
        self._max_age_seconds = max_age_seconds

    @property
    def configured(self) -> bool:
        return bool(self._remaining_pv_entity or self._remaining_load_entity)

    async def read_forecast_state(self) -> ForecastState:
        """Return only fresh, explicitly unit-labelled remaining-energy values."""
        now = datetime.now(UTC)
        pv, pv_timestamp = self._read_energy(self._remaining_pv_entity, now)
        load, load_timestamp = self._read_energy(self._remaining_load_entity, now)
        timestamps = [timestamp for timestamp in (pv_timestamp, load_timestamp) if timestamp]
        latest = max(timestamps) if timestamps else None
        communication = communication_state_for_timestamp(
            latest, now=now, max_age_seconds=self._max_age_seconds
        )
        if pv is not None or load is not None:
            communication = CommunicationState.ONLINE
        return ForecastState(
            timestamp=latest or now,
            remaining_pv_kwh=pv,
            expected_remaining_load_kwh=load,
            communication_state=communication,
        )

    def _read_energy(
        self, entity_id: str | None, now: datetime
    ) -> tuple[float | None, datetime | None]:
        state = self._hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in ("unknown", "unavailable"):
            return None, None
        updated = state.last_updated
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        if communication_state_for_timestamp(
            updated, now=now, max_age_seconds=self._max_age_seconds
        ) is not CommunicationState.ONLINE:
            return None, updated
        value = normalize_energy_kwh(state.state, state.attributes.get("unit_of_measurement"))
        return value, updated
