"""Single polling coordinator that orchestrates the independent core."""

from __future__ import annotations

import asyncio
import logging
import math
import socket
from dataclasses import dataclass, replace
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry
from homeassistant.helpers.issue_registry import IssueSeverity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ACTIVE_CONTROL_ENABLED,
    CONF_ACTIVE_CONTROL_FIRMWARE_CONFIRMED,
    CONF_ACTIVE_CONTROL_LS_RCD_CONFIRMED,
    CONF_ACTIVE_CONTROL_MAX_DURATION_SECONDS,
    CONF_ACTIVE_CONTROL_MAX_POWER_W,
    CONF_ACTIVE_CONTROL_SCHEDULED,
    CONF_ACTIVE_CONTROL_SINGLE_PHASE_CONFIRMED,
    CONF_ACTIVE_CONTROL_TELEMETRY_SOURCES,
    CONF_CONTROL_OWNERSHIP_CONFIRMED,
    CONF_ESTIMATE_REMAINING_LOAD,
    CONF_GRID_EXPORT_POWER_ENTITY,
    CONF_GRID_IMPORT_POWER_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_HOST,
    CONF_INVERTERS,
    CONF_LOAD_FORECAST_HISTORY_DAYS,
    CONF_LOAD_POWER_ENTITY,
    CONF_PORT,
    CONF_PREDICTIVE_CAPACITY_KWH,
    CONF_PREDICTIVE_CONTROL_ENABLED,
    CONF_PREDICTIVE_END_SOC_PERCENT,
    CONF_PREDICTIVE_EXPORT_CAPACITY_KWH,
    CONF_PREDICTIVE_GRID_CHARGE_ALLOWED,
    CONF_PREDICTIVE_MAX_CHARGE_POWER_W,
    CONF_PREDICTIVE_RESERVE_SOC_PERCENT,
    CONF_PRICE_ENTITY,
    CONF_PV_POWER_ENTITY,
    CONF_REMAINING_LOAD_FORECAST_ENTITY,
    CONF_REMAINING_PV_FORECAST_ENTITY,
    CONF_RULES_YAML,
    CONF_SCAN_INTERVAL,
    CONF_STATIC_PRICE_PER_KWH,
    CONF_TELEMETRY_MAX_AGE,
    CONF_UNIT_ID,
    DEFAULT_ACTIVE_CONTROL_MAX_DURATION_SECONDS,
    DEFAULT_ACTIVE_CONTROL_MAX_POWER_W,
    DEFAULT_PREDICTIVE_CAPACITY_KWH,
    DEFAULT_PREDICTIVE_END_SOC_PERCENT,
    DEFAULT_PREDICTIVE_EXPORT_CAPACITY_KWH,
    DEFAULT_PREDICTIVE_MAX_CHARGE_POWER_W,
    DEFAULT_PREDICTIVE_RESERVE_SOC_PERCENT,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEFAULT_SPEEDWIRE_MAX_AGE_SECONDS,
    DEFAULT_TELEMETRY_MAX_AGE_SECONDS,
    DOMAIN,
    MAX_ACTIVE_CONTROL_MAX_DURATION_SECONDS,
    MAX_ACTIVE_CONTROL_MAX_POWER_W,
    MAX_SCAN_INTERVAL_SECONDS,
    MIN_ACTIVE_CONTROL_MAX_DURATION_SECONDS,
)
from .core.powermanager_core.backends.sma_speedwire import (
    ExternalControllerMonitor,
    SpeedwireListener,
)
from .core.powermanager_core.backends.sma_sunny_island import (
    ControlCommandSession,
    ControlWriteError,
    ControlWriteGuard,
    SunnyIslandClient,
    SunnyIslandConnectionConfig,
    SunnyIslandControlAdapter,
)
from .core.powermanager_core.control.policy import ControlIntent
from .core.powermanager_core.control.predictive import (
    PredictiveInputs,
    PredictivePlan,
    PredictivePlanningError,
    plan_predictive_charge,
)
from .core.powermanager_core.control.rules import parse_rules_document
from .core.powermanager_core.control.runtime import ControlRuntime
from .core.powermanager_core.control.safety import SafetyConfig, validate_intent
from .core.powermanager_core.control.watchdog import ControlWatchdog
from .core.powermanager_core.exceptions import PowerManagerError, UnsupportedDeviceError
from .core.powermanager_core.inverters import InverterSourceConfig, parse_inverter_sources
from .core.powermanager_core.modbus.client import PymodbusTcpWriteTransport
from .core.powermanager_core.models import (
    BatteryState,
    CommunicationState,
    DeviceInfo,
    EnergyState,
    ForecastState,
    GridState,
    InverterState,
)
from .core.powermanager_core.telemetry import ExponentialBackoff
from .ha_energy_dashboard import (
    EnergyDashboardConfiguration,
    EnergyDashboardRuntime,
    HomeAssistantEnergyDashboardProvider,
)
from .ha_entity_provider import HomeAssistantEntityGridProvider
from .ha_forecast_provider import HomeAssistantEntityForecastProvider
from .ha_inverter_provider import HomeAssistantEntityInverterProvider
from .ha_price_provider import HomeAssistantEntityPriceProvider

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PowerManagerData:
    """A successful, read-only coordinator update."""

    device_info: DeviceInfo
    battery_state: BatteryState
    energy_state: EnergyState
    inverters: tuple[InverterState, ...] = ()
    possible_external_controller: bool = False
    speedwire_sources: tuple[str, ...] = ()
    speedwire_external_sources: tuple[str, ...] = ()
    simulated_rule_id: str | None = None
    simulated_target_power_w: float | None = None
    control_ownership_clear: bool = False
    speedwire_observation_state: CommunicationState = CommunicationState.UNKNOWN
    simulated_accepted: bool | None = None
    simulated_reason: str | None = None
    simulated_restore_normal: bool = False
    simulated_held: bool = False
    control_mode: str = "monitor_only"
    active_control_available: bool = False
    control_block_reason: str = "active control is not commissioned"
    predictive_target_power_w: float | None = None
    predictive_target_soc_percent: float | None = None
    predictive_forecast_surplus_kwh: float | None = None
    predictive_headroom_kwh: float | None = None
    predictive_charge_inhibit: bool | None = None
    predictive_reason: str = "forecast_unavailable"
    energy_dashboard_summary: str = "Energy Dashboard is not configured."
    energy_dashboard_missing: tuple[str, ...] = ()


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
        self._telemetry_max_age = entry.options.get(
            CONF_TELEMETRY_MAX_AGE, DEFAULT_TELEMETRY_MAX_AGE_SECONDS
        )
        self._grid_provider = HomeAssistantEntityGridProvider(
            hass,
            entry.options.get(CONF_GRID_POWER_ENTITY),
            entry.options.get(CONF_PV_POWER_ENTITY),
            entry.options.get(CONF_LOAD_POWER_ENTITY),
            self._telemetry_max_age,
            entry.options.get(CONF_GRID_IMPORT_POWER_ENTITY),
            entry.options.get(CONF_GRID_EXPORT_POWER_ENTITY),
        )
        self._price_provider = HomeAssistantEntityPriceProvider(
            hass,
            entry.options.get(CONF_PRICE_ENTITY),
            self._telemetry_max_age,
            entry.options.get(CONF_STATIC_PRICE_PER_KWH),
        )
        self._forecast_provider = HomeAssistantEntityForecastProvider(
            hass,
            entry.options.get(CONF_REMAINING_PV_FORECAST_ENTITY),
            entry.options.get(CONF_REMAINING_LOAD_FORECAST_ENTITY),
            self._telemetry_max_age,
            entry.options.get(CONF_LOAD_POWER_ENTITY),
            entry.options.get(CONF_ESTIMATE_REMAINING_LOAD, False),
            int(entry.options.get(CONF_LOAD_FORECAST_HISTORY_DAYS, 7)),
        )
        self._inverter_sources: tuple[InverterSourceConfig, ...] = parse_inverter_sources(
            entry.options.get(CONF_INVERTERS)
        )
        self._effective_inverter_sources = self._inverter_sources
        self._inverter_provider = HomeAssistantEntityInverterProvider(
            hass,
            self._inverter_sources,
            self._telemetry_max_age,
        )
        self._energy_dashboard_provider = HomeAssistantEnergyDashboardProvider(
            hass, entry.options.get(CONF_TELEMETRY_MAX_AGE, DEFAULT_TELEMETRY_MAX_AGE_SECONDS)
        )
        self._speedwire_monitor = ExternalControllerMonitor(
            self._config.host,
            max_age_seconds=max(
                DEFAULT_SPEEDWIRE_MAX_AGE_SECONDS,
                int(self._telemetry_max_age),
            ),
        )
        self._speedwire_task: asyncio.Task[None] | None = None
        self._poll_seconds = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)
        self._backoff = ExponentialBackoff(self._poll_seconds, MAX_SCAN_INTERVAL_SECONDS)
        self._control_ownership_confirmed = entry.options.get(
            CONF_CONTROL_OWNERSHIP_CONFIRMED, False
        )
        self._active_control_enabled = bool(
            entry.options.get(CONF_ACTIVE_CONTROL_ENABLED, False)
        )
        self._active_control_scheduled = bool(
            entry.options.get(CONF_ACTIVE_CONTROL_SCHEDULED, False)
        )
        self._active_control_single_phase_confirmed = bool(
            entry.options.get(CONF_ACTIVE_CONTROL_SINGLE_PHASE_CONFIRMED, False)
        )
        self._active_control_firmware_confirmed = bool(
            entry.options.get(CONF_ACTIVE_CONTROL_FIRMWARE_CONFIRMED, False)
        )
        self._active_control_ls_rcd_confirmed = bool(
            entry.options.get(CONF_ACTIVE_CONTROL_LS_RCD_CONFIRMED, False)
        )
        self._active_control_telemetry_sources = _parse_host_list(
            entry.options.get(CONF_ACTIVE_CONTROL_TELEMETRY_SOURCES)
        )
        self._active_control_max_power_w = min(
            max(
                float(
                    entry.options.get(
                        CONF_ACTIVE_CONTROL_MAX_POWER_W, DEFAULT_ACTIVE_CONTROL_MAX_POWER_W
                    )
                ),
                100.0,
            ),
            MAX_ACTIVE_CONTROL_MAX_POWER_W,
        )
        self._active_control_max_duration_seconds = min(
            max(
                int(
                    entry.options.get(
                        CONF_ACTIVE_CONTROL_MAX_DURATION_SECONDS,
                        DEFAULT_ACTIVE_CONTROL_MAX_DURATION_SECONDS,
                    )
                ),
                MIN_ACTIVE_CONTROL_MAX_DURATION_SECONDS,
            ),
            MAX_ACTIVE_CONTROL_MAX_DURATION_SECONDS,
        )
        self._active_control_task: asyncio.Task[None] | None = None
        self._active_control_stop: asyncio.Event | None = None
        self._active_control_power_w: float | None = None
        self._active_control_last_error: str | None = None
        rules_yaml = entry.options.get(CONF_RULES_YAML)
        self._rules = (
            parse_rules_document(
                yaml.safe_load(rules_yaml),
                allow_enabled=self._active_control_enabled and self._active_control_scheduled,
            )
            if rules_yaml
            else ()
        )
        self._timezone = _ha_timezone(hass)
        self._simulation_runtime = ControlRuntime(
            self._rules,
            watchdog=ControlWatchdog(timeout_seconds=max(30, self._poll_seconds * 3)),
            timezone=self._timezone,
        )
        self._predictive_capacity_kwh = float(
            entry.options.get(CONF_PREDICTIVE_CAPACITY_KWH, DEFAULT_PREDICTIVE_CAPACITY_KWH)
        )
        self._predictive_end_soc_percent = float(
            entry.options.get(
                CONF_PREDICTIVE_END_SOC_PERCENT, DEFAULT_PREDICTIVE_END_SOC_PERCENT
            )
        )
        self._predictive_reserve_soc_percent = float(
            entry.options.get(
                CONF_PREDICTIVE_RESERVE_SOC_PERCENT, DEFAULT_PREDICTIVE_RESERVE_SOC_PERCENT
            )
        )
        self._predictive_export_capacity_kwh = float(
            entry.options.get(
                CONF_PREDICTIVE_EXPORT_CAPACITY_KWH, DEFAULT_PREDICTIVE_EXPORT_CAPACITY_KWH
            )
        )
        self._predictive_max_charge_power_w = float(
            entry.options.get(
                CONF_PREDICTIVE_MAX_CHARGE_POWER_W, DEFAULT_PREDICTIVE_MAX_CHARGE_POWER_W
            )
        )
        self._predictive_grid_charge_allowed = bool(
            entry.options.get(CONF_PREDICTIVE_GRID_CHARGE_ALLOWED, False)
        )
        self._predictive_control_enabled = bool(
            entry.options.get(CONF_PREDICTIVE_CONTROL_ENABLED, False)
        )

    def start_speedwire_monitor(self) -> None:
        """Start passive multicast observation without affecting Modbus polling."""
        if self._speedwire_task is None:
            self._speedwire_task = asyncio.create_task(self._observe_speedwire())

    @property
    def inverter_sources(self) -> tuple[InverterSourceConfig, ...]:
        """Return configured per-inverter telemetry sources."""
        return self._effective_inverter_sources

    async def stop_speedwire_monitor(self) -> None:
        """Stop passive multicast observation during unload."""
        await self.stop_active_control()
        if self._speedwire_task is not None:
            self._speedwire_task.cancel()
            await asyncio.gather(self._speedwire_task, return_exceptions=True)
            self._speedwire_task = None

    @property
    def active_control_running(self) -> bool:
        """Return whether a bounded command session is currently running."""
        return self._active_control_task is not None and not self._active_control_task.done()

    @property
    def active_control_power_w(self) -> float | None:
        """Return the domain-power target of the current session."""
        return self._active_control_power_w

    @property
    def active_control_last_error(self) -> str | None:
        """Return the last bounded-session error for diagnostics."""
        return self._active_control_last_error

    @property
    def predictive_control_enabled(self) -> bool:
        """Return whether forecast planning is selected for scheduled control."""
        return self._predictive_control_enabled

    async def start_active_control(self, power_w: float, duration_seconds: int) -> None:
        """Start one explicit, bounded command session.

        ``power_w`` uses PowerManager's domain convention: positive charges the
        battery and negative discharges it.  The SMA register uses the inverse
        sign, so conversion is kept at this single adapter boundary.
        """
        if self.data is None:
            raise ControlWriteError("fresh Sunny Island telemetry is required")
        reason = self._active_control_block_reason(self.data)
        if reason is not None:
            raise ControlWriteError(reason)
        if not -self._active_control_max_power_w <= power_w <= self._active_control_max_power_w:
            raise ControlWriteError("requested power exceeds configured active-control bound")
        if not 1 <= duration_seconds <= self._active_control_max_duration_seconds:
            raise ControlWriteError("requested duration exceeds configured active-control bound")
        if self.active_control_running:
            raise ControlWriteError("another active-control session is already running")
        await self._validate_active_command(power_w)
        stop = asyncio.Event()
        self._active_control_stop = stop
        self._active_control_power_w = power_w
        self._active_control_last_error = None
        self._active_control_task = asyncio.create_task(
            self._run_active_control(power_w, duration_seconds, stop)
        )
        self._active_control_task.add_done_callback(self._active_control_done)
        self._publish_control_status()

    async def stop_active_control(self) -> None:
        """Stop the heartbeat and wait for its baseline restoration."""
        task = self._active_control_task
        if task is None:
            return
        if self._active_control_stop is not None:
            self._active_control_stop.set()
        await asyncio.gather(task, return_exceptions=True)
        self._active_control_task = None
        self._active_control_stop = None
        self._active_control_power_w = None
        self._publish_control_status()

    async def _run_active_control(
        self, power_w: float, duration_seconds: int, stop: asyncio.Event
    ) -> None:
        transport = PymodbusTcpWriteTransport(
            self._config.host,
            self._config.port,
            self._config.unit_id,
            self._config.timeout_seconds,
        )
        adapter = SunnyIslandControlAdapter(
            transport,
            unit_id=self._config.unit_id,
            max_power_w=self._active_control_max_power_w,
            guard=ControlWriteGuard(
                enabled=True,
                ownership_confirmed=True,
                home_manager_detected=False,
            ),
        )
        try:
            await transport.connect()
            session = ControlCommandSession(
                adapter,
                max_duration_seconds=duration_seconds,
                validate_command=lambda _sma_power: self._validate_active_command(power_w),
            )
            await session.run_for(-power_w, duration_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._active_control_last_error = str(error)
            _LOGGER.error("Active-control session stopped: %s", error)
        finally:
            await transport.close()
            self._active_control_power_w = None
            self._publish_control_status()

    def _active_control_done(self, task: asyncio.Task[None]) -> None:
        """Consume task exceptions; service failures remain visible in status."""
        if task.cancelled():
            return
        try:
            task.exception()
        except Exception as error:  # pragma: no cover - defensive callback guard
            self._active_control_last_error = str(error)
        self._publish_control_status()

    async def _validate_active_command(self, power_w: float) -> None:
        """Re-check ownership, freshness, operating state, and SoC per heartbeat."""
        data = self.data
        if data is None:
            raise ControlWriteError("fresh Sunny Island telemetry is required")
        reason = self._active_control_block_reason(data)
        if reason is not None:
            raise ControlWriteError(reason)
        intent = ControlIntent("active-control", power_w, 0, datetime.now(UTC))
        valid, validation_reason = validate_intent(
            intent,
            data.energy_state,
            SafetyConfig(
                max_charge_power_w=self._active_control_max_power_w,
                max_discharge_power_w=self._active_control_max_power_w,
                minimum_soc_percent=self._predictive_reserve_soc_percent,
                max_energy_age_seconds=self._config_max_age,
            ),
            enabled=True,
            at=datetime.now(UTC),
        )
        if not valid:
            raise ControlWriteError(validation_reason or "active-control safety validation failed")

    def _active_control_block_reason(self, data: PowerManagerData | None) -> str | None:
        """Return the first failed commissioning or runtime control gate."""
        if not self._active_control_enabled:
            return "active control is disabled"
        if not self._control_ownership_confirmed:
            return "PowerManager control ownership is not confirmed"
        if not self._active_control_single_phase_confirmed:
            return "single-phase topology is not confirmed"
        if not self._active_control_firmware_confirmed:
            return "firmware behavior is not confirmed"
        if not self._active_control_ls_rcd_confirmed:
            return "LS/RCD isolation procedure is not confirmed"
        if data is None:
            return "fresh Sunny Island telemetry is required"
        if not data.control_ownership_clear:
            return "Speedwire ownership is not clear"
        if data.battery_state.communication_state is not CommunicationState.ONLINE:
            return "battery telemetry is not online"
        return None

    def _publish_control_status(self) -> None:
        """Refresh status entities after a session lifecycle transition."""
        if self.data is not None:
            self.data = self._with_observation(self.data)
            self.async_update_listeners()

    async def _observe_speedwire(self) -> None:
        """Observe passively, retry failures, and expire health during silence."""
        try:
            while True:
                try:
                    self._speedwire_monitor.inverter_addresses = (
                        await self._resolve_inverter_addresses()
                    )
                    async with SpeedwireListener() as listener:
                        self._speedwire_monitor.listening = True
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

    async def _resolve_inverter_addresses(self) -> set[str]:
        """Resolve the configured inverter host for passive source filtering."""
        addresses = await asyncio.get_running_loop().getaddrinfo(
            self._config.host,
            None,
            family=socket.AF_INET,
            type=socket.SOCK_DGRAM,
        )
        return {address[4][0] for address in addresses}

    def _with_observation(self, data: PowerManagerData) -> PowerManagerData:
        """Use one authoritative snapshot for polls and passive updates."""
        monitor = self._speedwire_monitor
        now = datetime.now(UTC)
        unclassified_sources = set(monitor.external_sources) - set(
            self._active_control_telemetry_sources
        )
        observed = replace(
            data,
            possible_external_controller=bool(unclassified_sources),
            speedwire_sources=tuple(sorted(monitor.observed_sources)),
            speedwire_external_sources=monitor.external_sources,
            speedwire_observation_state=monitor.observation_state(now),
            control_ownership_clear=monitor.ownership_eligible(
                confirmed=self._control_ownership_confirmed,
                at=now,
                telemetry_only_sources=self._active_control_telemetry_sources,
            ),
        )
        block_reason = self._active_control_block_reason(observed)
        return replace(
            observed,
            control_mode="active_control" if block_reason is None else "monitor_only",
            active_control_available=block_reason is None,
            control_block_reason=block_reason or "active control ready",
        )

    def _publish_observation(self) -> None:
        """Update listeners without resetting Modbus polling or its health."""
        unclassified_sources = set(self._speedwire_monitor.external_sources) - set(
            self._active_control_telemetry_sources
        )
        if unclassified_sources:
            self._create_issue("possible_external_controller", "possible_external_controller")
        else:
            issue_registry.async_delete_issue(
                self.hass, DOMAIN, "possible_external_controller"
            )
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
        except UnsupportedDeviceError as error:
            self._schedule_retry()
            self._create_issue("unsupported_device", "unsupported_device")
            raise UpdateFailed(str(error)) from error
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
        if device_info.firmware_version is None:
            self._create_issue("firmware_unavailable", "firmware_unavailable")
        else:
            issue_registry.async_delete_issue(self.hass, DOMAIN, "firmware_unavailable")

        dashboard_runtime = await self._read_energy_dashboard()
        grid_state = (
            await self._grid_provider.read_grid_state()
            if self._grid_provider.configured
            else dashboard_runtime.grid
        )
        price_state = (
            await self._price_provider.read_price_state()
            if self._price_provider.configured
            else dashboard_runtime.price
        )
        forecast_state = (
            await self._forecast_provider.read_forecast_state()
            if self._forecast_provider.configured
            else dashboard_runtime.forecast
        )
        if self._inverter_sources:
            self._effective_inverter_sources = self._inverter_sources
            inverter_states = await self._inverter_provider.read_states()
        else:
            self._effective_inverter_sources = dashboard_runtime.configuration.inverter_sources
            inverter_provider = HomeAssistantEntityInverterProvider(
                self.hass,
                self._effective_inverter_sources,
                self._config_max_age,
            )
            inverter_states = await inverter_provider.read_states()
        if grid_state is None:
            grid_state = _aggregate_inverter_grid(inverter_states)
        elif grid_state.pv_power_w is None:
            inverter_grid = _aggregate_inverter_grid(inverter_states)
            if inverter_grid is not None:
                grid_state = replace(grid_state, pv_power_w=inverter_grid.pv_power_w)
        grid_state = _derive_load_power(grid_state, battery_state)
        forecast_state = _merge_forecasts(forecast_state, dashboard_runtime.forecast)
        forecast_state = _merge_forecasts(
            forecast_state,
            _aggregate_inverter_forecast(self._effective_inverter_sources, inverter_states),
        )
        energy_state = EnergyState(
            timestamp=battery_state.timestamp,
            battery=battery_state,
            grid=grid_state,
            price=price_state,
            forecast=forecast_state,
        )
        decision = await self._simulation_runtime.cycle(
            energy_state, at=battery_state.timestamp, enabled=True
        )
        intent = decision.intent
        predictive_plan = self._predictive_plan(battery_state, forecast_state, grid_state)
        result = self._with_observation(PowerManagerData(
            device_info=device_info,
            battery_state=battery_state,
            energy_state=energy_state,
            inverters=inverter_states,
            simulated_rule_id=intent.rule_id if intent else None,
            simulated_target_power_w=intent.target_power_w if intent else None,
            simulated_accepted=decision.accepted,
            simulated_reason=decision.reason,
            simulated_restore_normal=decision.restore_normal,
            simulated_held=decision.held,
            predictive_target_power_w=(predictive_plan.target_power_w if predictive_plan else None),
            predictive_target_soc_percent=(
                predictive_plan.target_soc_percent if predictive_plan else None
            ),
            predictive_forecast_surplus_kwh=(
                predictive_plan.forecast_surplus_kwh if predictive_plan else None
            ),
            predictive_headroom_kwh=(predictive_plan.headroom_kwh if predictive_plan else None),
            predictive_charge_inhibit=(
                predictive_plan.charge_inhibit if predictive_plan else None
            ),
            predictive_reason=(
                predictive_plan.reason
                if predictive_plan
                else self._predictive_reason(forecast_state)
            ),
            energy_dashboard_summary=dashboard_runtime.configuration.summary,
            energy_dashboard_missing=dashboard_runtime.configuration.missing,
        ))
        if self._active_control_scheduled:
            await self._reconcile_scheduled_control(result, decision, predictive_plan)
        return result

    async def _reconcile_scheduled_control(
        self,
        data: PowerManagerData,
        decision,
        predictive_plan: PredictivePlan | None,
    ) -> None:
        """Run the selected policy through the same bounded session as manual control."""
        if self.data is None:
            return
        intent = decision.intent if decision.accepted else None
        if self._predictive_control_enabled:
            intent = None
            if predictive_plan is not None and predictive_plan.target_power_w > 0:
                intent, reason = self._validated_predictive_intent(data, predictive_plan)
                if intent is None:
                    self._active_control_last_error = reason
                    _LOGGER.warning("Predictive scheduled control blocked: %s", reason)
            elif (
                predictive_plan is not None
                and decision.accepted
                and decision.intent is not None
                and decision.intent.target_power_w < 0
            ):
                # The planner never discharges; retain an explicitly matching
                # discharge rule while the planner is active.
                intent = decision.intent
        if not data.active_control_available or intent is None:
            await self.stop_active_control()
            return
        target = intent.target_power_w
        if self.active_control_running and self._active_control_power_w == target:
            return
        await self.stop_active_control()
        duration = max(
            1, min(intent.hold_seconds or 1, self._active_control_max_duration_seconds)
        )
        try:
            await self.start_active_control(target, duration)
        except ControlWriteError as error:
            self._active_control_last_error = str(error)
            _LOGGER.warning("Scheduled active-control command blocked: %s", error)

    def _validated_predictive_intent(
        self, data: PowerManagerData, plan: PredictivePlan
    ) -> tuple[ControlIntent | None, str | None]:
        """Turn one forecast recommendation into a freshly validated intent."""
        intent = ControlIntent(
            "predictive",
            plan.target_power_w,
            min(300, self._active_control_max_duration_seconds),
            datetime.now(UTC),
        )
        valid, reason = validate_intent(
            intent,
            data.energy_state,
            SafetyConfig(
                max_charge_power_w=min(
                    self._active_control_max_power_w, self._predictive_max_charge_power_w
                ),
                max_discharge_power_w=self._active_control_max_power_w,
                minimum_soc_percent=self._predictive_reserve_soc_percent,
                max_energy_age_seconds=self._config_max_age,
            ),
            enabled=True,
            at=datetime.now(UTC),
        )
        return (intent, None) if valid else (None, reason)

    @property
    def _config_max_age(self) -> int:
        """Return the configured telemetry freshness limit."""
        return self._telemetry_max_age

    async def _read_energy_dashboard(self) -> EnergyDashboardRuntime:
        """Read optional Energy Dashboard inputs without masking Sunny Island health."""
        try:
            runtime = await self._energy_dashboard_provider.read()
            if runtime.configuration.configured and not self._forecast_provider.configured:
                missing = (
                    *runtime.configuration.missing,
                    "PowerManager: no whole-home remaining-load forecast",
                )
                runtime = replace(
                    runtime,
                    configuration=replace(
                        runtime.configuration,
                        missing=missing,
                        summary=f"{runtime.configuration.summary}\n- Missing: {missing[-1]}",
                    ),
                )
            return runtime
        except Exception as error:  # Dashboard integration is an optional adapter.
            _LOGGER.warning("Energy Dashboard inputs unavailable: %s", error)
            return EnergyDashboardRuntime(
                EnergyDashboardConfiguration(summary="Energy Dashboard is unavailable."),
                None,
                None,
                None,
            )

    def _predictive_plan(
        self,
        battery_state: BatteryState,
        forecast_state: ForecastState | None,
        grid_state: GridState | None,
    ) -> PredictivePlan | None:
        """Return a forecast plan for sensors and the opt-in scheduler."""
        if (
            forecast_state is None
            or forecast_state.communication_state is not CommunicationState.ONLINE
            or forecast_state.remaining_pv_kwh is None
            or forecast_state.expected_remaining_load_kwh is None
            or battery_state.battery_soc_percent is None
        ):
            return None
        available_pv_surplus_w = _available_pv_surplus_w(grid_state)
        try:
            return plan_predictive_charge(
                PredictiveInputs(
                    timestamp=battery_state.timestamp,
                    horizon_end=_next_local_midnight(battery_state.timestamp, self._timezone),
                    usable_capacity_kwh=self._predictive_capacity_kwh,
                    battery_soc_percent=battery_state.battery_soc_percent,
                    end_soc_target_percent=self._predictive_end_soc_percent,
                    reserve_soc_percent=self._predictive_reserve_soc_percent,
                    remaining_pv_kwh=forecast_state.remaining_pv_kwh,
                    remaining_load_kwh=forecast_state.expected_remaining_load_kwh,
                    forecast_uncertainty_kwh=0.0,
                    export_capacity_kwh=self._predictive_export_capacity_kwh,
                    max_charge_power_w=self._predictive_max_charge_power_w,
                    reported_charge_limit_w=battery_state.charge_limit_w,
                    available_pv_surplus_w=available_pv_surplus_w,
                    # A live predictive schedule is always PV-surplus-only.
                    # Keep the legacy option available for shadow analysis,
                    # but never let it authorize a grid charge.
                    grid_charge_allowed=(
                        self._predictive_grid_charge_allowed
                        and not self._predictive_control_enabled
                    ),
                )
            )
        except PredictivePlanningError:
            return None

    @staticmethod
    def _predictive_reason(forecast_state) -> str:
        if forecast_state is None:
            return "forecast_unavailable"
        if forecast_state.remaining_pv_kwh is None:
            return "pv_forecast_unavailable"
        if forecast_state.expected_remaining_load_kwh is None:
            return "load_forecast_unavailable"
        return "invalid_planning_inputs"

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


def _aggregate_inverter_grid(states: tuple[InverterState, ...]) -> GridState | None:
    """Aggregate generation values when no site grid entity exists.

    Grid import/export cannot be inferred from inverter generation. It remains
    a site-meter input, while PV output is safe to sum across inverter sources.
    """
    pv_values = [
        state.generation_power_w
        for state in states
        if state.generation_power_w is not None
    ]
    if not pv_values:
        return None
    timestamps = [state.timestamp for state in states]
    return GridState(
        timestamp=max(timestamps),
        grid_power_w=None,
        pv_power_w=sum(pv_values) if pv_values else None,
        communication_state=(
            CommunicationState.ONLINE
            if any(state.communication_state is CommunicationState.ONLINE for state in states)
            else CommunicationState.UNKNOWN
        ),
    )


def _available_pv_surplus_w(grid: GridState | None) -> float | None:
    """Return the instantaneous PV surplus available to a scheduled plan."""
    if grid is None or grid.pv_power_w is None or grid.load_power_w is None:
        return None
    values = (grid.pv_power_w, grid.load_power_w, grid.grid_power_w)
    if any(value is not None and not math.isfinite(value) for value in values):
        return None
    surplus = max(grid.pv_power_w - grid.load_power_w, 0.0)
    if grid.grid_power_w is not None:
        surplus = min(surplus, max(-grid.grid_power_w, 0.0))
    return surplus


def _aggregate_inverter_forecast(
    sources: tuple[InverterSourceConfig, ...], states: tuple[InverterState, ...]
) -> ForecastState | None:
    """Aggregate PV forecasts only when every configured source is fresh."""
    source_by_id = {source.source_id: source for source in sources}
    forecast_states = [
        state
        for state in states
        if source_by_id.get(state.source_id)
        and source_by_id[state.source_id].forecasts_pv
        and source_by_id[state.source_id].remaining_pv_forecast_entity
    ]
    configured = [
        source
        for source in sources
        if source.forecasts_pv and source.remaining_pv_forecast_entity
    ]
    if not configured or len(forecast_states) != len(configured):
        return None
    if any(
        state.communication_state is not CommunicationState.ONLINE
        or state.remaining_pv_forecast_kwh is None
        for state in forecast_states
    ):
        return None
    return ForecastState(
        timestamp=max(state.timestamp for state in forecast_states),
        remaining_pv_kwh=sum(
            state.remaining_pv_forecast_kwh for state in forecast_states
        ),
        communication_state=CommunicationState.ONLINE,
    )


def _derive_load_power(grid: GridState | None, battery: BatteryState) -> GridState | None:
    """Derive whole-home load from fresh site power balance when possible."""
    if (
        grid is None
        or grid.load_power_w is not None
        or grid.grid_power_w is None
        or grid.pv_power_w is None
        or battery.battery_power_w is None
        or grid.communication_state is not CommunicationState.ONLINE
        or battery.communication_state is not CommunicationState.ONLINE
    ):
        return grid
    return replace(
        grid,
        load_power_w=grid.grid_power_w + grid.pv_power_w + battery.battery_power_w,
    )


def _merge_forecasts(
    site_forecast: ForecastState | None, inverter_forecast: ForecastState | None
) -> ForecastState | None:
    """Combine site-wide load with aggregate inverter PV forecast."""
    if site_forecast is None:
        return inverter_forecast
    if inverter_forecast is None:
        return site_forecast
    return replace(
        site_forecast,
        remaining_pv_kwh=(
            site_forecast.remaining_pv_kwh
            if site_forecast.remaining_pv_kwh is not None
            else inverter_forecast.remaining_pv_kwh
        ),
        pv_power_forecast_w=(
            site_forecast.pv_power_forecast_w
            if site_forecast.pv_power_forecast_w is not None
            else inverter_forecast.pv_power_forecast_w
        ),
        pv_power_forecast_profile=(
            site_forecast.pv_power_forecast_profile
            or inverter_forecast.pv_power_forecast_profile
        ),
        load_power_forecast_w=(
            site_forecast.load_power_forecast_w
            if site_forecast.load_power_forecast_w is not None
            else inverter_forecast.load_power_forecast_w
        ),
        load_power_forecast_profile=(
            site_forecast.load_power_forecast_profile
            or inverter_forecast.load_power_forecast_profile
        ),
    )


def _ha_timezone(hass: HomeAssistant):
    """Resolve Home Assistant's configured timezone for rule windows."""
    try:
        return ZoneInfo(hass.config.time_zone)
    except (ZoneInfoNotFoundError, AttributeError):
        _LOGGER.warning("Unknown Home Assistant timezone; using timestamps as provided")
        return None


def _next_local_midnight(at: datetime, timezone) -> datetime:
    """Return the next local midnight as an aware timestamp when possible."""
    local = at.astimezone(timezone) if timezone is not None else at
    next_day = local.date() + timedelta(days=1)
    return datetime.combine(next_day, time.min, tzinfo=local.tzinfo)


def _parse_host_list(value: object) -> set[str]:
    """Parse the explicit comma-separated list of reporting-only senders."""
    if not isinstance(value, str):
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}
