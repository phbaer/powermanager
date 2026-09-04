"""Shared normalization helpers for optional energy telemetry."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from .models import CommunicationState


def communication_state_for_timestamp(
    timestamp: datetime | None, *, now: datetime, max_age_seconds: int
) -> CommunicationState:
    """Classify a source timestamp without treating stale data as usable.

    Providers use this helper even when their value is unavailable, so callers
    can distinguish a source which is offline from one which is merely late.
    """
    if timestamp is None:
        return CommunicationState.OFFLINE
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    if (now - timestamp).total_seconds() > max_age_seconds:
        return CommunicationState.STALE
    return CommunicationState.ONLINE


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
    if not math.isfinite(value):
        return None
    unit = (state.attributes.get("unit_of_measurement") or "W").lower()
    return value * 1000 if unit in {"kw", "kilowatt", "kilowatts"} else value


def normalize_price_per_kwh(value: Any, unit: str | None) -> tuple[float, str | None] | None:
    """Normalize common market-price units to currency/kWh.

    A provider must expose an explicit energy unit.  Bare numeric prices are
    rejected rather than guessed, preventing a EUR/MWh value being used as
    EUR/kWh by a future policy.
    """
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    normalized = (unit or "").strip()
    if not normalized:
        return None
    compact = normalized.lower().replace(" ", "")
    if compact.endswith("/mwh") or compact.endswith("per_mwh"):
        return parsed / 1000, normalized.rsplit("/", 1)[0] + "/kWh"
    if compact.endswith("/kwh") or compact.endswith("per_kwh"):
        return parsed, normalized
    return None
