"""Fixtures for the TechnitiumDNS integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    yield


def _counter(value: int = 0) -> MagicMock:
    return MagicMock(hits=value)


def _named(name: str, hits: int) -> MagicMock:
    item = MagicMock()
    item.name = name
    item.hits = hits
    return item


@pytest.fixture
def stats_response() -> MagicMock:
    """A realistic api.dashboard.stats() response."""
    counters = MagicMock()
    counters.total_queries = 1000
    counters.total_blocked = 150
    counters.total_clients = 12
    counters.total_no_error = 800
    counters.total_server_failure = 5
    counters.total_nx_domain = 40
    counters.total_refused = 3
    counters.total_authoritative = 200
    counters.total_recursive = 600
    counters.total_cached = 190
    counters.total_dropped = 2
    counters.zones = 4
    counters.cached_entries = 5000
    counters.allowed_zones = 1
    counters.blocked_zones = 2
    counters.allow_list_zones = 1
    counters.block_list_zones = 3

    stats = MagicMock()
    stats.stats = counters
    stats.top_clients = [_named("192.168.1.10", 300), _named("192.168.1.11", 200)]
    stats.top_domains = [_named("example.com", 120)]
    stats.top_blocked_domains = [_named("ads.example.com", 80)]
    return stats


@pytest.fixture
def mock_api(stats_response) -> MagicMock:
    """A mocked technitiumdns AsyncClient with the sub-APIs used by the code."""
    api = MagicMock()
    api.dashboard.stats = AsyncMock(return_value=stats_response)

    update = MagicMock()
    update.update_available = False
    api.user.check_for_update = AsyncMock(return_value=update)

    api.dhcp.leases_list = AsyncMock(return_value=[])

    settings = MagicMock()
    settings.enable_blocking = True
    api.settings.get = AsyncMock(return_value=settings)
    api.settings.set = AsyncMock(return_value=settings)
    api.settings.temporary_disable_blocking = AsyncMock(return_value=settings)
    return api


@pytest.fixture
def config_entry():
    """A configured MockConfigEntry at the current schema version (DHCP off)."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.technitiumdns.config_flow import CONFIG_VERSION
    from custom_components.technitiumdns.const import DOMAIN

    return MockConfigEntry(
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
