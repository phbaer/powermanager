"""UI configuration flow for the read-only PowerManager integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
import yaml
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector,
    BooleanSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_CONTROL_OWNERSHIP_CONFIRMED,
    CONF_ESTIMATE_REMAINING_LOAD,
    CONF_GRID_EXPORT_POWER_ENTITY,
    CONF_GRID_IMPORT_POWER_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_HOST,
    CONF_INVERTER_PROFILE_COUNT,
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
    DEFAULT_LOAD_FORECAST_HISTORY_DAYS,
    DEFAULT_PORT,
    DEFAULT_PREDICTIVE_CAPACITY_KWH,
    DEFAULT_PREDICTIVE_END_SOC_PERCENT,
    DEFAULT_PREDICTIVE_EXPORT_CAPACITY_KWH,
    DEFAULT_PREDICTIVE_MAX_CHARGE_POWER_W,
    DEFAULT_PREDICTIVE_RESERVE_SOC_PERCENT,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEFAULT_TELEMETRY_MAX_AGE_SECONDS,
    DEFAULT_UNIT_ID,
    DOMAIN,
    MAX_LOAD_FORECAST_HISTORY_DAYS,
    MAX_SCAN_INTERVAL_SECONDS,
    MAX_TELEMETRY_MAX_AGE_SECONDS,
    MIN_LOAD_FORECAST_HISTORY_DAYS,
    MIN_SCAN_INTERVAL_SECONDS,
    MIN_TELEMETRY_MAX_AGE_SECONDS,
)
from .core.powermanager_core.backends.sma_sunny_island import (
    SunnyIslandClient,
    SunnyIslandConnectionConfig,
)
from .core.powermanager_core.control.rules import parse_rules_document
from .core.powermanager_core.exceptions import BackendConnectionError, UnsupportedDeviceError
from .core.powermanager_core.inverters import parse_inverter_sources
from .ha_energy_dashboard import (
    EnergyDashboardConfiguration,
    async_read_energy_dashboard_configuration,
)


async def validate_input(data: dict[str, Any]) -> str:
    """Perform a read-only compatibility check and return the device title."""
    config = SunnyIslandConnectionConfig(
        host=data[CONF_HOST], port=data[CONF_PORT], unit_id=data[CONF_UNIT_ID]
    )
    async with SunnyIslandClient(config) as client:
        info = await client.get_device_info()
    return info.model or data[CONF_HOST]


class PowerManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle UI configuration without issuing any battery-control command."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        """Return the polling options flow for an existing entry."""
        return PowerManagerOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure a Sunny Island connection."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                title = await validate_input(user_input)
            except BackendConnectionError:
                errors["base"] = "cannot_connect"
            except UnsupportedDeviceError:
                errors["base"] = "unsupported_device"
            except Exception:  # pragma: no cover - Home Assistant displays a safe fallback.
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_HOST].lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=title, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): vol.All(str, vol.Length(min=1)),
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=247)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class PowerManagerOptionsFlow(OptionsFlow):
    """Configure polling without changing the device connection."""

    def __init__(self, config_entry: Any) -> None:
        self._config_entry = config_entry
        self._pending_options: dict[str, Any] | None = None
        self._inverter_profile_count = 0
        self._inverter_profiles: list[dict[str, Any]] = []

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Update the coordinator polling interval."""
        errors: dict[str, str] = {}
        dashboard = await self._energy_dashboard_configuration()
        if user_input is not None:
            grid_power_entity = user_input.get(CONF_GRID_POWER_ENTITY)
            grid_import_power_entity = user_input.get(CONF_GRID_IMPORT_POWER_ENTITY)
            grid_export_power_entity = user_input.get(CONF_GRID_EXPORT_POWER_ENTITY)
            derived_load_entity = self._derived_load_power_entity()
            load_power_entity = (
                user_input.get(CONF_LOAD_POWER_ENTITY)
                or self._option(CONF_LOAD_POWER_ENTITY)
                or derived_load_entity
            )
            estimate_remaining_load = user_input.get(
                CONF_ESTIMATE_REMAINING_LOAD,
                self._config_entry.options.get(
                    CONF_ESTIMATE_REMAINING_LOAD, bool(derived_load_entity)
                ),
            )
            remaining_load_forecast_entity = user_input.get(
                CONF_REMAINING_LOAD_FORECAST_ENTITY,
                self._option(CONF_REMAINING_LOAD_FORECAST_ENTITY),
            )
            remaining_pv_forecast_entity = user_input.get(
                CONF_REMAINING_PV_FORECAST_ENTITY,
                self._option(CONF_REMAINING_PV_FORECAST_ENTITY),
            )
            price_entity = user_input.get(CONF_PRICE_ENTITY)
            static_price = user_input.get(CONF_STATIC_PRICE_PER_KWH)
            predictive_reserve = user_input.get(
                CONF_PREDICTIVE_RESERVE_SOC_PERCENT, DEFAULT_PREDICTIVE_RESERVE_SOC_PERCENT
            )
            predictive_end = user_input.get(
                CONF_PREDICTIVE_END_SOC_PERCENT, DEFAULT_PREDICTIVE_END_SOC_PERCENT
            )
            rules_yaml = user_input.get(CONF_RULES_YAML)
            inverters_yaml = user_input.get(CONF_INVERTERS)
            profile_count = int(user_input.get(CONF_INVERTER_PROFILE_COUNT, 0) or 0)
            if static_price == "":
                user_input.pop(CONF_STATIC_PRICE_PER_KWH, None)
                static_price = None
            if grid_power_entity and (
                grid_import_power_entity or grid_export_power_entity
            ):
                errors["base"] = "grid_power_source_conflict"
            elif bool(grid_import_power_entity) != bool(grid_export_power_entity):
                errors["base"] = "incomplete_grid_power_pair"
            elif estimate_remaining_load and remaining_load_forecast_entity:
                errors["base"] = "load_forecast_source_conflict"
            elif estimate_remaining_load and not load_power_entity:
                errors["base"] = "load_forecast_requires_load_power"
            if not errors and rules_yaml:
                try:
                    parse_rules_document(yaml.safe_load(rules_yaml))
                except (TypeError, ValueError, yaml.YAMLError):
                    errors["base"] = "invalid_rules"
            if not errors and inverters_yaml and profile_count:
                errors["base"] = "inverter_source_conflict"
            if not errors and inverters_yaml:
                try:
                    parse_inverter_sources(inverters_yaml)
                except (TypeError, ValueError, yaml.YAMLError):
                    errors["base"] = "invalid_inverters"
            if not errors and price_entity and static_price is not None:
                errors["base"] = "price_source_conflict"
            elif not errors and static_price is not None:
                try:
                    user_input[CONF_STATIC_PRICE_PER_KWH] = float(static_price)
                except (TypeError, ValueError):
                    errors["base"] = "invalid_static_price"
                else:
                    if user_input[CONF_STATIC_PRICE_PER_KWH] < 0:
                        errors["base"] = "invalid_static_price"
            if not errors and float(predictive_reserve) > float(predictive_end):
                errors["base"] = "invalid_predictive_targets"
            has_manual_grid = bool(
                grid_power_entity or (grid_import_power_entity and grid_export_power_entity)
            )
            if (
                not errors
                and dashboard.configured
                and not has_manual_grid
                and not dashboard.grid_power_entities
            ):
                errors["base"] = "missing_grid_power_entity"
            has_load_forecast = bool(remaining_load_forecast_entity) or bool(
                estimate_remaining_load and load_power_entity
            )
            if not errors and dashboard.configured and not has_load_forecast:
                errors["base"] = "missing_load_forecast"
            if (
                not errors
                and dashboard.configured
                and dashboard.missing
                and not profile_count
                and (inverters_yaml or "").strip() == dashboard.inverter_yaml().strip()
                and any(
                    item.startswith("PV ") or item.startswith("Inverters:")
                    for item in dashboard.missing
                )
            ):
                missing_generation = any(
                    item.startswith("PV ")
                    and "instantaneous generation" in item
                    for item in dashboard.missing
                )
                missing_forecast = any(
                    item.startswith("PV ")
                    and ("forecast" in item or "solar forecast" in item)
                    for item in dashboard.missing
                )
                if missing_generation or any(
                    item.startswith("Inverters:") for item in dashboard.missing
                ):
                    errors["base"] = "missing_inverter_telemetry"
                elif missing_forecast and not (
                    remaining_pv_forecast_entity
                    or self._option(CONF_REMAINING_PV_FORECAST_ENTITY)
                ):
                    errors["base"] = "missing_pv_forecast"
            if not errors and profile_count:
                self._pending_options = dict(user_input)
                self._pending_options.pop(CONF_INVERTER_PROFILE_COUNT, None)
                self._inverter_profile_count = profile_count
                self._inverter_profiles = []
                return await self.async_step_inverter()
            if not errors:
                imported_yaml = dashboard.inverter_yaml()
                if imported_yaml and (inverters_yaml or "").strip() == imported_yaml.strip():
                    user_input.pop(CONF_INVERTERS, None)
                user_input.pop(CONF_INVERTER_PROFILE_COUNT, None)
                return self.async_create_entry(title="", data=user_input)

        current_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
        )
        static_price_default = self._option_number(CONF_STATIC_PRICE_PER_KWH)
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL_SECONDS, max=MAX_SCAN_INTERVAL_SECONDS),
                ),
                self._optional_field(
                    CONF_GRID_POWER_ENTITY,
                    self._option(CONF_GRID_POWER_ENTITY)
                    or (
                        dashboard.grid_power_entities[0]
                        if len(dashboard.grid_power_entities) == 1
                        else None
                    ),
                ): _POWER_ENTITY_SELECTOR,
                self._optional_field(
                    CONF_GRID_IMPORT_POWER_ENTITY, self._option(CONF_GRID_IMPORT_POWER_ENTITY)
                ): _POWER_ENTITY_SELECTOR,
                self._optional_field(
                    CONF_GRID_EXPORT_POWER_ENTITY, self._option(CONF_GRID_EXPORT_POWER_ENTITY)
                ): _POWER_ENTITY_SELECTOR,
                self._optional_field(CONF_PV_POWER_ENTITY, self._option(CONF_PV_POWER_ENTITY)):
                    _POWER_ENTITY_SELECTOR,
                self._optional_field(
                    CONF_LOAD_POWER_ENTITY,
                    self._option(CONF_LOAD_POWER_ENTITY) or self._derived_load_power_entity(),
                ): _POWER_ENTITY_SELECTOR,
                vol.Optional(
                    CONF_ESTIMATE_REMAINING_LOAD,
                    default=self._config_entry.options.get(
                        CONF_ESTIMATE_REMAINING_LOAD,
                        bool(self._derived_load_power_entity()),
                    ),
                ): _BOOLEAN_SELECTOR,
                vol.Optional(
                    CONF_CONTROL_OWNERSHIP_CONFIRMED,
                    default=self._config_entry.options.get(
                        CONF_CONTROL_OWNERSHIP_CONFIRMED, False
                    ),
                ): _BOOLEAN_SELECTOR,
                vol.Required(
                    CONF_LOAD_FORECAST_HISTORY_DAYS,
                    default=self._config_entry.options.get(
                        CONF_LOAD_FORECAST_HISTORY_DAYS,
                        DEFAULT_LOAD_FORECAST_HISTORY_DAYS,
                    ),
                ): _LOAD_FORECAST_DAYS_SELECTOR,
                self._optional_field(
                    CONF_PRICE_ENTITY, self._option(CONF_PRICE_ENTITY) or dashboard.price_entity
                ): _PRICE_ENTITY_SELECTOR,
                self._optional_field(
                    CONF_STATIC_PRICE_PER_KWH,
                    static_price_default
                    if static_price_default is not None
                    else dashboard.static_price_per_kwh,
                ):
                    _STATIC_PRICE_SELECTOR,
                self._optional_field(
                    CONF_REMAINING_PV_FORECAST_ENTITY,
                    self._option_list(CONF_REMAINING_PV_FORECAST_ENTITY),
                ): _PV_FORECAST_ENTITY_SELECTOR,
                self._optional_field(
                    CONF_REMAINING_LOAD_FORECAST_ENTITY,
                    self._option(CONF_REMAINING_LOAD_FORECAST_ENTITY),
                ): _ENERGY_ENTITY_SELECTOR,
                self._optional_field(CONF_RULES_YAML, self._option(CONF_RULES_YAML)):
                    _RULES_SELECTOR,
                vol.Optional(
                    CONF_INVERTERS,
                    default=self._config_entry.options.get(CONF_INVERTERS)
                    or dashboard.inverter_yaml(),
                ): _INVERTERS_SELECTOR,
                vol.Optional(CONF_INVERTER_PROFILE_COUNT, default=0): _INVERTER_COUNT_SELECTOR,
                vol.Optional(
                    CONF_PREDICTIVE_CAPACITY_KWH,
                    default=self._option_number_or(
                        CONF_PREDICTIVE_CAPACITY_KWH, DEFAULT_PREDICTIVE_CAPACITY_KWH
                    ),
                ): _PREDICTIVE_CAPACITY_SELECTOR,
                vol.Optional(
                    CONF_PREDICTIVE_END_SOC_PERCENT,
                    default=self._option_number_or(
                        CONF_PREDICTIVE_END_SOC_PERCENT, DEFAULT_PREDICTIVE_END_SOC_PERCENT
                    ),
                ): _PREDICTIVE_SOC_SELECTOR,
                vol.Optional(
                    CONF_PREDICTIVE_RESERVE_SOC_PERCENT,
                    default=self._option_number_or(
                        CONF_PREDICTIVE_RESERVE_SOC_PERCENT,
                        DEFAULT_PREDICTIVE_RESERVE_SOC_PERCENT,
                    ),
                ): _PREDICTIVE_SOC_SELECTOR,
                vol.Optional(
                    CONF_PREDICTIVE_EXPORT_CAPACITY_KWH,
                    default=self._option_number_or(
                        CONF_PREDICTIVE_EXPORT_CAPACITY_KWH,
                        DEFAULT_PREDICTIVE_EXPORT_CAPACITY_KWH,
                    ),
                ): _PREDICTIVE_EXPORT_SELECTOR,
                vol.Optional(
                    CONF_PREDICTIVE_MAX_CHARGE_POWER_W,
                    default=self._option_number_or(
                        CONF_PREDICTIVE_MAX_CHARGE_POWER_W,
                        DEFAULT_PREDICTIVE_MAX_CHARGE_POWER_W,
                    ),
                ): _PREDICTIVE_POWER_SELECTOR,
                vol.Optional(
                    CONF_PREDICTIVE_GRID_CHARGE_ALLOWED,
                    default=self._config_entry.options.get(
                        CONF_PREDICTIVE_GRID_CHARGE_ALLOWED, False
                    ),
                ): _BOOLEAN_SELECTOR,
                vol.Required(
                    CONF_TELEMETRY_MAX_AGE,
                    default=self._config_entry.options.get(
                        CONF_TELEMETRY_MAX_AGE, DEFAULT_TELEMETRY_MAX_AGE_SECONDS
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_TELEMETRY_MAX_AGE_SECONDS, max=MAX_TELEMETRY_MAX_AGE_SECONDS
                    ),
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={"energy_dashboard_summary": dashboard.summary},
        )

    async def async_step_inverter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect one inverter profile with native HA entity selectors."""
        errors: dict[str, str] = {}
        if user_input is not None:
            profile = {
                key: value
                for key, value in user_input.items()
                if value not in (None, "")
            }
            profile["id"] = profile.get("id", "").lower()
            try:
                document = yaml.safe_dump(
                    {"inverters": [*self._inverter_profiles, profile]}, sort_keys=False
                )
                parse_inverter_sources(document)
            except (TypeError, ValueError, yaml.YAMLError):
                errors["base"] = "invalid_inverter_profile"
            else:
                self._inverter_profiles.append(profile)
                if len(self._inverter_profiles) >= self._inverter_profile_count:
                    assert self._pending_options is not None
                    self._pending_options[CONF_INVERTERS] = yaml.safe_dump(
                        {"inverters": self._inverter_profiles}, sort_keys=False
                    )
                    return self.async_create_entry(title="", data=self._pending_options)

        index = len(self._inverter_profiles) + 1
        schema = vol.Schema(
            {
                vol.Required("id"): vol.All(str, vol.Length(min=1, max=64)),
                vol.Required("role", default="pv"): _INVERTER_ROLE_SELECTOR,
                vol.Optional("generation_power_entity"): _POWER_ENTITY_SELECTOR,
                vol.Optional("battery_power_entity"): _POWER_ENTITY_SELECTOR,
                vol.Optional("remaining_pv_forecast_entity"): _ENERGY_ENTITY_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="inverter",
            data_schema=schema,
            errors=errors,
            description_placeholders={"index": index},
        )

    def _option(self, key: str) -> str | None:
        """Return an optional selector default without presenting an empty value."""
        return self._config_entry.options.get(key) or None

    def _derived_load_power_entity(self) -> str | None:
        """Return PowerManager's derived load sensor when it is registered."""
        hass = getattr(self, "hass", None)
        if hass is None:
            return None
        registry = er.async_get(hass)
        unique_id = f"{self._config_entry.unique_id or self._config_entry.entry_id}_load_power"
        return next(
            (
                entity.entity_id
                for entity in registry.entities.values()
                if entity.config_entry_id == self._config_entry.entry_id
                and entity.unique_id == unique_id
            ),
            None,
        )

    async def _energy_dashboard_configuration(self) -> EnergyDashboardConfiguration:
        """Return the live Energy Dashboard topology when HA provides it."""
        hass = getattr(self, "hass", None)
        if hass is None:
            return EnergyDashboardConfiguration()
        return await async_read_energy_dashboard_configuration(hass)

    @staticmethod
    def _optional_field(key: str, default: Any) -> vol.Optional:
        """Create an optional form field without injecting an invalid null default."""
        return vol.Optional(key) if default is None else vol.Optional(key, default=default)

    def _option_number(self, key: str) -> float | None:
        """Return an optional numeric default, preserving zero as a valid value."""
        value = self._config_entry.options.get(key)
        return float(value) if value is not None else None

    def _option_number_or(self, key: str, default: float) -> float:
        """Return a numeric option or its configured default."""
        return self._option_number(key) if self._option_number(key) is not None else default

    def _option_list(self, key: str) -> list[str] | None:
        """Return a multi-selector default and preserve existing string options."""
        value = self._config_entry.options.get(key)
        if value is None:
            return None
        return [value] if isinstance(value, str) else value


_POWER_ENTITY_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER)
)
_ENERGY_ENTITY_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.ENERGY)
)
_PV_FORECAST_ENTITY_SELECTOR = EntitySelector(
    EntitySelectorConfig(
        domain="sensor", device_class=SensorDeviceClass.ENERGY, multiple=True
    )
)
_SENSOR_ENTITY_SELECTOR = EntitySelector(EntitySelectorConfig(domain="sensor"))
_PRICE_ENTITY_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain=["sensor", "input_number"])
)
_STATIC_PRICE_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, step=0.001, mode=NumberSelectorMode.BOX)
)
_BOOLEAN_SELECTOR = BooleanSelector(BooleanSelectorConfig())
_LOAD_FORECAST_DAYS_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=MIN_LOAD_FORECAST_HISTORY_DAYS,
        max=MAX_LOAD_FORECAST_HISTORY_DAYS,
        step=1,
        mode=NumberSelectorMode.BOX,
    )
)
_RULES_SELECTOR = TextSelector(TextSelectorConfig(multiline=True))
_INVERTERS_SELECTOR = TextSelector(TextSelectorConfig(multiline=True))
_INVERTER_ROLE_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[
            {"value": "pv", "label": "PV inverter"},
            {"value": "battery", "label": "Battery inverter"},
            {"value": "hybrid", "label": "Hybrid inverter"},
        ]
    )
)
_INVERTER_COUNT_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=16, step=1, mode=NumberSelectorMode.BOX)
)
_PREDICTIVE_CAPACITY_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0.1, max=1000, step=0.1, mode=NumberSelectorMode.BOX)
)
_PREDICTIVE_EXPORT_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=1000, step=0.1, mode=NumberSelectorMode.BOX)
)
_PREDICTIVE_SOC_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=100, step=0.1, mode=NumberSelectorMode.BOX)
)
_PREDICTIVE_POWER_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=100000, step=1, mode=NumberSelectorMode.BOX)
)
