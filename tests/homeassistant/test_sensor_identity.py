"""Device registry identity remains stable when serial data becomes available."""

from datetime import UTC, datetime
from types import SimpleNamespace

from custom_components.powermanager.const import DOMAIN
from custom_components.powermanager.coordinator import PowerManagerData
from custom_components.powermanager.core.powermanager_core.models import (
    BatteryState,
    DeviceInfo,
    EnergyState,
)
from custom_components.powermanager.sensor import SENSORS, PowerManagerSensor


def test_sensor_device_has_legacy_and_serial_identifiers(hass) -> None:
    now = datetime.now(UTC)
    battery = BatteryState(timestamp=now)
    coordinator = SimpleNamespace(
        data=PowerManagerData(
            device_info=DeviceInfo("sma", "SI4.4M-12", "305419896", "01.05.10.R", 9332, True),
            battery_state=battery,
            energy_state=EnergyState(timestamp=now, battery=battery),
        )
    )
    entry = SimpleNamespace(entry_id="entry", unique_id="10.0.1.240")
    entity = PowerManagerSensor(coordinator, entry, SENSORS[0])

    assert entity.device_info["identifiers"] == {
        (DOMAIN, "10.0.1.240"),
        (DOMAIN, "serial:305419896"),
    }
