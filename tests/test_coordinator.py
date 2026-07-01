"""Tests for the TechnitiumDNS data update coordinators."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant

from custom_components.technitiumdns.coordinator import TechnitiumDNSCoordinator


async def test_stats_update_success(hass: HomeAssistant, mock_api) -> None:
    """A successful refresh exposes the parsed statistics."""
    coordinator = TechnitiumDNSCoordinator(
        hass, mock_api, "last_hour", update_interval=60
    )

    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data["queries"] == 1000
    assert coordinator.data["blocked_queries"] == 150
    assert coordinator.data["clients"] == 12
    assert coordinator.data["update_available"] is False
    assert coordinator.data["top_clients"][0] == {"name": "192.168.1.10", "hits": 300}


async def test_stats_maps_duration_to_api_value(hass: HomeAssistant, mock_api) -> None:
    """The lowercase selector value is mapped to the Technitium API value."""
    coordinator = TechnitiumDNSCoordinator(hass, mock_api, "last_day")

    await coordinator.async_refresh()

    mock_api.dashboard.stats.assert_awaited_once()
    assert mock_api.dashboard.stats.await_args.kwargs["type"] == "LastDay"


async def test_stats_update_failure(hass: HomeAssistant, mock_api) -> None:
    """Any API error marks the coordinator as failed (UpdateFailed)."""
    mock_api.dashboard.stats = AsyncMock(side_effect=Exception("boom"))
    coordinator = TechnitiumDNSCoordinator(hass, mock_api, "last_hour")

    await coordinator.async_refresh()

    assert coordinator.last_update_success is False


async def test_update_check_cached(hass: HomeAssistant, mock_api) -> None:
    """The update check is cached and not repeated on every refresh."""
    coordinator = TechnitiumDNSCoordinator(hass, mock_api, "last_hour")

    await coordinator.async_refresh()
    await coordinator.async_refresh()

    # stats fetched twice, but the (hourly) update check only once
    assert mock_api.dashboard.stats.await_count == 2
    assert mock_api.user.check_for_update.await_count == 1
