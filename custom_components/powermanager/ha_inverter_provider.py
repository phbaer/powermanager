"""Home Assistant adapter for multiple per-inverter telemetry sources."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.core import HomeAssistant

from .core.powermanager_core.inverters import InverterSourceConfig
from .core.powermanager_core.models import CommunicationState, InverterState
from .core.powermanager_core.telemetry import (
    communication_state_for_timestamp,
    normalize_energy_kwh,
    normalize_power_state,
)


class HomeAssistantEntityInverterProvider:
    """Read role-specific power and PV forecast entities for each inverter."""

    def __init__(
        self,
        hass: HomeAssistant,
        sources: tuple[InverterSourceConfig, ...],
        max_age_seconds: int,
    ) -> None:
        self._hass = hass
        self.sources = sources
        self._max_age_seconds = max_age_seconds

    @property
    def configured(self) -> bool:
        """Return whether any per-inverter source is configured."""
        return bool(self.sources)

    async def read_states(self) -> tuple[InverterState, ...]:
        """Read all configured sources without allowing one to mask another."""
        now = datetime.now(UTC)
        states: list[InverterState] = []
        for source in self.sources:
            readings = {
                "generation_power_w": self._read_power(source.generation_power_entity, now),
                "battery_power_w": self._read_power(source.battery_power_entity, now),
                "remaining_pv_forecast_kwh": self._read_forecast(
                    source.remaining_pv_forecast_entity, now
                ),
            }
            timestamps = [
                self._updated(entity_id)
                for entity_id in (
                    source.generation_power_entity,
                    source.battery_power_entity,
                    source.remaining_pv_forecast_entity,
                )
                if entity_id and self._updated(entity_id)
            ]
            latest = max(timestamps) if timestamps else now
            communication = (
                CommunicationState.ONLINE
                if any(value is not None for value in readings.values())
                else communication_state_for_timestamp(
                    latest if timestamps else None,
                    now=now,
                    max_age_seconds=self._max_age_seconds,
                )
            )
            states.append(
                InverterState(
                    source_id=source.source_id,
                    role=source.role,
                    timestamp=latest,
                    communication_state=communication,
                    **readings,
                )
            )
        return tuple(states)

    def _read_power(self, entity_id: str | None, now: datetime) -> float | None:
        state = self._hass.states.get(entity_id) if entity_id else None
        return normalize_power_state(state, now=now, max_age_seconds=self._max_age_seconds)

    def _read_forecast(self, entity_id: str | None, now: datetime) -> float | None:
        if not entity_id:
            return None
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        updated = self._updated(entity_id)
        if updated is None or communication_state_for_timestamp(
            updated, now=now, max_age_seconds=max(self._max_age_seconds, 7200)
        ) is not CommunicationState.ONLINE:
            return None
        return normalize_energy_kwh(state.state, state.attributes.get("unit_of_measurement"))

    def _updated(self, entity_id: str) -> datetime | None:
        state = self._hass.states.get(entity_id)
        if state is None:
            return None
        updated = state.last_updated
        return updated if updated.tzinfo else updated.replace(tzinfo=UTC)
