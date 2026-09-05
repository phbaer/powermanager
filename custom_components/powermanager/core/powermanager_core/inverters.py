"""Configuration models for normalized multi-inverter telemetry."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import yaml

_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_ENTITY_FIELDS = (
    "generation_power_entity",
    "battery_power_entity",
    "remaining_pv_forecast_entity",
)


class InverterRole(StrEnum):
    """Physical role of an inverter telemetry source."""

    PV = "pv"
    BATTERY = "battery"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class InverterSourceConfig:
    """Describe HA entities that provide one inverter's telemetry."""

    source_id: str
    role: InverterRole
    generation_power_entity: str | None = None
    battery_power_entity: str | None = None
    remaining_pv_forecast_entity: str | None = None

    @property
    def forecasts_pv(self) -> bool:
        """Return whether this source can contribute a PV forecast."""
        return self.role in (InverterRole.PV, InverterRole.HYBRID) and bool(
            self.generation_power_entity
        )


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
        try:
            role = InverterRole(item.get("role", InverterRole.PV))
        except ValueError as error:
            raise ValueError(f"invalid role for {source_id}") from error
        values: dict[str, str | None] = {}
        for field in _ENTITY_FIELDS:
            value = item.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field} for {source_id} must be a non-empty string")
            values[field] = value
        if role is InverterRole.PV and not values["generation_power_entity"]:
            raise ValueError(f"PV inverter {source_id} requires generation_power_entity")
        if role is InverterRole.PV and values["battery_power_entity"]:
            raise ValueError(f"PV inverter {source_id} cannot have battery_power_entity")
        if role is InverterRole.BATTERY and not values["battery_power_entity"]:
            raise ValueError(f"battery inverter {source_id} requires battery_power_entity")
        if role is InverterRole.BATTERY and values["generation_power_entity"]:
            raise ValueError(f"battery inverter {source_id} cannot have generation_power_entity")
        if role is InverterRole.HYBRID and not any(
            (values["generation_power_entity"], values["battery_power_entity"])
        ):
            raise ValueError(
                f"hybrid inverter {source_id} requires generation_power_entity or "
                "battery_power_entity"
            )
        if values["remaining_pv_forecast_entity"] and not (
            role in (InverterRole.PV, InverterRole.HYBRID)
            and values["generation_power_entity"]
        ):
            raise ValueError(
                f"remaining_pv_forecast_entity for {source_id} requires a generation source"
            )
        seen.add(source_id)
        sources.append(InverterSourceConfig(source_id=source_id, role=role, **values))
    return tuple(sources)
