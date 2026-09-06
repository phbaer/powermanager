"""Home Assistant adapter for optional remaining-energy forecasts."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance, history
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
        self._history_cache_key: tuple[datetime.date, int, int] | None = None
        self._history_cache_value: float | None = None
        self._history_cache_profile: tuple[tuple[datetime, float], ...] = ()

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
        estimated_load = False
        estimated_load_profile: tuple[tuple[datetime, float], ...] = ()
        if load is None and self._estimate_remaining_load and not self._remaining_load_entity:
            load = await self._estimate_remaining_load_kwh()
            load_timestamp = now if load is not None else None
            estimated_load = load is not None
            estimated_load_profile = self._history_cache_profile
        timestamps = [timestamp for timestamp in (pv_timestamp, load_timestamp) if timestamp]
        latest = max(timestamps) if timestamps else None
        communication = communication_state_for_timestamp(
            latest, now=now, max_age_seconds=self._max_age_seconds
        )
        if pv is not None or load is not None:
            communication = CommunicationState.ONLINE
        local_now = dt_util.now()
        next_midnight = datetime.combine(
            local_now.date() + timedelta(days=1), time.min, tzinfo=local_now.tzinfo
        )
        remaining_hours = max((next_midnight - local_now).total_seconds() / 3600, 0.25)
        load_power_forecast_w = load * 1000 / remaining_hours if load is not None else None
        if estimated_load_profile:
            load_power_forecast_w = estimated_load_profile[0][1]
        return ForecastState(
            timestamp=latest or now,
            remaining_pv_kwh=pv,
            expected_remaining_load_kwh=load,
            communication_state=communication,
            load_power_forecast_w=load_power_forecast_w,
            load_power_forecast_profile=(
                estimated_load_profile
                if estimated_load_profile
                else _flat_forecast_profile(local_now, next_midnight, load_power_forecast_w)
                if estimated_load and load_power_forecast_w is not None
                else ()
            ),
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
            updated, now=now, max_age_seconds=max(self._max_age_seconds, 7200)
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
        cache_key = (local_now.date(), local_now.hour, local_now.weekday())
        if cache_key == self._history_cache_key:
            return self._history_cache_value

        day_starts = _matching_history_days(local_now, self._history_days)
        day_ends = [
            datetime.combine(
                day_start.date() + timedelta(days=1), time.min, tzinfo=local_now.tzinfo
            )
            for day_start in day_starts
        ]
        try:
            values = await get_instance(self._hass).async_add_executor_job(
                self._read_historical_energy_profile, day_starts, day_ends
            )
        except Exception:  # Recorder availability must not break normal telemetry.
            values = []
        self._history_cache_key = cache_key
        if len(values) != self._history_days:
            self._history_cache_value = None
            self._history_cache_profile = ()
            return None
        self._history_cache_value = sum(value for value, _ in values) / len(values)
        slots = {slot for _, profile in values for slot in profile}
        averaged_slots = {
            slot: sum(profile[slot] for _, profile in values) / len(values)
            for slot in slots
            if all(slot in profile for _, profile in values)
        }
        self._history_cache_profile = _hourly_forecast_profile(
            local_now, averaged_slots
        )
        return self._history_cache_value

    def _read_historical_energy(
        self, starts: list[datetime], ends: list[datetime]
    ) -> list[float]:
        """Integrate each matching historical remainder using Recorder states."""
        return [
            value
            for value, _ in self._read_historical_energy_profile(starts, ends)
        ]

    def _read_historical_energy_profile(
        self, starts: list[datetime], ends: list[datetime]
    ) -> list[tuple[float, dict[int, float]]]:
        """Integrate matching history and build hourly power profiles."""
        if not self._load_power_entity:
            return []
        values: list[tuple[float, dict[int, float]]] = []
        for start, end in zip(starts, ends, strict=True):
            profile_start = datetime.combine(
                start.date(), time.min, tzinfo=start.tzinfo
            )
            states = history.get_significant_states(
                self._hass,
                profile_start,
                end,
                entity_ids=[self._load_power_entity],
                include_start_time_state=True,
                no_attributes=False,
            ).get(self._load_power_entity, [])
            energy = self._integrate_power_states(states, start, end)
            profile = self._hourly_power_profile(states, profile_start, end)
            if energy is not None and profile is not None:
                values.append((energy, profile))
        return values if len(values) == self._history_days else []

    @classmethod
    def _hourly_power_profile(
        cls, states: list[Any], start: datetime, end: datetime
    ) -> dict[int, float] | None:
        """Return average watts per hour slot from piecewise-constant states."""
        profile: dict[int, float] = {}
        cursor = start.replace(minute=0, second=0, microsecond=0)
        while cursor < end:
            hour_end = min(cursor + timedelta(hours=1), end)
            energy = cls._integrate_power_states(states, cursor, hour_end)
            if energy is None:
                return None
            duration_hours = (hour_end - cursor).total_seconds() / 3600
            if duration_hours <= 0:
                return None
            slot = int((cursor - start).total_seconds() // 3600)
            profile[slot] = energy * 1000 / duration_hours
            cursor = hour_end
        return profile

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


def _matching_history_days(local_now: datetime, count: int) -> list[datetime]:
    """Select recent same-weekday samples, with a contiguous fallback.

    Matching weekdays reduce the bias from weekend/weekday load patterns. The
    bounded lookback keeps the estimator seasonal enough without requiring a
    separate climate model; if Recorder has fewer matching days, recent days
    fill the missing samples.
    """
    matching: list[datetime] = []
    fallback: list[datetime] = []
    for offset in range(1, max(56, count) + 1):
        candidate = local_now - timedelta(days=offset)
        if candidate.weekday() == local_now.weekday() and len(matching) < count:
            matching.append(candidate)
        if len(fallback) < count:
            fallback.append(candidate)
        if len(matching) == count:
            break
    if len(matching) == count:
        return matching
    return matching + [day for day in fallback if day not in matching][: count - len(matching)]


def _flat_forecast_profile(
    start: datetime, end: datetime, power_w: float | None
) -> tuple[tuple[datetime, float], ...]:
    """Represent a remaining-energy estimate as hourly forecast samples."""
    if power_w is None:
        return ()
    points: list[tuple[datetime, float]] = []
    cursor = start.replace(minute=0, second=0, microsecond=0)
    while cursor < end:
        points.append((cursor, power_w))
        cursor += timedelta(hours=1)
    return tuple(points)


def _hourly_forecast_profile(
    local_now: datetime, averaged_slots: dict[int, float]
) -> tuple[tuple[datetime, float], ...]:
    """Map averaged historical slots onto today's remaining local hours."""
    if not averaged_slots:
        return ()
    day_start = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
    next_midnight = day_start + timedelta(days=1)
    cursor = local_now.replace(minute=0, second=0, microsecond=0)
    points: list[tuple[datetime, float]] = []
    while cursor < next_midnight:
        slot = int((cursor - day_start).total_seconds() // 3600)
        power_w = averaged_slots.get(slot)
        if power_w is None:
            return ()
        points.append((cursor, power_w))
        cursor += timedelta(hours=1)
    return tuple(points)
