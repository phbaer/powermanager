"""Home Assistant entity adapter for optional energy telemetry."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.core import HomeAssistant

from .core.powermanager_core.models import CommunicationState, GridState


class HomeAssistantEntityGridProvider:
    """Read grid, PV, and load power from existing numeric HA entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        grid_entity: str | None = None,
        pv_entity: str | None = None,
        load_entity: str | None = None,
    ) -> None:
        self._hass = hass
        self._entities = {
            "grid_power_w": grid_entity,
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
        communication = (
            CommunicationState.ONLINE
            if any(value is not None for value in values.values())
            else CommunicationState.OFFLINE
        )
        return GridState(
            timestamp=datetime.now(UTC),
            grid_power_w=values["grid_power_w"],
            pv_power_w=values["pv_power_w"],
            load_power_w=values["load_power_w"],
            communication_state=communication,
        )

    def _read_power(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        unit = (state.attributes.get("unit_of_measurement") or "W").lower()
        if unit in {"kw", "kilowatt", "kilowatts"}:
            return value * 1000
        return value
