"""Read Home Assistant Energy Dashboard configuration as telemetry defaults."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, valid_entity_id
from homeassistant.util import dt as dt_util

from .core.powermanager_core.inverters import InverterRole, InverterSourceConfig
from .core.powermanager_core.models import (
    CommunicationState,
    ForecastState,
    GridState,
    PriceState,
)
from .core.powermanager_core.telemetry import (
    communication_state_for_timestamp,
    normalize_energy_kwh,
    normalize_power_state,
)
from .ha_price_provider import HomeAssistantEntityPriceProvider

_SLUG_RE = re.compile(r"[^a-z0-9_-]+")


@dataclass(frozen=True, slots=True)
class EnergyDashboardConfiguration:
    """Normalized topology declared by the Energy Dashboard."""

    grid_power_entities: tuple[str, ...] = ()
    price_entity: str | None = None
    static_price_per_kwh: float | None = None
    inverter_sources: tuple[InverterSourceConfig, ...] = ()
    solar_forecast_entries: tuple[tuple[str, tuple[str, ...]], ...] = ()
    missing: tuple[str, ...] = ()
    summary: str = "Energy Dashboard is not configured."

    @property
    def configured(self) -> bool:
        """Return whether the dashboard supplied any energy source."""
        return bool(self.grid_power_entities or self.inverter_sources or self.missing)

    def inverter_yaml(self) -> str:
        """Return imported inverter profiles in the advanced YAML format."""
        import yaml

        if not self.inverter_sources:
            return ""
        return yaml.safe_dump(
            {
                "inverters": [
                    {
                        "id": source.source_id,
                        "role": source.role.value,
                        **(
                            {"generation_power_entity": source.generation_power_entity}
                            if source.generation_power_entity
                            else {}
                        ),
                        **(
                            {"battery_power_entity": source.battery_power_entity}
                            if source.battery_power_entity
                            else {}
                        ),
                    }
                    for source in self.inverter_sources
                ]
            },
            sort_keys=False,
        )


@dataclass(frozen=True, slots=True)
class EnergyDashboardRuntime:
    """A read-only snapshot of configured dashboard telemetry."""

    configuration: EnergyDashboardConfiguration
    grid: GridState | None
    price: PriceState | None
    forecast: ForecastState | None


class HomeAssistantEnergyDashboardProvider:
    """Import dashboard topology while keeping freshness checks local."""

    def __init__(self, hass: HomeAssistant, max_age_seconds: int) -> None:
        self._hass = hass
        self._max_age_seconds = max_age_seconds
        self._forecast_cache: tuple[datetime, ForecastState | None] | None = None

    async def read(self) -> EnergyDashboardRuntime:
        """Read configured dashboard sources and optional solar forecast."""
        configuration = await async_read_energy_dashboard_configuration(self._hass)
        now = datetime.now(UTC)
        grid = self._read_grid(configuration.grid_power_entities, now)
        price = await self._read_price(configuration, now)
        forecast = await self._read_forecast(configuration, now)
        return EnergyDashboardRuntime(configuration, grid, price, forecast)

    def _read_grid(self, entities: tuple[str, ...], now: datetime) -> GridState | None:
        if not entities:
            return None
        readings = [
            (entity_id, self._hass.states.get(entity_id)) for entity_id in entities
        ]
        timestamps = [
            _state_timestamp(state)
            for _, state in readings
            if state is not None and _state_timestamp(state) is not None
        ]
        values = [
            normalize_power_state(state, now=now, max_age_seconds=self._max_age_seconds)
            for _, state in readings
        ]
        if any(value is None for value in values):
            latest = max(timestamps) if timestamps else None
            return GridState(
                timestamp=latest or now,
                communication_state=communication_state_for_timestamp(
                    latest, now=now, max_age_seconds=self._max_age_seconds
                ),
            )
        return GridState(
            timestamp=max(timestamps) if timestamps else now,
            grid_power_w=sum(value for value in values if value is not None),
            communication_state=CommunicationState.ONLINE,
        )

    async def _read_price(
        self, configuration: EnergyDashboardConfiguration, now: datetime
    ) -> PriceState | None:
        if not configuration.price_entity and configuration.static_price_per_kwh is None:
            return None
        provider = HomeAssistantEntityPriceProvider(
            self._hass,
            configuration.price_entity,
            self._max_age_seconds,
            configuration.static_price_per_kwh,
        )
        return await provider.read_price_state()

    async def _read_forecast(
        self, configuration: EnergyDashboardConfiguration, now: datetime
    ) -> ForecastState | None:
        if not configuration.solar_forecast_entries:
            return None
        if self._forecast_cache and now - self._forecast_cache[0] < timedelta(minutes=5):
            return self._forecast_cache[1]
        forecast = await _read_solar_forecast(self._hass, configuration, now)
        self._forecast_cache = (now, forecast)
        return forecast


async def async_read_energy_dashboard_configuration(
    hass: HomeAssistant,
) -> EnergyDashboardConfiguration:
    """Read the Energy Dashboard manager without touching its storage file."""
    try:
        from homeassistant.components.energy.data import async_get_manager

        manager = await async_get_manager(hass)
    except Exception:  # Optional core integration must never break PowerManager.
        return EnergyDashboardConfiguration(summary="Energy Dashboard is unavailable.")
    data = manager.data
    if not data:
        return EnergyDashboardConfiguration(summary="Energy Dashboard is not configured.")
    configuration = _parse_configuration(data)
    missing = list(configuration.missing)
    for source_id, entry_ids in configuration.solar_forecast_entries:
        for entry_id in entry_ids:
            if hass.config_entries.async_get_entry(entry_id) is None:
                missing.append(f"PV {source_id}: forecast config entry {entry_id} is missing")
    if not missing or tuple(missing) == configuration.missing:
        return configuration
    return replace(
        configuration,
        missing=tuple(missing),
        summary=f"{configuration.summary}\n- Missing: {'; '.join(missing)}",
    )


def _parse_configuration(data: dict[str, Any]) -> EnergyDashboardConfiguration:
    grid_entities: list[str] = []
    inverter_sources: list[InverterSourceConfig] = []
    forecast_entries: list[tuple[str, tuple[str, ...]]] = []
    missing: list[str] = []
    status: list[str] = ["Energy Dashboard: configured"]
    used_ids: set[str] = set()
    price_entity: str | None = None
    static_price: float | None = None

    for index, source in enumerate(data.get("energy_sources", []), start=1):
        if not isinstance(source, dict):
            missing.append(f"source {index}: invalid Energy Dashboard entry")
            continue
        source_type = source.get("type")
        power_entity = source.get("stat_rate") or (source.get("power_config") or {}).get(
            "stat_rate"
        )
        if source_type == "grid":
            if isinstance(power_entity, str) and valid_entity_id(power_entity):
                grid_entities.append(power_entity)
                status.append(f"Grid: imported {power_entity}")
            else:
                missing.append(
                    "Grid: no instantaneous power entity (configure stat_rate or power_config)"
                )
            if price_entity is None:
                candidate = source.get("entity_energy_price")
                if isinstance(candidate, str) and valid_entity_id(candidate):
                    price_entity = candidate
                elif source.get("number_energy_price") is not None:
                    try:
                        static_price = float(source["number_energy_price"])
                    except (TypeError, ValueError):
                        missing.append("Grid: invalid Energy Dashboard import price")
        elif source_type == "solar":
            source_id = _source_id(source, index, used_ids)
            forecast_ids = tuple(
                value
                for value in source.get("config_entry_solar_forecast") or ()
                if isinstance(value, str)
            )
            forecast_entries.append((source_id, forecast_ids))
            if isinstance(power_entity, str) and valid_entity_id(power_entity):
                inverter_sources.append(
                    InverterSourceConfig(
                        source_id=source_id,
                        role=InverterRole.PV,
                        generation_power_entity=power_entity,
                    )
                )
                status.append(
                    f"PV {source_id}: imported {power_entity}"
                    + (
                        "; forecast " + ", ".join(forecast_ids)
                        if forecast_ids
                        else "; no forecast configured"
                    )
                )
                if not forecast_ids:
                    missing.append(f"PV {source_id}: no solar forecast configured")
            else:
                missing.append(f"PV {source_id}: no instantaneous generation entity")
        elif source_type == "battery":
            source_id = _source_id(source, index, used_ids, prefix="battery")
            if isinstance(power_entity, str) and valid_entity_id(power_entity):
                inverter_sources.append(
                    InverterSourceConfig(
                        source_id=source_id,
                        role=InverterRole.BATTERY,
                        battery_power_entity=power_entity,
                    )
                )
                status.append(f"Battery {source_id}: imported {power_entity}")
            else:
                missing.append(f"Battery {source_id}: no signed battery power entity")

    if not grid_entities:
        missing.append("Grid: PowerManager requires a fresh signed grid-power entity")
    if not inverter_sources:
        missing.append("Inverters: no usable PV or battery sources were imported")
    if missing:
        status.append("Missing: " + "; ".join(missing))
    return EnergyDashboardConfiguration(
        grid_power_entities=tuple(dict.fromkeys(grid_entities)),
        price_entity=price_entity,
        static_price_per_kwh=static_price,
        inverter_sources=tuple(inverter_sources),
        solar_forecast_entries=tuple(forecast_entries),
        missing=tuple(missing),
        summary="\n".join(f"- {line}" for line in status),
    )


def _source_id(
    source: dict[str, Any], index: int, used_ids: set[str], prefix: str = "pv"
) -> str:
    raw = source.get("name") or source.get("stat_rate") or f"{prefix}_{index}"
    candidate = _SLUG_RE.sub("_", str(raw).lower()).strip("_-") or f"{prefix}_{index}"
    if not candidate[0].isalnum():
        candidate = f"{prefix}_{candidate}"
    source_id = candidate[:64]
    suffix = 2
    while source_id in used_ids:
        suffix_text = f"_{suffix}"
        source_id = f"{candidate[:64 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    used_ids.add(source_id)
    return source_id


async def _read_solar_forecast(
    hass: HomeAssistant,
    configuration: EnergyDashboardConfiguration,
    now: datetime,
) -> ForecastState | None:
    """Resolve configured Energy Dashboard solar forecasts into remaining kWh."""
    try:
        from homeassistant.components.energy.websocket_api import async_get_energy_platforms

        platforms = await async_get_energy_platforms(hass)
    except Exception:  # Optional forecast platforms must never break telemetry.
        return None
    total_wh = 0.0
    current_power_w = 0.0
    forecast_sources = 0
    current_power_sources = 0
    profile_power_w: dict[datetime, float] = {}
    latest = now
    found = False
    for _, config_entry_ids in configuration.solar_forecast_entries:
        for config_entry_id in config_entry_ids:
            entry = hass.config_entries.async_get_entry(config_entry_id)
            if entry is None or entry.domain not in platforms:
                continue
            try:
                forecast = await platforms[entry.domain](hass, config_entry_id)
            except Exception:  # Forecast integrations are optional inputs.
                continue
            if not forecast:
                continue
            forecast_sources += 1
            samples: list[tuple[datetime, float]] = []
            for timestamp_text, value in forecast.get("wh_hours", {}).items():
                timestamp = dt_util.parse_datetime(timestamp_text)
                if timestamp is None:
                    continue
                timestamp = timestamp.astimezone(UTC)
                if timestamp < now - timedelta(hours=1):
                    continue
                try:
                    energy_wh = float(value)
                except (TypeError, ValueError):
                    continue
                total_wh += energy_wh
                samples.append((timestamp, energy_wh))
                latest = max(latest, timestamp)
                found = True
            current_power = _current_forecast_power_w(samples, now)
            if current_power is not None:
                current_power_w += current_power
                current_power_sources += 1
            for timestamp, power_w in _forecast_profile_power_w(samples, now=now):
                profile_power_w[timestamp] = profile_power_w.get(timestamp, 0.0) + power_w
    if not found:
        return None
    return ForecastState(
        timestamp=latest,
        remaining_pv_kwh=normalize_energy_kwh(total_wh, "Wh"),
        pv_power_forecast_w=(
            current_power_w if current_power_sources == forecast_sources else None
        ),
        pv_power_forecast_profile=tuple(sorted(profile_power_w.items())),
        communication_state=CommunicationState.ONLINE,
    )


def _state_timestamp(state: Any) -> datetime | None:
    if state is None:
        return None
    timestamp = state.last_updated
    return timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)


def _current_forecast_power_w(
    samples: list[tuple[datetime, float]], now: datetime
) -> float | None:
    """Return the forecast power for the interval containing ``now``."""
    samples.sort()
    for index, (timestamp, energy_wh) in enumerate(samples):
        next_timestamp = (
            samples[index + 1][0]
            if index + 1 < len(samples)
            else timestamp + timedelta(hours=1)
        )
        interval_hours = (next_timestamp - timestamp).total_seconds() / 3600
        if interval_hours > 0 and timestamp <= now < next_timestamp:
            return energy_wh / interval_hours
    return None


def _forecast_profile_power_w(
    samples: list[tuple[datetime, float]],
    *,
    now: datetime | None = None,
    horizon: timedelta = timedelta(hours=24),
) -> tuple[tuple[datetime, float], ...]:
    """Convert forecast interval energy into a bounded power profile.

    Energy Dashboard providers may expose several days of forecast intervals.
    PowerManager only needs the near-term profile, and keeping it bounded also
    prevents the profile attribute from exceeding Home Assistant Recorder's
    16 KiB attribute limit.
    """
    samples.sort()
    profile: list[tuple[datetime, float]] = []
    end = now + horizon if now is not None else None
    for index, (timestamp, energy_wh) in enumerate(samples):
        if end is not None and timestamp > end:
            break
        next_timestamp = (
            samples[index + 1][0]
            if index + 1 < len(samples)
            else timestamp + timedelta(hours=1)
        )
        if end is not None:
            next_timestamp = min(next_timestamp, end)
        interval_hours = (next_timestamp - timestamp).total_seconds() / 3600
        if interval_hours > 0:
            profile.append((timestamp, energy_wh / interval_hours))
    return tuple(profile)
