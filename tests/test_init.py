"""Tests for the TechnitiumDNS integration setup, unload and migration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.technitiumdns.config_flow import CONFIG_VERSION
from custom_components.technitiumdns.const import DOMAIN
from technitiumdns import InvalidTokenError, TransportError


def _patch_client(**kwargs):
    return patch(
        "custom_components.technitiumdns.create_api_client",
        AsyncMock(**kwargs),
    )


async def test_setup_and_unload(hass: HomeAssistant, config_entry, mock_api) -> None:
    """The entry sets up, populates hass.data, then unloads cleanly."""
    config_entry.add_to_hass(hass)

    with _patch_client(return_value=mock_api):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.runtime_data is not None
    assert config_entry.runtime_data.api is mock_api

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_auth_failed(hass: HomeAssistant, config_entry) -> None:
    """An invalid token puts the entry in the error state (triggers reauth)."""
    config_entry.add_to_hass(hass)

    with _patch_client(side_effect=InvalidTokenError("bad token")):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_setup_cannot_connect(hass: HomeAssistant, config_entry) -> None:
    """A transport error puts the entry in the retry state (ConfigEntryNotReady)."""
    config_entry.add_to_hass(hass)

    with _patch_client(side_effect=TransportError("no route")):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_migrate_from_v1(hass: HomeAssistant, mock_api) -> None:
    """A version 1 entry is migrated up to the current schema version."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Home DNS",
        version=1,
        data={
            "api_url": "http://dns.local:5380",
            "token": "s3cr3t",
            "server_name": "Home DNS",
            "username": "admin",
            "stats_duration": "last_hour",
        },
        options={},
    )
    entry.add_to_hass(hass)

    with _patch_client(return_value=mock_api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.version == CONFIG_VERSION
    # v1 -> v2 migration adds the check_ssl default
    assert entry.data["check_ssl"] is True
    # v3 -> v4 migration adds the cluster_mode default
    assert entry.data["cluster_mode"] is False
