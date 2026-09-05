"""Home Assistant adapter for multiple per-inverter telemetry sources."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.core import HomeAssistant

from .core.powermanager_core.inverters import InverterSourceConfig
from .core.powermanager_core.models import CommunicationState, ForecastState, InverterState
from .core.powermanager_core.telemetry import (
    communication_state_for_timestamp,
    normalize_energy_kwh,
    normalize_power_state,
)


class HomeAssistantEntityInverterProvider:
    """Read directional power, PV, and forecast entities for each inverter."""

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
                "import_power_w": self._read_power(source.import_power_entity, now),
                "export_power_w": self._read_power(source.export_power_entity, now),
                "pv_power_w": self._read_power(source.pv_power_entity, now),
            }
            timestamps = [
                self._updated(entity_id)
                for entity_id in (
                    source.import_power_entity,
                    source.export_power_entity,
                    source.pv_power_entity,
                )
                if entity_id and self._updated(entity_id)
            ]
            forecast = self._read_forecast(source, now)
            if forecast is not None:
                timestamps.append(forecast.timestamp)
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
                    timestamp=latest,
                    forecast=forecast,
                    communication_state=communication,
                    **readings,
                )
            )
        return tuple(states)

    def _read_power(self, entity_id: str | None, now: datetime) -> float | None:
        state = self._hass.states.get(entity_id) if entity_id else None
        return normalize_power_state(state, now=now, max_age_seconds=self._max_age_seconds)

    def _read_forecast(
        self, source: InverterSourceConfig, now: datetime
    ) -> ForecastState | None:
        values: dict[str, float | None] = {}
        timestamps: list[datetime] = []
        for key, entity_id in (
            ("remaining_pv_kwh", source.remaining_pv_forecast_entity),
            ("expected_remaining_load_kwh", source.expected_remaining_load_forecast_entity),
        ):
            if not entity_id:
                values[key] = None
                continue
            state = self._hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable"):
                values[key] = None
                continue
            updated = self._updated(entity_id)
            if updated is not None:
                timestamps.append(updated)
            if updated is None or communication_state_for_timestamp(
                updated, now=now, max_age_seconds=max(self._max_age_seconds, 7200)
            ) is not CommunicationState.ONLINE:
                values[key] = None
                continue
            values[key] = normalize_energy_kwh(
                state.state, state.attributes.get("unit_of_measurement")
            )
        if not timestamps and not any(values.values()):
            return None
        latest = max(timestamps) if timestamps else now
        communication = communication_state_for_timestamp(
            latest, now=now, max_age_seconds=max(self._max_age_seconds, 7200)
        )
        if any(value is not None for value in values.values()):
            communication = CommunicationState.ONLINE
        return ForecastState(timestamp=latest, communication_state=communication, **values)

    def _updated(self, entity_id: str) -> datetime | None:
        state = self._hass.states.get(entity_id)
        if state is None:
            return None
        updated = state.last_updated
        return updated if updated.tzinfo else updated.replace(tzinfo=UTC)
