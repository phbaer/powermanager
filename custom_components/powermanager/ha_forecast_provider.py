"""Home Assistant adapter for optional remaining-energy forecasts."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any

from homeassistant.components.recorder import history
from homeassistant.util import dt as dt_util

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
        load_power_entity: str | None = None,
        estimate_remaining_load: bool = False,
        history_days: int = 7,
    ) -> None:
        self._hass = hass
        self._remaining_pv_entities = self._entity_ids(remaining_pv_entity)
        self._remaining_load_entity = remaining_load_entity
        self._max_age_seconds = max_age_seconds
        self._load_power_entity = load_power_entity
        self._estimate_remaining_load = estimate_remaining_load
        self._history_days = history_days
        self._history_cache_key: tuple[datetime.date, int] | None = None
        self._history_cache_value: float | None = None

    @property
    def configured(self) -> bool:
        return bool(
            self._remaining_pv_entities
            or self._remaining_load_entity
            or (self._estimate_remaining_load and self._load_power_entity)
        )

    async def read_forecast_state(self) -> ForecastState:
        """Return only fresh, explicitly unit-labelled remaining-energy values."""
        now = datetime.now(UTC)
        pv, pv_timestamp = self._read_energy_total(self._remaining_pv_entities, now)
        load, load_timestamp = self._read_energy(self._remaining_load_entity, now)
        if load is None and self._estimate_remaining_load and not self._remaining_load_entity:
            load = await self._estimate_remaining_load_kwh()
            load_timestamp = now if load is not None else None
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

    async def _estimate_remaining_load_kwh(self) -> float | None:
        """Average historical load energy from the current time until local midnight."""
        if not self._load_power_entity:
            return None
        local_now = dt_util.now()
        cache_key = (local_now.date(), local_now.hour)
        if cache_key == self._history_cache_key:
            return self._history_cache_value

        day_starts = [
            local_now - timedelta(days=offset)
            for offset in range(1, self._history_days + 1)
        ]
        day_ends = [
            datetime.combine(
                day_start.date() + timedelta(days=1), time.min, tzinfo=local_now.tzinfo
            )
            for day_start in day_starts
        ]
        try:
            values = await self._hass.async_add_executor_job(
                self._read_historical_energy, day_starts, day_ends
            )
        except Exception:  # Recorder availability must not break normal telemetry.
            values = []
        self._history_cache_key = cache_key
        self._history_cache_value = sum(values) / len(values) if values else None
        return self._history_cache_value

    def _read_historical_energy(
        self, starts: list[datetime], ends: list[datetime]
    ) -> list[float]:
        """Integrate each matching historical remainder using Recorder states."""
        if not self._load_power_entity:
            return []
        values: list[float] = []
        for start, end in zip(starts, ends, strict=True):
            states = history.get_significant_states(
                self._hass,
                start,
                end,
                entity_ids=[self._load_power_entity],
                include_start_time_state=True,
                no_attributes=False,
            ).get(self._load_power_entity, [])
            energy = self._integrate_power_states(states, start, end)
            if energy is not None:
                values.append(energy)
        return values if len(values) == self._history_days else []

    @staticmethod
    def _integrate_power_states(
        states: list[Any], start: datetime, end: datetime
    ) -> float | None:
        """Integrate piecewise-constant W/kW readings to kWh over a time window."""
        samples: list[tuple[datetime, float]] = []
        for state in states:
            if state.state in ("unknown", "unavailable"):
                return None
            try:
                value = float(state.state)
            except (TypeError, ValueError):
                return None
            unit = (state.attributes.get("unit_of_measurement") or "W").strip().lower()
            if unit in {"w", "watt", "watts"}:
                power_w = value
            elif unit in {"kw", "kilowatt", "kilowatts"}:
                power_w = value * 1000
            else:
                return None
            timestamp = state.last_updated
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            samples.append((timestamp, power_w))
        if not samples or samples[0][0] > start:
            return None
        energy_wh = 0.0
        for index, (timestamp, power_w) in enumerate(samples):
            interval_start = max(timestamp, start)
            interval_end = min(samples[index + 1][0] if index + 1 < len(samples) else end, end)
            if interval_end > interval_start:
                energy_wh += power_w * (interval_end - interval_start).total_seconds() / 3600
        return energy_wh / 1000

    @staticmethod
    def _entity_ids(value: str | list[str] | None) -> tuple[str, ...]:
        """Normalize legacy scalar options and the multi-entity selector value."""
        if value is None:
            return ()
        return (value,) if isinstance(value, str) else tuple(value)
