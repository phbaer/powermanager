"""UI setup and option-flow tests without device communication."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.powermanager.config_flow import PowerManagerOptionsFlow
from custom_components.powermanager.const import DOMAIN
from custom_components.powermanager.core.powermanager_core.models import CommunicationState
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

    assert data == {"scan_interval": 30, "telemetry_max_age": 120}
