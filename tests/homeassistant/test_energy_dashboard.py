"""Energy Dashboard topology import tests."""

from datetime import UTC, datetime, timedelta

from custom_components.powermanager.core.powermanager_core.inverters import InverterRole
from custom_components.powermanager.ha_energy_dashboard import (
    _current_forecast_power_w,
    _forecast_profile_power_w,
    _parse_configuration,
)


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


def test_energy_dashboard_forecast_exposes_current_predicted_power() -> None:
    now = datetime(2026, 6, 1, 12, 30, tzinfo=UTC)
    samples = [
        (datetime(2026, 6, 1, 12, tzinfo=UTC), 1800.0),
        (datetime(2026, 6, 1, 13, tzinfo=UTC), 2400.0),
    ]
    assert _current_forecast_power_w(samples, now) == 1800.0


def test_energy_dashboard_forecast_exposes_power_profile() -> None:
    samples = [
        (datetime(2026, 6, 1, 12, tzinfo=UTC), 1800.0),
        (datetime(2026, 6, 1, 13, tzinfo=UTC), 2400.0),
    ]
    assert _forecast_profile_power_w(samples) == (
        (datetime(2026, 6, 1, 12, tzinfo=UTC), 1800.0),
        (datetime(2026, 6, 1, 13, tzinfo=UTC), 2400.0),
    )


def test_energy_dashboard_forecast_profile_is_limited_to_next_day() -> None:
    now = datetime(2026, 6, 1, 12, 30, tzinfo=UTC)
    samples = [
        (now, 1000.0),
        (now + timedelta(hours=24), 2000.0),
        (now + timedelta(hours=25), 3000.0),
    ]

    profile = _forecast_profile_power_w(samples, now=now)

    assert profile[0] == (now, 1000 / 24)
    assert all(timestamp <= now + timedelta(hours=24) for timestamp, _ in profile)
    assert not any(timestamp > now + timedelta(hours=24) for timestamp, _ in profile)
