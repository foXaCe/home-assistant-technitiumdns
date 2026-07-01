"""Tests for the switch and button entity actions."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.technitiumdns.config_flow import CONFIG_VERSION
from custom_components.technitiumdns.const import DOMAIN


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


async def test_switch_turn_on_and_off(hass: HomeAssistant, mock_api) -> None:
    await _setup(hass, mock_api)
    switch_id = hass.states.async_entity_ids("switch")[0]

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": switch_id}, blocking=True
    )
    await hass.async_block_till_done()
    mock_api.settings.set.assert_awaited()

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": switch_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert mock_api.settings.set.await_count >= 2


async def test_button_press_disables_blocking(hass: HomeAssistant, mock_api) -> None:
    await _setup(hass, mock_api)
    # the temp-disable buttons call temporary_disable_blocking; the cleanup button
    # is only present with DHCP on, so pick a temp-disable one.
    buttons = hass.states.async_entity_ids("button")
    assert buttons
    await hass.services.async_call(
        "button", "press", {"entity_id": buttons[0]}, blocking=True
    )
    await hass.async_block_till_done()
    mock_api.settings.temporary_disable_blocking.assert_awaited()
