"""Data update coordinators for the TechnitiumDNS integration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from technitiumdns import TransportError

from .const import DEFAULT_UPDATE_INFO, DOMAIN, STATS_DURATION_API

_LOGGER = logging.getLogger(__name__)

UPDATE_CHECK_INTERVAL = timedelta(hours=1)


class TechnitiumDNSCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator fetching dashboard statistics from a Technitium DNS server."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: Any,
        stats_duration: str,
        update_interval: int = 60,
    ) -> None:
        """Initialize the statistics coordinator."""
        self.api = api
        self.stats_duration = stats_duration
        self._last_update_check: datetime | None = None
        self._cached_update_info: Any | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch statistics (and, hourly, update availability) from the server."""
        try:
            _LOGGER.debug("Fetching data from TechnitiumDNS API")
            stats = await self.api.dashboard.stats(
                type=STATS_DURATION_API.get(self.stats_duration, self.stats_duration),
                utc=True,
            )

            current_time = dt_util.utcnow()
            should_check_updates = (
                self._last_update_check is None
                or current_time - self._last_update_check >= UPDATE_CHECK_INTERVAL
            )

            update_result = self._cached_update_info
            if should_check_updates:
                _LOGGER.debug("Checking for updates (hourly check)")
                try:
                    update_result = await self.api.user.check_for_update()
                    self._cached_update_info = update_result
                    self._last_update_check = current_time
                    _LOGGER.debug("Update check completed, cached for next hour")
                except (TransportError, asyncio.TimeoutError) as update_err:
                    _LOGGER.warning(
                        "Failed to check for updates: %s, using cached data",
                        update_err,
                    )
            else:
                _LOGGER.debug("Using cached update info")

            if update_result is None:
                update_available = DEFAULT_UPDATE_INFO["response"]["updateAvailable"]
            else:
                update_available = update_result.update_available

            counters = stats.stats
            data: dict[str, Any] = {
                "queries": counters.total_queries,
                "blocked_queries": counters.total_blocked,
                "clients": counters.total_clients,
                "update_available": update_available,
                "no_error": counters.total_no_error,
                "server_failure": counters.total_server_failure,
                "nx_domain": counters.total_nx_domain,
                "refused": counters.total_refused,
                "authoritative": counters.total_authoritative,
                "recursive": counters.total_recursive,
                "cached": counters.total_cached,
                "dropped": counters.total_dropped,
                "zones": counters.zones,
                "cached_entries": counters.cached_entries,
                "allowed_zones": counters.allowed_zones,
                "blocked_zones": counters.blocked_zones,
                "allow_list_zones": counters.allow_list_zones,
                "block_list_zones": counters.block_list_zones,
                "top_clients": [
                    {"name": client.name or "Unknown", "hits": client.hits}
                    for client in stats.top_clients[:5]
                ],
                "top_domains": [
                    {"name": domain.name or "Unknown", "hits": domain.hits}
                    for domain in stats.top_domains[:5]
                ],
                "top_blocked_domains": [
                    {"name": domain.name or "Unknown", "hits": domain.hits}
                    for domain in stats.top_blocked_domains[:5]
                ],
            }
            _LOGGER.debug("Data combined: %s", data)
            return data
        except Exception as err:
            _LOGGER.error("Error fetching data: %s", err)
            raise UpdateFailed(f"Error fetching data: {err}") from err
