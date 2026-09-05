"""Configuration models for normalized multi-inverter telemetry."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml

_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_ENTITY_FIELDS = (
    "import_power_entity",
    "export_power_entity",
    "pv_power_entity",
    "remaining_pv_forecast_entity",
    "expected_remaining_load_forecast_entity",
)


@dataclass(frozen=True, slots=True)
class InverterSourceConfig:
    """Describe HA entities that provide one inverter's telemetry."""

    source_id: str
    import_power_entity: str | None = None
    export_power_entity: str | None = None
    pv_power_entity: str | None = None
    remaining_pv_forecast_entity: str | None = None
    expected_remaining_load_forecast_entity: str | None = None


def parse_inverter_sources(document: str | None) -> tuple[InverterSourceConfig, ...]:
    """Parse and validate the optional per-inverter YAML document."""
    if not document or not document.strip():
        return ()
    loaded: Any = yaml.safe_load(document)
    if loaded is None:
        return ()
    if isinstance(loaded, dict):
        loaded = loaded.get("inverters")
    if not isinstance(loaded, list):
        raise ValueError("inverters must be a YAML list")

    sources: list[InverterSourceConfig] = []
    seen: set[str] = set()
    for item in loaded:
        if not isinstance(item, dict):
            raise ValueError("each inverter must be a mapping")
        source_id = item.get("id")
        if not isinstance(source_id, str) or not _SOURCE_ID.fullmatch(source_id):
            raise ValueError("inverter id must use lowercase letters, digits, _ or -")
        if source_id in seen:
            raise ValueError(f"duplicate inverter id: {source_id}")
        values: dict[str, str | None] = {}
        for field in _ENTITY_FIELDS:
            value = item.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field} for {source_id} must be a non-empty string")
            values[field] = value
        if not any(values.values()):
            raise ValueError(f"inverter {source_id} has no telemetry entities")
        seen.add(source_id)
        sources.append(InverterSourceConfig(source_id=source_id, **values))
    return tuple(sources)
