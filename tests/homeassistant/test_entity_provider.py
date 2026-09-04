"""Home Assistant entity telemetry provider tests."""

from __future__ import annotations

from custom_components.powermanager.ha_entity_provider import HomeAssistantEntityGridProvider


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
