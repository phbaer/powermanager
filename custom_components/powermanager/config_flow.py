"""UI configuration flow for the read-only PowerManager integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_GRID_POWER_ENTITY,
    CONF_HOST,
    CONF_LOAD_POWER_ENTITY,
    CONF_PORT,
    CONF_PRICE_ENTITY,
    CONF_PV_POWER_ENTITY,
    CONF_SCAN_INTERVAL,
    CONF_TELEMETRY_MAX_AGE,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEFAULT_TELEMETRY_MAX_AGE_SECONDS,
    DEFAULT_UNIT_ID,
    DOMAIN,
    MAX_SCAN_INTERVAL_SECONDS,
    MAX_TELEMETRY_MAX_AGE_SECONDS,
    MIN_SCAN_INTERVAL_SECONDS,
    MIN_TELEMETRY_MAX_AGE_SECONDS,
)
from .core.powermanager_core.backends.sma_sunny_island import (
    SunnyIslandClient,
    SunnyIslandConnectionConfig,
)
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
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL_SECONDS, max=MAX_SCAN_INTERVAL_SECONDS),
                ),
                vol.Optional(
                    CONF_GRID_POWER_ENTITY,
                    default=self._config_entry.options.get(CONF_GRID_POWER_ENTITY, ""),
                ): str,
                vol.Optional(
                    CONF_PV_POWER_ENTITY,
                    default=self._config_entry.options.get(CONF_PV_POWER_ENTITY, ""),
                ): str,
                vol.Optional(
                    CONF_LOAD_POWER_ENTITY,
                    default=self._config_entry.options.get(CONF_LOAD_POWER_ENTITY, ""),
                ): str,
                vol.Optional(
                    CONF_PRICE_ENTITY,
                    default=self._config_entry.options.get(CONF_PRICE_ENTITY, ""),
                ): str,
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
        return self.async_show_form(step_id="init", data_schema=schema)
