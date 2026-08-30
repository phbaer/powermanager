"""UI configuration flow for the read-only PowerManager integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_HOST, CONF_PORT, CONF_UNIT_ID, DEFAULT_PORT, DEFAULT_UNIT_ID, DOMAIN
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
