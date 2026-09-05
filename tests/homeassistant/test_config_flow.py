"""UI setup and option-flow tests without device communication."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powermanager import (
    PLATFORMS,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.powermanager.config_flow import PowerManagerOptionsFlow
from custom_components.powermanager.const import DOMAIN
from custom_components.powermanager.core.powermanager_core.backends.sma_sunny_island import (
    ControlWriteError,
)
from custom_components.powermanager.core.powermanager_core.inverters import parse_inverter_sources
from custom_components.powermanager.core.powermanager_core.models import (
    BatteryState,
    CommunicationState,
    DeviceInfo,
)
from custom_components.powermanager.ha_energy_dashboard import EnergyDashboardConfiguration
from custom_components.powermanager.ha_price_provider import HomeAssistantEntityPriceProvider


async def test_user_flow_validates_read_only_connection(hass) -> None:
    """A successful setup delegates identity validation without any write path."""
    with patch(
        "custom_components.powermanager.config_flow.validate_input",
        AsyncMock(return_value="Sunny Island SI4.4M-12"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={"host": "10.0.1.240", "port": 502, "unit_id": 3},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Sunny Island SI4.4M-12"
    assert result["data"] == {"host": "10.0.1.240", "port": 502, "unit_id": 3}


async def test_static_price_does_not_require_a_home_assistant_entity(hass) -> None:
    """A fixed tariff is available without creating a helper entity."""
    provider = HomeAssistantEntityPriceProvider(
        hass, entity_id=None, max_age_seconds=120, static_price_per_kwh=0.32
    )

    state = await provider.read_price_state()

    assert provider.configured
    assert state.price_per_kwh == 0.32
    assert state.currency == "EUR/kWh"
    assert state.communication_state is CommunicationState.ONLINE


async def test_options_flow_accepts_empty_optional_telemetry_sources() -> None:
    """Unset optional fields must not be passed to selectors as null values."""
    flow = PowerManagerOptionsFlow(Mock(options={}))

    result = await flow.async_step_init()
    data = result["data_schema"]({"scan_interval": 30, "telemetry_max_age": 120})

    assert data["scan_interval"] == 30
    assert data["telemetry_max_age"] == 120


async def test_options_flow_validates_price_conflict_with_valid_rules() -> None:
    """Independent option validations must still run when rules are supplied."""
    flow = PowerManagerOptionsFlow(Mock(options={}))
    result = await flow.async_step_init()
    data = result["data_schema"](
        {
            "scan_interval": 30,
            "telemetry_max_age": 120,
            "rules_yaml": "version: 1\nenabled: false\nrules: []",
            "price_entity": "sensor.market_price",
            "static_price_per_kwh": 0.2,
        }
    )
    with patch.object(flow, "async_show_form", return_value={"errors": {}}) as show_form:
        response = await flow.async_step_init(data)

    assert response == {"errors": {}}
    assert show_form.call_args.kwargs["errors"] == {"base": "price_source_conflict"}


async def test_options_flow_requires_all_confirmations_before_active_enablement() -> None:
    """The write path cannot be enabled by checking only ownership."""
    flow = PowerManagerOptionsFlow(Mock(options={}))
    result = await flow.async_step_init()
    data = result["data_schema"](
        {
            "scan_interval": 30,
            "telemetry_max_age": 120,
            "active_control_enabled": True,
            "control_ownership_confirmed": True,
        }
    )
    with patch.object(flow, "async_show_form", return_value={"errors": {}}) as show_form:
        await flow.async_step_init(data)
    assert show_form.call_args.kwargs["errors"] == {
        "base": "active_control_confirmations_required"
    }


async def test_control_services_are_explicit_and_locked_by_default(hass) -> None:
    """Registering services never bypasses the coordinator's safety gates."""
    await async_setup(hass, {})
    coordinator = Mock()
    coordinator.start_active_control = AsyncMock(
        side_effect=ControlWriteError("active control is disabled")
    )
    hass.data.setdefault(DOMAIN, {})["test"] = coordinator
    with pytest.raises(Exception, match="active control is disabled"):
        await hass.services.async_call(
            DOMAIN,
            "start_control",
            {"power_w": 500, "duration_seconds": 30},
            blocking=True,
        )


async def test_options_flow_rejects_invalid_inverter_sources() -> None:
    """Per-inverter telemetry YAML must be validated before saving options."""
    flow = PowerManagerOptionsFlow(Mock(options={}))
    result = await flow.async_step_init()
    data = result["data_schema"](
        {
            "scan_interval": 30,
            "telemetry_max_age": 120,
            "inverters_yaml": "inverters: [{id: Invalid, generation_power_entity: sensor.pv}]",
        }
    )
    with patch.object(flow, "async_show_form", return_value={"errors": {}}) as show_form:
        response = await flow.async_step_init(data)

    assert response == {"errors": {}}
    assert show_form.call_args.kwargs["errors"] == {"base": "invalid_inverters"}


async def test_options_flow_entity_picker_profiles_build_role_aware_yaml() -> None:
    """Native entity selectors persist the same validated advanced YAML format."""
    flow = PowerManagerOptionsFlow(Mock(options={}))
    result = await flow.async_step_init()
    data = result["data_schema"](
        {
            "scan_interval": 30,
            "telemetry_max_age": 120,
            "inverter_profile_count": 1,
        }
    )
    with patch.object(flow, "async_show_form", return_value=None):
        response = await flow.async_step_init(data)
    assert response is None

    profile_result = await flow.async_step_inverter(
        {
            "id": "sunnyboy",
            "role": "pv",
            "generation_power_entity": "sensor.sunnyboy_power",
            "remaining_pv_forecast_entity": "sensor.sunnyboy_forecast",
        }
    )
    assert profile_result["type"] is FlowResultType.CREATE_ENTRY
    sources = parse_inverter_sources(profile_result["data"]["inverters_yaml"])
    assert sources[0].generation_power_entity == "sensor.sunnyboy_power"
    assert sources[0].remaining_pv_forecast_entity == "sensor.sunnyboy_forecast"


async def test_options_flow_shows_dashboard_sources_and_requires_load_forecast(hass) -> None:
    """Imported dashboard topology is visible and missing planning input blocks save."""
    dashboard = EnergyDashboardConfiguration(
        grid_power_entities=("sensor.grid_power",),
        inverter_sources=(),
        missing=("PV roof_pv: no instantaneous generation entity",),
        summary="- PV roof_pv: missing generation",
    )
    flow = PowerManagerOptionsFlow(Mock(options={}))
    flow.hass = hass
    result = await flow.async_step_init()
    data = result["data_schema"]({
        "scan_interval": 30,
        "telemetry_max_age": 120,
        "inverters_yaml": "",
    })
    with (
        patch(
            "custom_components.powermanager.config_flow.async_read_energy_dashboard_configuration",
            AsyncMock(return_value=dashboard),
        ),
        patch.object(flow, "async_show_form", return_value={"errors": {}}) as show_form,
    ):
        response = await flow.async_step_init(data)

    assert response == {"errors": {}}
    assert show_form.call_args.kwargs["errors"] == {"base": "missing_load_forecast"}


async def test_setup_failure_stops_monitor_and_removes_coordinator(hass) -> None:
    """A failed platform setup cannot leave a retrying Speedwire task behind."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "port": 502, "unit_id": 3},
    )
    entry.add_to_hass(hass)
    coordinator = Mock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.stop_speedwire_monitor = AsyncMock()
    with (
        patch("custom_components.powermanager.PowerManagerCoordinator", return_value=coordinator),
        patch.object(hass.config_entries, "async_forward_entry_setups", side_effect=RuntimeError),
    ):
        with pytest.raises(RuntimeError):
            await async_setup_entry(hass, entry)

    coordinator.start_speedwire_monitor.assert_called_once_with()
    coordinator.stop_speedwire_monitor.assert_awaited_once_with()
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_setup_forwards_only_read_only_platforms(hass) -> None:
    """The entry setup surface remains limited to monitor entities."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "port": 502, "unit_id": 3},
    )
    entry.add_to_hass(hass)
    coordinator = Mock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.stop_speedwire_monitor = AsyncMock()
    with (
        patch("custom_components.powermanager.PowerManagerCoordinator", return_value=coordinator),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()) as forward,
    ):
        assert await async_setup_entry(hass, entry)

    forward.assert_awaited_once_with(entry, PLATFORMS)


async def test_unload_stops_monitor_and_removes_coordinator(hass) -> None:
    """A normal unload releases the passive listener and coordinator state."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "port": 502, "unit_id": 3},
    )
    entry.add_to_hass(hass)
    coordinator = Mock()
    coordinator.stop_speedwire_monitor = AsyncMock()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    with patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)):
        assert await async_unload_entry(hass, entry)

    coordinator.stop_speedwire_monitor.assert_awaited_once_with()
    assert entry.entry_id not in hass.data[DOMAIN]


async def test_full_read_only_setup_forwards_entities_and_unloads(hass) -> None:
    """A real coordinator refresh can create monitor entities and unload cleanly."""
    from custom_components.powermanager.coordinator import PowerManagerCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "port": 502, "unit_id": 3},
    )
    entry.add_to_hass(hass)
    now = datetime.now(UTC)
    client = AsyncMock()
    client.get_device_info.return_value = DeviceInfo(
        "sma_sunny_island", "SI4.4M-12", "305419896", "01.05.10.R", 9332, True
    )
    client.read_state.return_value = BatteryState(
        timestamp=now,
        battery_soc_percent=50,
        communication_state=CommunicationState.ONLINE,
    )
    with (
        patch("custom_components.powermanager.coordinator.SunnyIslandClient") as factory,
        patch.object(PowerManagerCoordinator, "start_speedwire_monitor"),
    ):
        factory.return_value.__aenter__.return_value = client
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.entry_id in hass.data[DOMAIN]
        assert any(
            state.entity_id.startswith("sensor.")
            for state in hass.states.async_all()
        )
        with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
            hass.config_entries.async_update_entry(entry, options={"scan_interval": 60})
            await hass.async_block_till_done()
            reload.assert_awaited_once_with(entry.entry_id)
        assert await hass.config_entries.async_unload(entry.entry_id)
