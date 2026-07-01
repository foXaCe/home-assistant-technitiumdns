"""Tests for the diagnostics dump."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.technitiumdns.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics_redacts_secrets(
    hass: HomeAssistant, config_entry, mock_api
) -> None:
    """Diagnostics expose entry state with the token and URL redacted."""
    config_entry.add_to_hass(hass)
    with patch(
        "custom_components.technitiumdns.create_api_client",
        AsyncMock(return_value=mock_api),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, config_entry)

    assert diag["entry"]["data"]["token"] == "**REDACTED**"
    assert diag["entry"]["data"]["api_url"] == "**REDACTED**"
    assert diag["entry"]["data"]["username"] == "**REDACTED**"
    assert diag["entry"]["data"]["server_name"] == "Home DNS"
    assert diag["server_name"] == "Home DNS"
    assert diag["dhcp"]["enabled"] is False
