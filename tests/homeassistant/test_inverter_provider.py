from custom_components.powermanager.core.powermanager_core.inverters import InverterSourceConfig
from custom_components.powermanager.ha_inverter_provider import HomeAssistantEntityInverterProvider


async def test_inverter_provider_reads_role_specific_power_and_forecast(hass) -> None:
    hass.states.async_set("sensor.pv", "3", {"unit_of_measurement": "kW"})
    hass.states.async_set("sensor.forecast", "4.5", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.battery", "-1.2", {"unit_of_measurement": "kW"})
    provider = HomeAssistantEntityInverterProvider(
        hass,
        (
            InverterSourceConfig(
                source_id="hybrid",
                role="hybrid",
                generation_power_entity="sensor.pv",
                battery_power_entity="sensor.battery",
                remaining_pv_forecast_entity="sensor.forecast",
            ),
        ),
        max_age_seconds=120,
    )

    states = await provider.read_states()

    assert provider.configured
    assert len(states) == 1
    assert states[0].generation_power_w == 3000
    assert states[0].battery_power_w == -1200
    assert states[0].remaining_pv_forecast_kwh == 4.5
