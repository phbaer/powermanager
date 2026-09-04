"""Home Assistant entity adapter for optional energy telemetry."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from .core.powermanager_core.models import CommunicationState, GridState
from .core.powermanager_core.telemetry import (
    communication_state_for_timestamp,
    normalize_power_state,
)


class HomeAssistantEntityGridProvider:
    """Read grid, PV, and load power from existing numeric HA entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        grid_entity: str | None = None,
        pv_entity: str | None = None,
        load_entity: str | None = None,
        max_age_seconds: int = 120,
        grid_import_entity: str | None = None,
        grid_export_entity: str | None = None,
    ) -> None:
        self._hass = hass
        self._max_age_seconds = max_age_seconds
        self._entities = {
            "grid_power_w": grid_entity,
            "grid_import_power_w": grid_import_entity,
            "grid_export_power_w": grid_export_entity,
            "pv_power_w": pv_entity,
            "load_power_w": load_entity,
        }

    @property
    def configured(self) -> bool:
        """Return whether at least one telemetry entity was selected."""
        return any(self._entities.values())

    async def read_grid_state(self) -> GridState:
        """Read configured values, treating unavailable entities as missing."""
        values: dict[str, float | None] = {}
        for key, entity_id in self._entities.items():
            values[key] = self._read_power(entity_id)
        timestamps = [
            self._hass.states.get(entity_id).last_updated
            for entity_id in self._entities.values()
            if entity_id and self._hass.states.get(entity_id) is not None
        ]
        communication = (
            CommunicationState.ONLINE
            if any(value is not None for value in values.values())
            else communication_state_for_timestamp(
                max(timestamps) if timestamps else None,
                now=datetime.now(UTC),
                max_age_seconds=self._max_age_seconds,
            )
        )
        grid_power = values["grid_power_w"]
        import_power = values["grid_import_power_w"]
        export_power = values["grid_export_power_w"]
        if grid_power is None and import_power is not None and export_power is not None:
            grid_power = import_power - export_power

        return GridState(
            timestamp=datetime.now(UTC),
            grid_power_w=grid_power,
            pv_power_w=values["pv_power_w"],
            load_power_w=values["load_power_w"],
            communication_state=communication,
        )

    def _read_power(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self._hass.states.get(entity_id)
        return normalize_power_state(
            state, now=datetime.now(UTC), max_age_seconds=self._max_age_seconds
        )
