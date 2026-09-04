"""UI configuration flow for the read-only PowerManager integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
import yaml
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    BooleanSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
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
    DEFAULT_LOAD_FORECAST_HISTORY_DAYS,
    DEFAULT_PORT,
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

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Update the coordinator polling interval."""
        errors: dict[str, str] = {}
        if user_input is not None:
            grid_power_entity = user_input.get(CONF_GRID_POWER_ENTITY)
            grid_import_power_entity = user_input.get(CONF_GRID_IMPORT_POWER_ENTITY)
            grid_export_power_entity = user_input.get(CONF_GRID_EXPORT_POWER_ENTITY)
            load_power_entity = user_input.get(CONF_LOAD_POWER_ENTITY) or self._option(
                CONF_LOAD_POWER_ENTITY
            )
            estimate_remaining_load = user_input.get(CONF_ESTIMATE_REMAINING_LOAD, False)
            remaining_load_forecast_entity = user_input.get(CONF_REMAINING_LOAD_FORECAST_ENTITY)
            price_entity = user_input.get(CONF_PRICE_ENTITY)
            static_price = user_input.get(CONF_STATIC_PRICE_PER_KWH)
            rules_yaml = user_input.get(CONF_RULES_YAML)
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
            elif rules_yaml:
                try:
                    parse_rules_document(yaml.safe_load(rules_yaml))
                except (TypeError, ValueError, yaml.YAMLError):
                    errors["base"] = "invalid_rules"
            elif price_entity and static_price is not None:
                errors["base"] = "price_source_conflict"
            elif static_price is not None:
                try:
                    user_input[CONF_STATIC_PRICE_PER_KWH] = float(static_price)
                except (TypeError, ValueError):
                    errors["base"] = "invalid_static_price"
                else:
                    if user_input[CONF_STATIC_PRICE_PER_KWH] < 0:
                        errors["base"] = "invalid_static_price"
            if not errors:
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
                self._optional_field(CONF_GRID_POWER_ENTITY, self._option(CONF_GRID_POWER_ENTITY)):
                    _POWER_ENTITY_SELECTOR,
                self._optional_field(
                    CONF_GRID_IMPORT_POWER_ENTITY, self._option(CONF_GRID_IMPORT_POWER_ENTITY)
                ): _POWER_ENTITY_SELECTOR,
                self._optional_field(
                    CONF_GRID_EXPORT_POWER_ENTITY, self._option(CONF_GRID_EXPORT_POWER_ENTITY)
                ): _POWER_ENTITY_SELECTOR,
                self._optional_field(CONF_PV_POWER_ENTITY, self._option(CONF_PV_POWER_ENTITY)):
                    _POWER_ENTITY_SELECTOR,
                self._optional_field(CONF_LOAD_POWER_ENTITY, self._option(CONF_LOAD_POWER_ENTITY)):
                    _POWER_ENTITY_SELECTOR,
                vol.Optional(
                    CONF_ESTIMATE_REMAINING_LOAD,
                    default=self._config_entry.options.get(CONF_ESTIMATE_REMAINING_LOAD, False),
                ): _BOOLEAN_SELECTOR,
                vol.Required(
                    CONF_LOAD_FORECAST_HISTORY_DAYS,
                    default=self._config_entry.options.get(
                        CONF_LOAD_FORECAST_HISTORY_DAYS,
                        DEFAULT_LOAD_FORECAST_HISTORY_DAYS,
                    ),
                ): _LOAD_FORECAST_DAYS_SELECTOR,
                self._optional_field(CONF_PRICE_ENTITY, self._option(CONF_PRICE_ENTITY)):
                    _PRICE_ENTITY_SELECTOR,
                self._optional_field(CONF_STATIC_PRICE_PER_KWH, static_price_default):
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
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    def _option(self, key: str) -> str | None:
        """Return an optional selector default without presenting an empty value."""
        return self._config_entry.options.get(key) or None

    @staticmethod
    def _optional_field(key: str, default: Any) -> vol.Optional:
        """Create an optional form field without injecting an invalid null default."""
        return vol.Optional(key) if default is None else vol.Optional(key, default=default)

    def _option_number(self, key: str) -> float | None:
        """Return an optional numeric default, preserving zero as a valid value."""
        value = self._config_entry.options.get(key)
        return float(value) if value is not None else None

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
