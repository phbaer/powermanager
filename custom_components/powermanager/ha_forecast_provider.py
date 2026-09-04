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
        remaining_pv_entity: str | list[str] | None,
        remaining_load_entity: str | None,
        max_age_seconds: int,
    ) -> None:
        self._hass = hass
        self._remaining_pv_entities = self._entity_ids(remaining_pv_entity)
        self._remaining_load_entity = remaining_load_entity
        self._max_age_seconds = max_age_seconds

    @property
    def configured(self) -> bool:
        return bool(self._remaining_pv_entities or self._remaining_load_entity)

    async def read_forecast_state(self) -> ForecastState:
        """Return only fresh, explicitly unit-labelled remaining-energy values."""
        now = datetime.now(UTC)
        pv, pv_timestamp = self._read_energy_total(self._remaining_pv_entities, now)
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

    def _read_energy_total(
        self, entity_ids: tuple[str, ...], now: datetime
    ) -> tuple[float | None, datetime | None]:
        """Sum separate array forecasts only when every configured value is fresh."""
        if not entity_ids:
            return None, None
        readings = [self._read_energy(entity_id, now) for entity_id in entity_ids]
        timestamps = [timestamp for _, timestamp in readings if timestamp]
        if any(value is None for value, _ in readings):
            return None, max(timestamps) if timestamps else None
        return sum(value for value, _ in readings if value is not None), max(timestamps)

    @staticmethod
    def _entity_ids(value: str | list[str] | None) -> tuple[str, ...]:
        """Normalize legacy scalar options and the multi-entity selector value."""
        if value is None:
            return ()
        return (value,) if isinstance(value, str) else tuple(value)
