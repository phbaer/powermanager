"""Single polling coordinator that orchestrates the independent core."""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import yaml
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry
from homeassistant.helpers.issue_registry import IssueSeverity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CONTROL_OWNERSHIP_CONFIRMED,
    CONF_ESTIMATE_REMAINING_LOAD,
    CONF_GRID_EXPORT_POWER_ENTITY,
    CONF_GRID_IMPORT_POWER_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_HOST,
    CONF_LOAD_FORECAST_HISTORY_DAYS,
    CONF_LOAD_POWER_ENTITY,
    CONF_PORT,
    CONF_PRICE_ENTITY,
    CONF_PV_POWER_ENTITY,
    CONF_REMAINING_LOAD_FORECAST_ENTITY,
    CONF_REMAINING_PV_FORECAST_ENTITY,
    CONF_RULES_YAML,
    CONF_SCAN_INTERVAL,
    CONF_STATIC_PRICE_PER_KWH,
    CONF_TELEMETRY_MAX_AGE,
    CONF_UNIT_ID,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEFAULT_TELEMETRY_MAX_AGE_SECONDS,
    DOMAIN,
    MAX_SCAN_INTERVAL_SECONDS,
)
from .core.powermanager_core.backends.sma_speedwire import (
    ExternalControllerMonitor,
    SpeedwireListener,
)
from .core.powermanager_core.backends.sma_sunny_island import (
    SunnyIslandClient,
    SunnyIslandConnectionConfig,
)
from .core.powermanager_core.control.policy import evaluate_rules
from .core.powermanager_core.control.rules import parse_rules_document
from .core.powermanager_core.exceptions import PowerManagerError
from .core.powermanager_core.models import (
    BatteryState,
    CommunicationState,
    DeviceInfo,
    EnergyState,
)
from .core.powermanager_core.telemetry import ExponentialBackoff
from .ha_entity_provider import HomeAssistantEntityGridProvider
from .ha_forecast_provider import HomeAssistantEntityForecastProvider
from .ha_price_provider import HomeAssistantEntityPriceProvider

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PowerManagerData:
    """A successful, read-only coordinator update."""

    device_info: DeviceInfo
    battery_state: BatteryState
    energy_state: EnergyState
    possible_external_controller: bool = False
    speedwire_sources: tuple[str, ...] = ()
    simulated_rule_id: str | None = None
    simulated_target_power_w: float | None = None
    control_ownership_clear: bool = False
    speedwire_observation_state: CommunicationState = CommunicationState.UNKNOWN


class PowerManagerCoordinator(DataUpdateCoordinator[PowerManagerData]):
    """Periodically obtain state while keeping protocol details in the core."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)
            ),
        )
        self._config = SunnyIslandConnectionConfig(
            host=entry.data[CONF_HOST],
            port=entry.data[CONF_PORT],
            unit_id=entry.data[CONF_UNIT_ID],
        )
        self._grid_provider = HomeAssistantEntityGridProvider(
            hass,
            entry.options.get(CONF_GRID_POWER_ENTITY),
            entry.options.get(CONF_PV_POWER_ENTITY),
            entry.options.get(CONF_LOAD_POWER_ENTITY),
            entry.options.get(CONF_TELEMETRY_MAX_AGE, DEFAULT_TELEMETRY_MAX_AGE_SECONDS),
            entry.options.get(CONF_GRID_IMPORT_POWER_ENTITY),
            entry.options.get(CONF_GRID_EXPORT_POWER_ENTITY),
        )
        self._price_provider = HomeAssistantEntityPriceProvider(
            hass,
            entry.options.get(CONF_PRICE_ENTITY),
            entry.options.get(CONF_TELEMETRY_MAX_AGE, DEFAULT_TELEMETRY_MAX_AGE_SECONDS),
            entry.options.get(CONF_STATIC_PRICE_PER_KWH),
        )
        self._forecast_provider = HomeAssistantEntityForecastProvider(
            hass,
            entry.options.get(CONF_REMAINING_PV_FORECAST_ENTITY),
            entry.options.get(CONF_REMAINING_LOAD_FORECAST_ENTITY),
            entry.options.get(CONF_TELEMETRY_MAX_AGE, DEFAULT_TELEMETRY_MAX_AGE_SECONDS),
            entry.options.get(CONF_LOAD_POWER_ENTITY),
            entry.options.get(CONF_ESTIMATE_REMAINING_LOAD, False),
            int(entry.options.get(CONF_LOAD_FORECAST_HISTORY_DAYS, 7)),
        )
        self._speedwire_monitor = ExternalControllerMonitor(self._config.host)
        self._speedwire_task: asyncio.Task[None] | None = None
        self._poll_seconds = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)
        self._backoff = ExponentialBackoff(self._poll_seconds, MAX_SCAN_INTERVAL_SECONDS)
        self._control_ownership_confirmed = entry.options.get(
            CONF_CONTROL_OWNERSHIP_CONFIRMED, False
        )
        rules_yaml = entry.options.get(CONF_RULES_YAML)
        self._rules = parse_rules_document(yaml.safe_load(rules_yaml)) if rules_yaml else ()

    def start_speedwire_monitor(self) -> None:
        """Start passive multicast observation without affecting Modbus polling."""
        if self._speedwire_task is None:
            self._speedwire_task = asyncio.create_task(self._observe_speedwire())

    async def stop_speedwire_monitor(self) -> None:
        """Stop passive multicast observation during unload."""
        if self._speedwire_task is not None:
            self._speedwire_task.cancel()
            await asyncio.gather(self._speedwire_task, return_exceptions=True)
            self._speedwire_task = None

    async def _observe_speedwire(self) -> None:
        """Observe passively, retry failures, and expire health during silence."""
        try:
            while True:
                try:
                    addresses = await asyncio.get_running_loop().getaddrinfo(
                        self._config.host, None, family=socket.AF_INET,
                        type=socket.SOCK_DGRAM,
                    )
                    self._speedwire_monitor.inverter_addresses = {
                        address[4][0] for address in addresses
                    }
                    async with SpeedwireListener() as listener:
                        self._speedwire_monitor.listening = True
                        self._speedwire_monitor.last_received_at = None
                        self._publish_observation()
                        while True:
                            try:
                                frame = await listener.receive(timeout=5)
                            except TimeoutError:
                                self._publish_observation()
                                continue
                            self._speedwire_monitor.observe(frame)
                            self._publish_observation()
                except OSError as error:
                    self._speedwire_monitor.listening = False
                    self._publish_observation()
                    _LOGGER.warning("SMA Speedwire listener unavailable: %s", error)
                    await asyncio.sleep(30)
        finally:
            self._speedwire_monitor.listening = False
            self._publish_observation()

    def _with_observation(self, data: PowerManagerData) -> PowerManagerData:
        """Use one authoritative snapshot for polls and passive updates."""
        monitor = self._speedwire_monitor
        now = datetime.now(UTC)
        return replace(
            data,
            possible_external_controller=monitor.possible_external_controller,
            speedwire_sources=tuple(sorted(monitor.observed_sources)),
            speedwire_observation_state=monitor.observation_state(now),
            control_ownership_clear=monitor.ownership_eligible(
                confirmed=self._control_ownership_confirmed, at=now,
            ),
        )

    def _publish_observation(self) -> None:
        """Update listeners without resetting Modbus polling or its health."""
        if self._speedwire_monitor.possible_external_controller:
            self._create_issue("possible_external_controller", "possible_external_controller")
        if self.data is not None:
            updated = self._with_observation(self.data)
            if updated != self.data:
                self.data = updated
                self.async_update_listeners()

    async def _async_update_data(self) -> PowerManagerData:
        """Read state through a new TCP connection, allowing safe reconnects."""
        try:
            async with SunnyIslandClient(self._config) as client:
                device_info = await client.get_device_info()
                battery_state = await client.read_state()
        except PowerManagerError as error:
            self._schedule_retry()
            self._create_issue("communication_failure", "communication_failure")
            raise UpdateFailed(str(error)) from error
        except Exception as error:
            self._schedule_retry()
            self._create_issue("communication_failure", "communication_failure")
            raise UpdateFailed(f"Unexpected PowerManager update failure: {error}") from error

        self._backoff.record_success()
        self.update_interval = timedelta(seconds=self._poll_seconds)
        issue_registry.async_delete_issue(self.hass, DOMAIN, "communication_failure")

        grid_state = (
            await self._grid_provider.read_grid_state()
            if self._grid_provider.configured
            else None
        )
        price_state = (
            await self._price_provider.read_price_state()
            if self._price_provider.configured
            else None
        )
        forecast_state = (
            await self._forecast_provider.read_forecast_state()
            if self._forecast_provider.configured
            else None
        )
        energy_state = EnergyState(
            timestamp=battery_state.timestamp,
            battery=battery_state,
            grid=grid_state,
            price=price_state,
            forecast=forecast_state,
        )
        intent = evaluate_rules(energy_state, self._rules, at=battery_state.timestamp)
        return self._with_observation(PowerManagerData(
            device_info=device_info,
            battery_state=battery_state,
            energy_state=energy_state,
            simulated_rule_id=intent.rule_id if intent else None,
            simulated_target_power_w=intent.target_power_w if intent else None,
        ))

    def _schedule_retry(self) -> None:
        """Increase only the next read delay; successful reads reset it."""
        self.update_interval = timedelta(seconds=self._backoff.record_failure())

    def _create_issue(self, issue_id: str, translation_key: str) -> None:
        """Surface safety-relevant telemetry state through Home Assistant Repairs."""
        issue_registry.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key=translation_key,
        )
