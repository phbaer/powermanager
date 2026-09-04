"""UI setup and option-flow tests without device communication."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.powermanager.const import DOMAIN


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
