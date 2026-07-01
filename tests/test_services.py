"""Tests for the integration services (cleanup_devices, get_dhcp_leases)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.technitiumdns.config_flow import CONFIG_VERSION
from custom_components.technitiumdns.const import DOMAIN


class _Lease:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def get(self, key, default=None):
        return getattr(self, key, default)


def _leases():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        _Lease(
            address="192.168.1.50",
            hardware_address="AA:BB:CC:00:00:01",
            host_name="raspberrypi",
            client_identifier="cid",
            lease_obtained=now,
            lease_expires=now,
            scope="192.168.1.0/24",
            address_status="InUse",
            type="Dynamic",
        )
    ]


async def _setup(hass: HomeAssistant, mock_api):
    mock_api.dhcp.leases_list = AsyncMock(return_value=_leases())
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
        options={
            "enable_dhcp_tracking": True,
            "dhcp_update_interval": 60,
            "dhcp_ip_filter_mode": "disabled",
            "dhcp_ip_ranges": "",
            "dhcp_log_tracking": False,
            "dhcp_smart_activity": False,
        },
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.technitiumdns.create_api_client",
        AsyncMock(return_value=mock_api),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_services_are_registered(hass: HomeAssistant, mock_api) -> None:
    await _setup(hass, mock_api)
    assert hass.services.has_service(DOMAIN, "cleanup_devices")
    assert hass.services.has_service(DOMAIN, "get_dhcp_leases")


async def test_get_dhcp_leases_fires_event(hass: HomeAssistant, mock_api) -> None:
    await _setup(hass, mock_api)

    events = []
    hass.bus.async_listen(
        f"{DOMAIN}_dhcp_leases_retrieved", lambda e: events.append(e)
    )

    await hass.services.async_call(DOMAIN, "get_dhcp_leases", {}, blocking=True)
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["total_leases"] == 1
    assert events[0].data["leases"][0]["address"] == "192.168.1.50"


async def test_get_dhcp_leases_filter_scope_no_match(
    hass: HomeAssistant, mock_api
) -> None:
    await _setup(hass, mock_api)

    events = []
    hass.bus.async_listen(
        f"{DOMAIN}_dhcp_leases_retrieved", lambda e: events.append(e)
    )

    await hass.services.async_call(
        DOMAIN, "get_dhcp_leases", {"filter_scope": "10.0.0.0/8"}, blocking=True
    )
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["total_leases"] == 0


async def test_cleanup_devices_runs(hass: HomeAssistant, mock_api) -> None:
    entry = await _setup(hass, mock_api)
    # should not raise; runs the orphan-analysis path
    await hass.services.async_call(
        DOMAIN, "cleanup_devices", {"config_entry_id": entry.entry_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert entry.runtime_data is not None
