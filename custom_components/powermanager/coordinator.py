"""Single polling coordinator that orchestrates the independent core."""

from __future__ import annotations

import asyncio
import logging
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
    DEFAULT_PREDICTIVE_CAPACITY_KWH,
    DEFAULT_PREDICTIVE_END_SOC_PERCENT,
    DEFAULT_PREDICTIVE_EXPORT_CAPACITY_KWH,
    DEFAULT_PREDICTIVE_MAX_CHARGE_POWER_W,
    DEFAULT_PREDICTIVE_RESERVE_SOC_PERCENT,
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
from .core.powermanager_core.control.predictive import (
    PredictiveInputs,
    PredictivePlan,
    PredictivePlanningError,
    plan_predictive_charge,
)
from .core.powermanager_core.control.rules import parse_rules_document
from .core.powermanager_core.control.runtime import ControlRuntime
from .core.powermanager_core.control.watchdog import ControlWatchdog
from .core.powermanager_core.exceptions import PowerManagerError, UnsupportedDeviceError
from .core.powermanager_core.inverters import InverterSourceConfig, parse_inverter_sources
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
        self._inverter_sources: tuple[InverterSourceConfig, ...] = parse_inverter_sources(
            entry.options.get(CONF_INVERTERS)
        )
        self._inverter_provider = HomeAssistantEntityInverterProvider(
            hass,
            self._inverter_sources,
            entry.options.get(CONF_TELEMETRY_MAX_AGE, DEFAULT_TELEMETRY_MAX_AGE_SECONDS),
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

    def start_speedwire_monitor(self) -> None:
        """Start passive multicast observation without affecting Modbus polling."""
        if self._speedwire_task is None:
            self._speedwire_task = asyncio.create_task(self._observe_speedwire())

    @property
    def inverter_sources(self) -> tuple[InverterSourceConfig, ...]:
        """Return configured per-inverter telemetry sources."""
        return self._inverter_sources

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
                    self._speedwire_monitor.inverter_addresses = (
                        await self._resolve_inverter_addresses()
                    )
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
        return replace(
            data,
            possible_external_controller=monitor.possible_external_controller,
            speedwire_sources=tuple(sorted(monitor.observed_sources)),
            speedwire_external_sources=monitor.external_sources,
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
        inverter_states = await self._inverter_provider.read_states()
        if grid_state is None:
            grid_state = _aggregate_inverter_grid(inverter_states)
        if forecast_state is None:
            forecast_state = _aggregate_inverter_forecast(inverter_states)
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
        predictive_plan = self._predictive_plan(battery_state, forecast_state)
        return self._with_observation(PowerManagerData(
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
        ))

    def _predictive_plan(
        self, battery_state: BatteryState, forecast_state: ForecastState | None
    ) -> PredictivePlan | None:
        """Return a forecast plan for shadow sensors without any actuator call."""
        if (
            forecast_state is None
            or forecast_state.communication_state is not CommunicationState.ONLINE
            or forecast_state.remaining_pv_kwh is None
            or forecast_state.expected_remaining_load_kwh is None
            or battery_state.battery_soc_percent is None
        ):
            return None
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
                    grid_charge_allowed=self._predictive_grid_charge_allowed,
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
    """Aggregate complete directional readings when no site grid entity exists."""
    directional = [
        state
        for state in states
        if state.import_power_w is not None or state.export_power_w is not None
    ]
    if directional and any(
        state.import_power_w is None or state.export_power_w is None for state in directional
    ):
        directional = []
    pv_values = [state.pv_power_w for state in states if state.pv_power_w is not None]
    if not directional and not pv_values:
        return None
    timestamps = [state.timestamp for state in states]
    return GridState(
        timestamp=max(timestamps),
        grid_power_w=(
            sum(state.import_power_w - state.export_power_w for state in directional)
            if directional
            else None
        ),
        pv_power_w=sum(pv_values) if pv_values else None,
        communication_state=(
            CommunicationState.ONLINE
            if any(state.communication_state is CommunicationState.ONLINE for state in states)
            else CommunicationState.UNKNOWN
        ),
    )


def _aggregate_inverter_forecast(states: tuple[InverterState, ...]) -> ForecastState | None:
    """Aggregate forecasts only when every configured forecast is complete and fresh."""
    forecasts = [state.forecast for state in states]
    if not forecasts or any(forecast is None for forecast in forecasts):
        return None
    if any(
        forecast.communication_state is not CommunicationState.ONLINE
        or forecast.remaining_pv_kwh is None
        or forecast.expected_remaining_load_kwh is None
        for forecast in forecasts
        if forecast is not None
    ):
        return None
    return ForecastState(
        timestamp=max(forecast.timestamp for forecast in forecasts if forecast is not None),
        remaining_pv_kwh=sum(
            forecast.remaining_pv_kwh for forecast in forecasts if forecast is not None
        ),
        expected_remaining_load_kwh=sum(
            forecast.expected_remaining_load_kwh for forecast in forecasts if forecast is not None
        ),
        communication_state=CommunicationState.ONLINE,
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
