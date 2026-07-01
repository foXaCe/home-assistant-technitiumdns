"""Tests for the TechnitiumDNS config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from technitiumdns import InvalidTokenError, TransportError

from custom_components.technitiumdns.const import DOMAIN

USER_INPUT = {
    "api_url": "http://dns.local:5380",
    "token": "s3cr3t",
    "check_ssl": True,
    "cluster_mode": False,
    "server_name": "Home DNS",
    "username": "admin",
    "stats_duration": "last_hour",
}


async def _run_user_flow(hass: HomeAssistant, side_effect=None, return_value=None):
    with patch(
        "custom_components.technitiumdns.config_flow.create_api_client",
        AsyncMock(side_effect=side_effect, return_value=return_value),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )


async def test_user_flow_success(hass: HomeAssistant, mock_api) -> None:
    """A valid configuration creates the config entry."""
    result = await _run_user_flow(hass, return_value=mock_api)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home DNS"
    assert result["data"]["stats_duration"] == "last_hour"


async def test_user_flow_invalid_auth(hass: HomeAssistant) -> None:
    """An invalid token surfaces the auth error."""
    result = await _run_user_flow(hass, side_effect=InvalidTokenError("bad token"))

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "auth"}


async def test_user_flow_cannot_connect(hass: HomeAssistant) -> None:
    """A transport error surfaces the cannot_connect error."""
    result = await _run_user_flow(hass, side_effect=TransportError("no route"))

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_unknown_error(hass: HomeAssistant) -> None:
    """An unexpected error surfaces the unknown error."""
    result = await _run_user_flow(hass, side_effect=ValueError("boom"))

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}
