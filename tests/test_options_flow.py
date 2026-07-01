"""Tests for the options flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.technitiumdns.config_flow import CONFIG_VERSION
from custom_components.technitiumdns.const import DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _setup(hass: HomeAssistant, mock_api):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Home DNS",
        version=CONFIG_VERSION,
        data={
            "api_url": "http://dns.local:5380",
            "token": "s3cr3t",
            "check_ssl": True,
            "cluster_mode": False,
            "server_name": "Home DNS",
            "username": "admin",
            "stats_duration": "last_hour",
        },
        options={"enable_dhcp_tracking": False},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.technitiumdns.create_api_client",
        AsyncMock(return_value=mock_api),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_options_flow_saves(hass: HomeAssistant, mock_api) -> None:
    entry = await _setup(hass, mock_api)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    with patch(
        "custom_components.technitiumdns.create_api_client",
        AsyncMock(return_value=mock_api),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"enable_dhcp_tracking": False, "dhcp_ip_filter_mode": "disabled"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_flow_numeric_selectors(hass: HomeAssistant, mock_api) -> None:
    """Numeric selectors accept, persist and round-trip string values as ints."""
    entry = await _setup(hass, mock_api)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(
        "custom_components.technitiumdns.create_api_client",
        AsyncMock(return_value=mock_api),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "enable_dhcp_tracking": False,
                "dhcp_update_interval": "300",
                "stats_update_interval": "120",
                "dhcp_ip_filter_mode": "exclude",
                "dhcp_stale_threshold": "60",
                "activity_score_threshold": "76",
                "activity_analysis_window": "120",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    opts = entry.options
    # SelectSelector stores the chosen value as a string...
    assert opts["dhcp_update_interval"] == "300"
    assert opts["dhcp_ip_filter_mode"] == "exclude"
    # ...but every numeric option stays coercible to int for consumers.
    assert int(opts["stats_update_interval"]) == 120
    assert int(opts["dhcp_stale_threshold"]) == 60
    assert int(opts["activity_score_threshold"]) == 76
    assert int(opts["activity_analysis_window"]) == 120


async def test_options_flow_dhcp_test_step(hass: HomeAssistant, mock_api) -> None:
    entry = await _setup(hass, mock_api)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(
        "custom_components.technitiumdns.config_flow.create_api_client",
        AsyncMock(return_value=mock_api),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"test_dhcp": True, "dhcp_ip_filter_mode": "disabled"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "dhcp_test"
