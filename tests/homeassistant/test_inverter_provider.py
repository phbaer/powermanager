from custom_components.powermanager.core.powermanager_core.inverters import InverterSourceConfig
from custom_components.powermanager.ha_inverter_provider import HomeAssistantEntityInverterProvider


async def test_inverter_provider_reads_directional_power_and_forecast(hass) -> None:
    hass.states.async_set("sensor.import", "1.2", {"unit_of_measurement": "kW"})
    hass.states.async_set("sensor.export", "200", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv", "3", {"unit_of_measurement": "kW"})
    hass.states.async_set("sensor.forecast", "4.5", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.load_forecast", "2", {"unit_of_measurement": "kWh"})
    provider = HomeAssistantEntityInverterProvider(
        hass,
        (
            InverterSourceConfig(
                source_id="hybrid",
                import_power_entity="sensor.import",
                export_power_entity="sensor.export",
                pv_power_entity="sensor.pv",
                remaining_pv_forecast_entity="sensor.forecast",
                expected_remaining_load_forecast_entity="sensor.load_forecast",
            ),
        ),
        max_age_seconds=120,
    )

    states = await provider.read_states()

    assert provider.configured
    assert len(states) == 1
    assert states[0].import_power_w == 1200
    assert states[0].export_power_w == 200
    assert states[0].pv_power_w == 3000
    assert states[0].net_power_w == 1000
    assert states[0].forecast is not None
    assert states[0].forecast.remaining_pv_kwh == 4.5
    assert states[0].forecast.expected_remaining_load_kwh == 2
