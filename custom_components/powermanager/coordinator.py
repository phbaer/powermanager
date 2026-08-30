"""Single polling coordinator that orchestrates the independent core."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_GRID_POWER_ENTITY,
    CONF_HOST,
    CONF_LOAD_POWER_ENTITY,
    CONF_PORT,
    CONF_PV_POWER_ENTITY,
    CONF_SCAN_INTERVAL,
    CONF_TELEMETRY_MAX_AGE,
    CONF_UNIT_ID,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEFAULT_TELEMETRY_MAX_AGE_SECONDS,
    DOMAIN,
)
from .core.powermanager_core.backends.sma_sunny_island import (
    SunnyIslandClient,
    SunnyIslandConnectionConfig,
)
from .core.powermanager_core.exceptions import PowerManagerError
from .core.powermanager_core.models import BatteryState, DeviceInfo, EnergyState
from .ha_entity_provider import HomeAssistantEntityGridProvider

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PowerManagerData:
    """A successful, read-only coordinator update."""

    device_info: DeviceInfo
    battery_state: BatteryState
    energy_state: EnergyState


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
        )

    async def _async_update_data(self) -> PowerManagerData:
        """Read state through a new TCP connection, allowing safe reconnects."""
        try:
            async with SunnyIslandClient(self._config) as client:
                device_info = await client.get_device_info()
                battery_state = await client.read_state()
        except PowerManagerError as error:
            raise UpdateFailed(str(error)) from error
        except Exception as error:
            raise UpdateFailed(f"Unexpected PowerManager update failure: {error}") from error

        grid_state = (
            await self._grid_provider.read_grid_state()
            if self._grid_provider.configured
            else None
        )
        return PowerManagerData(
            device_info=device_info,
            battery_state=battery_state,
            energy_state=EnergyState(
                timestamp=battery_state.timestamp, battery=battery_state, grid=grid_state
            ),
        )
