"""Passive observation must not mask Modbus health or grant unsafe eligibility."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powermanager.binary_sensor import ExternalControllerWarning
from custom_components.powermanager.const import DOMAIN
from custom_components.powermanager.coordinator import PowerManagerCoordinator, PowerManagerData
from custom_components.powermanager.core.powermanager_core.backends.sma_speedwire import (
    SpeedwireFrame,
)
from custom_components.powermanager.core.powermanager_core.control import (
    ControlRule,
    ControlRuntime,
    RuleConditions,
)
from custom_components.powermanager.core.powermanager_core.control.watchdog import ControlWatchdog
from custom_components.powermanager.core.powermanager_core.models import (
    BatteryState,
    CommunicationState,
    DeviceInfo,
    EnergyState,
)


@pytest.fixture
def coordinator(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "port": 502, "unit_id": 3},
        options={"control_ownership_confirmed": True},
    )
    entry.add_to_hass(hass)
    result = PowerManagerCoordinator(hass, entry)
    now = datetime.now(UTC)
    battery = BatteryState(timestamp=now)
    result.data = PowerManagerData(
        DeviceInfo("sma", "SI4.4M-12", None, None, 9332, True),
        battery, EnergyState(now, battery),
    )
    return result


async def test_detection_survives_poll_and_does_not_mask_modbus_failure(coordinator):
    monitor = coordinator._speedwire_monitor
    monitor.listening = True
    monitor.observe(SpeedwireFrame(b"frame", ("127.0.0.1", 9522), datetime.now(UTC)))
    coordinator._publish_observation()
    assert coordinator.data.control_ownership_clear
    coordinator.last_update_success = False
    monitor.observe(SpeedwireFrame(b"frame", ("127.0.0.2", 9522), datetime.now(UTC)))
    with patch.object(coordinator, "_schedule_refresh") as schedule:
        coordinator._publish_observation()
        schedule.assert_not_called()
    assert not coordinator.last_update_success
    assert coordinator.data.possible_external_controller
    assert not coordinator.data.control_ownership_clear
    client = AsyncMock()
    client.get_device_info.return_value = coordinator.data.device_info
    client.read_state.return_value = coordinator.data.battery_state
    with patch("custom_components.powermanager.coordinator.SunnyIslandClient") as factory:
        factory.return_value.__aenter__.return_value = client
        data = await coordinator._async_update_data()
    assert data.possible_external_controller
    assert data.speedwire_sources == ("127.0.0.1", "127.0.0.2")
    assert not data.control_ownership_clear


async def test_unknown_and_stale_observation_are_visible(coordinator):
    entity = ExternalControllerWarning(coordinator, Mock(unique_id="test"))
    coordinator._publish_observation()
    assert entity.is_on is None
    assert not coordinator.data.control_ownership_clear
    monitor = coordinator._speedwire_monitor
    monitor.listening = True
    monitor.observe(SpeedwireFrame(b"frame", ("127.0.0.1", 9522), datetime.now(UTC)))
    coordinator._publish_observation()
    assert entity.is_on is False
    monitor.last_received_at -= timedelta(seconds=121)
    coordinator._publish_observation()
    assert entity.is_on is None
    assert entity.extra_state_attributes == {"observation_state": "stale"}
    assert not coordinator.data.control_ownership_clear


async def test_listener_failure_retries_and_stop_cleans_up(coordinator):
    import asyncio

    recovered = asyncio.Event()
    entered = 0

    async def start():
        nonlocal entered
        entered += 1
        if entered == 1:
            raise OSError("multicast unavailable")
        return listener

    async def receive(*, timeout):
        recovered.set()
        await asyncio.Future()

    async def retry_delay(seconds):
        assert seconds == 30
        assert coordinator.data.speedwire_observation_state == "offline"
        assert not coordinator.data.control_ownership_clear

    with (
        patch("custom_components.powermanager.coordinator.SpeedwireListener") as factory,
        patch("custom_components.powermanager.coordinator.asyncio.sleep", retry_delay),
    ):
        listener = factory.return_value
        listener.__aenter__.side_effect = start
        listener.receive = AsyncMock(side_effect=receive)
        coordinator.start_speedwire_monitor()
        await asyncio.wait_for(recovered.wait(), timeout=2)
        assert entered == 2
        assert coordinator.data.speedwire_observation_state == "unknown"
        assert not coordinator.data.control_ownership_clear
        assert not coordinator._speedwire_task.done()
        await coordinator.stop_speedwire_monitor()
        listener.__aexit__.assert_awaited_once()
    assert coordinator._speedwire_task is None
    assert not coordinator._speedwire_monitor.listening


async def test_coordinator_uses_runtime_for_simulation_decision(coordinator):
    now = datetime.now(UTC)
    battery = BatteryState(
        timestamp=now,
        battery_soc_percent=50,
        communication_state=CommunicationState.ONLINE,
    )
    coordinator._rules = (ControlRule("always", 1, RuleConditions(), 100),)
    coordinator._simulation_runtime = ControlRuntime(
        coordinator._rules, watchdog=ControlWatchdog(timeout_seconds=60)
    )
    client = AsyncMock()
    client.get_device_info.return_value = coordinator.data.device_info
    client.read_state.return_value = battery
    with patch("custom_components.powermanager.coordinator.SunnyIslandClient") as factory:
        factory.return_value.__aenter__.return_value = client
        data = await coordinator._async_update_data()
    assert data.simulated_rule_id == "always"
    assert data.simulated_target_power_w == 100
    assert data.simulated_accepted is True
    assert data.simulated_reason is None
