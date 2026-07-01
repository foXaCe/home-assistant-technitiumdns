"""Tests for the system health info."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.technitiumdns import system_health as sh
from custom_components.technitiumdns.const import DOMAIN


async def test_system_health_info(hass: HomeAssistant) -> None:
    """It reports the configured servers and a reachability check."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Home DNS",
        data={"api_url": "http://dns.local:5380", "token": "s3cr3t"},
    )
    entry.add_to_hass(hass)

    with patch.object(
        sh.system_health,
        "async_check_can_reach_url",
        new=MagicMock(return_value="ok"),
    ) as reach:
        info = await sh.system_health_info(hass)

    assert info["configured_servers"] == 1
    assert info["can_reach_server"] == "ok"
    reach.assert_called_once_with(hass, "http://dns.local:5380")


async def test_system_health_info_no_entries(hass: HomeAssistant) -> None:
    """With no config entry, it reports zero servers and no reachability key."""
    info = await sh.system_health_info(hass)
    assert info == {"configured_servers": 0}
