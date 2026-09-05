"""Energy Dashboard topology import tests."""

from custom_components.powermanager.core.powermanager_core.inverters import InverterRole
from custom_components.powermanager.ha_energy_dashboard import _parse_configuration


def test_energy_dashboard_imports_grid_pv_and_battery_sources() -> None:
    configuration = _parse_configuration(
        {
            "energy_sources": [
                {
                    "type": "grid",
                    "stat_rate": "sensor.grid_power",
                    "entity_energy_price": "sensor.energy_price",
                },
                {
                    "type": "solar",
                    "stat_rate": "sensor.roof_power",
                    "name": "Roof PV",
                    "config_entry_solar_forecast": ["forecast-entry"],
                },
                {
                    "type": "battery",
                    "stat_rate": "sensor.battery_power",
                },
            ]
        }
    )

    assert configuration.grid_power_entities == ("sensor.grid_power",)
    assert configuration.price_entity == "sensor.energy_price"
    assert [source.source_id for source in configuration.inverter_sources] == [
        "roof_pv",
        "sensor_battery_power",
    ]
    assert configuration.inverter_sources[0].role is InverterRole.PV
    assert configuration.inverter_sources[1].role is InverterRole.BATTERY
    assert configuration.missing == ()
    assert "PV roof_pv: imported sensor.roof_power" in configuration.summary


def test_energy_dashboard_reports_missing_real_time_inputs() -> None:
    configuration = _parse_configuration(
        {
            "energy_sources": [
                {"type": "grid", "stat_energy_from": "sensor.grid_energy"},
                {"type": "solar", "stat_energy_from": "sensor.pv_energy"},
            ]
        }
    )

    assert configuration.grid_power_entities == ()
    assert any(item.startswith("Grid:") for item in configuration.missing)
    assert any(item.startswith("PV ") for item in configuration.missing)
    assert "Missing:" in configuration.summary
