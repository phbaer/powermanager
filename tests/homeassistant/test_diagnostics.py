"""Diagnostics must not disclose LAN connection data."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from powermanager_core.models import BatteryState, DeviceInfo, EnergyState

from custom_components.powermanager.const import DOMAIN
from custom_components.powermanager.coordinator import PowerManagerData
from custom_components.powermanager.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_redacts_configured_host_and_shows_speedwire_sources(hass) -> None:
    """Keep the configured host private while exposing local sender addresses."""
    now = datetime.now(UTC)
    battery = BatteryState(timestamp=now)
    coordinator = SimpleNamespace(
        last_update_success=True,
        data=PowerManagerData(
            device_info=DeviceInfo("sma", "SI4.4M-12", None, None, 9332, True),
            battery_state=battery,
            energy_state=EnergyState(timestamp=now, battery=battery),
            speedwire_sources=("10.0.1.192",),
            speedwire_external_sources=("10.0.1.192",),
        ),
    )
    entry = SimpleNamespace(entry_id="entry", data={"host": "10.0.1.240"})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["entry"]["host"] != "10.0.1.240"
    assert diagnostics["speedwire_external_sources"] == ["10.0.1.192"]
    assert diagnostics["speedwire_sources"] == ["10.0.1.192"]
    assert diagnostics["speedwire_source_count"] == 1
    assert diagnostics["control_mode"] == "monitor_only"
    assert diagnostics["active_control_available"] is False
