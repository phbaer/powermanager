"""Shared normalization helpers for optional energy telemetry."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def normalize_power_state(
    state: Any, *, now: datetime, max_age_seconds: int
) -> float | None:
    """Convert a Home Assistant-like state to watts, rejecting stale values."""
    if state is None or state.state in ("unknown", "unavailable"):
        return None
    updated = state.last_updated
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    if (now - updated).total_seconds() > max_age_seconds:
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None
    unit = (state.attributes.get("unit_of_measurement") or "W").lower()
    return value * 1000 if unit in {"kw", "kilowatt", "kilowatts"} else value
