"""Home Assistant entity telemetry provider tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from homeassistant.core import State

from custom_components.powermanager.ha_entity_provider import HomeAssistantEntityGridProvider
from custom_components.powermanager.ha_forecast_provider import HomeAssistantEntityForecastProvider


async def test_separate_grid_import_and_export_power_are_combined(hass) -> None:
    """Import minus export produces the signed grid exchange convention."""
    hass.states.async_set("sensor.grid_import_power", "1.2", {"unit_of_measurement": "kW"})
    hass.states.async_set("sensor.grid_export_power", "0.2", {"unit_of_measurement": "kW"})
    provider = HomeAssistantEntityGridProvider(
        hass,
        grid_import_entity="sensor.grid_import_power",
        grid_export_entity="sensor.grid_export_power",
    )

    state = await provider.read_grid_state()

    assert provider.configured
    assert state.grid_power_w == 1000


async def test_separate_pv_forecasts_are_summed(hass) -> None:
    """Fresh remaining-energy forecasts for independent arrays are combined."""
    hass.states.async_set("sensor.roof_remaining_pv", "2.5", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.garage_remaining_pv", "750", {"unit_of_measurement": "Wh"})
    provider = HomeAssistantEntityForecastProvider(
        hass,
        remaining_pv_entity=["sensor.roof_remaining_pv", "sensor.garage_remaining_pv"],
        remaining_load_entity=None,
        max_age_seconds=120,
    )

    state = await provider.read_forecast_state()

    assert provider.configured
    assert state.remaining_pv_kwh == 3.25


def test_historical_load_energy_is_integrated_as_piecewise_constant_power() -> None:
    """Load history is integrated from W/kW samples into remaining kWh."""
    start = datetime(2026, 9, 3, 15, tzinfo=UTC)
    states = [
        State(
            "sensor.load_power",
            "1",
            {"unit_of_measurement": "kW"},
            last_updated=start,
        ),
        State(
            "sensor.load_power",
            "2000",
            {"unit_of_measurement": "W"},
            last_updated=start + timedelta(hours=1),
        ),
    ]

    energy = HomeAssistantEntityForecastProvider._integrate_power_states(
        states, start, start + timedelta(hours=2)
    )

    assert energy == 3
