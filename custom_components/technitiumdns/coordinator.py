"""Data update coordinators for the TechnitiumDNS integration."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any, cast

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from technitiumdns import TransportError

from .activity_analyzer import SmartActivityAnalyzer, analyze_batch_device_activity
from .const import DEFAULT_UPDATE_INFO, DOMAIN, STATS_DURATION_API
from .dns_logs import (
    get_dns_logs_for_analysis,
    get_last_seen_for_multiple_ips,
    test_dns_logs_api,
)
from .models import async_loaded_runtime_data
from .services import async_cleanup_orphaned_entities
from .utils import normalize_mac_address, should_track_ip

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

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
                except (TimeoutError, TransportError) as update_err:
                    _LOGGER.warning(
                        "Failed to check for updates: %s, using cached data",
                        update_err,
                    )
            else:
                _LOGGER.debug("Using cached update info")

            if update_result is None:
                default_response = cast(
                    "dict[str, Any]", DEFAULT_UPDATE_INFO["response"]
                )
                update_available = default_response["updateAvailable"]
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


class TechnitiumDHCPCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Class to manage fetching TechnitiumDNS DHCP data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: Any,
        update_interval: int,
        ip_filter_mode: str = "disabled",
        ip_ranges: str = "",
        log_tracking: bool = False,
        stale_threshold: int = 60,
        smart_activity: bool = True,
        activity_threshold: int = 25,
        analysis_window: int = 30,
    ) -> None:
        """Initialize."""
        _LOGGER.info(
            "Initializing TechnitiumDHCPCoordinator with interval=%s, filter_mode=%s, log_tracking=%s, stale_threshold=%s, smart_activity=%s, activity_threshold=%s, analysis_window=%s",
            update_interval,
            ip_filter_mode,
            log_tracking,
            stale_threshold,
            smart_activity,
            activity_threshold,
            analysis_window,
        )
        self.api = api
        self.ip_filter_mode = ip_filter_mode
        self.ip_ranges = ip_ranges
        self.log_tracking = log_tracking
        self.stale_threshold_minutes = stale_threshold
        self.smart_activity_enabled = smart_activity
        self.activity_analyzer = (
            SmartActivityAnalyzer(activity_threshold, analysis_window)
            if smart_activity
            else None
        )
        scan_interval = timedelta(seconds=update_interval)
        _LOGGER.debug("Setting coordinator update interval to %s", scan_interval)
        super().__init__(
            hass, _LOGGER, name=f"{DOMAIN}_dhcp", update_interval=scan_interval
        )
        _LOGGER.info("TechnitiumDHCPCoordinator initialized successfully")

    async def _cleanup_orphaned_entities(self, current_macs: set[str]) -> None:
        """Clean up entities for devices that no longer match current criteria."""
        try:
            # Find the config entry that owns this coordinator
            entry_id = None
            for eid, runtime_data in async_loaded_runtime_data(self.hass).items():
                if runtime_data.coordinators.get("dhcp") is self:
                    entry_id = eid
                    break

            if entry_id:
                await async_cleanup_orphaned_entities(self.hass, entry_id, current_macs)
            else:
                _LOGGER.warning("Could not find config entry ID for entity cleanup")
        except Exception as e:
            _LOGGER.error("Error during entity cleanup: %s", e, exc_info=True)

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Update data via library."""
        _LOGGER.info("Starting DHCP data update cycle")
        try:
            _LOGGER.debug("Fetching DHCP leases from TechnitiumDNS API")
            leases = await self.api.dhcp.leases_list()

            _LOGGER.info("Retrieved %d total DHCP leases from API", len(leases))

            # Log summary of lease types found
            if leases:
                types_found = set()
                for lease in leases:
                    lease_type = lease.get("type")
                    if lease_type:
                        types_found.add(lease_type)
                _LOGGER.info("Lease types found: %s", sorted(types_found))

            # Process and clean up lease data
            processed_leases = []
            filtered_count = 0
            skipped_count = 0

            for i, lease in enumerate(leases):
                lease_type = lease.type
                ip_address = lease.address
                mac_address = lease.hardware_address or ""
                _LOGGER.debug(
                    "Processing lease %d: type=%s, address=%s, mac=%s",
                    i + 1,
                    lease_type,
                    ip_address,
                    mac_address,
                )

                # Filter leases based on the official Technitium DNS API specification
                should_include = False
                skip_reason = ""

                # Check if we have basic required data
                if not ip_address:
                    skip_reason = "no IP address"
                elif not mac_address:
                    skip_reason = "no MAC address"
                else:
                    # Accept lease types according to Technitium DNS API docs
                    if (
                        lease_type == "Dynamic"
                        or lease_type == "Reserved"
                        or not lease_type
                    ):
                        should_include = True
                        # _LOGGER.debug("Including lease with empty type (assuming dynamic)")
                    else:
                        # Log but still include unknown lease types to be flexible
                        should_include = True
                        # _LOGGER.debug("Including lease with unknown type '%s'", lease_type)

                if should_include:
                    # Apply IP filtering
                    if not should_track_ip(
                        ip_address, self.ip_filter_mode, self.ip_ranges
                    ):
                        filtered_count += 1
                        # _LOGGER.debug("Filtering out IP %s based on filter mode %s", ip_address, self.ip_filter_mode)
                        continue

                    processed_lease = {
                        "ip_address": ip_address,
                        "mac_address": normalize_mac_address(mac_address),
                        "hostname": lease.host_name or "",
                        "client_id": lease.client_identifier or "",
                        "lease_expires": (
                            lease.lease_expires.isoformat()
                            if lease.lease_expires
                            else None
                        ),
                        "lease_obtained": (
                            lease.lease_obtained.isoformat()
                            if lease.lease_obtained
                            else None
                        ),
                        "scope": lease.scope or "",
                        "type": lease_type,
                        "last_seen": None,  # Will be populated by DNS log query
                        "is_stale": False,  # Will be calculated based on last_seen or activity score
                        "minutes_since_seen": 0,  # Minutes since last DNS activity
                        "activity_score": 0,  # Smart activity score (0-100)
                        "is_actively_used": False,  # Whether device is genuinely being used
                        "activity_summary": "",  # Human-readable activity summary
                    }
                    processed_leases.append(processed_lease)
                    _LOGGER.debug(
                        "Added lease for tracking: IP=%s, MAC=%s, hostname=%s, type=%s",
                        ip_address,
                        processed_lease["mac_address"],
                        processed_lease["hostname"],
                        lease_type,
                    )
                else:
                    _LOGGER.debug("Skipping lease: %s", skip_reason)
                    skipped_count += 1

            # Query DNS logs for last seen times if enabled
            processed_leases = await self._get_last_seen_for_devices(processed_leases)

            # Log stale device summary if log tracking is enabled
            if self.log_tracking:
                stale_count = sum(
                    1 for lease in processed_leases if lease.get("is_stale", False)
                )
                _LOGGER.info(
                    "DNS activity summary: %d devices total, %d are stale (>%d min since last seen)",
                    len(processed_leases),
                    stale_count,
                    self.stale_threshold_minutes,
                )

            _LOGGER.info(
                "DHCP data processing complete: %d active leases, %d filtered, %d skipped",
                len(processed_leases),
                filtered_count,
                skipped_count,
            )

            if filtered_count > 0:
                _LOGGER.info(
                    "Filtered out %d devices based on IP filter settings",
                    filtered_count,
                )

            _LOGGER.debug("Final processed DHCP leases: %s", processed_leases)
            _LOGGER.info(
                "DHCP update cycle completed successfully with %d trackable devices",
                len(processed_leases),
            )

            # Track current devices for cleanup purposes - normalize MAC addresses
            current_macs = set()
            for lease in processed_leases:
                mac = lease.get("mac_address")
                if mac:
                    normalized_mac = normalize_mac_address(mac)
                    current_macs.add(normalized_mac)
                    # _LOGGER.debug("Device tracker normalized MAC %s -> %s", mac, normalized_mac)
            _LOGGER.debug(
                "Device tracker collected %d normalized MAC addresses: %s",
                len(current_macs),
                sorted(current_macs),
            )
            await self._cleanup_orphaned_entities(current_macs)

            return processed_leases

        except Exception as err:
            _LOGGER.error("Error fetching DHCP data: %s", err, exc_info=True)
            raise UpdateFailed(f"Error fetching DHCP data: {err}") from err

    async def _get_last_seen_for_devices(
        self, processed_leases: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Query DNS logs to get last seen times and activity analysis for devices."""
        if not self.log_tracking:
            _LOGGER.debug("DNS log tracking disabled, skipping last seen queries")
            return processed_leases

        # Extract all IP addresses for batch query
        ip_addresses = []
        ip_to_lease_map = {}

        for lease in processed_leases:
            ip_address = lease.get("ip_address")
            if ip_address:
                ip_addresses.append(ip_address)
                # Map IP to lease for easier lookup
                ip_to_lease_map[ip_address] = lease

        if not ip_addresses:
            _LOGGER.debug("No IP addresses to query for DNS logs")
            return processed_leases

        _LOGGER.info("Performing batch DNS log query for %d devices", len(ip_addresses))

        try:
            # First, test if DNS logs API is working at all
            api_test = await test_dns_logs_api(self.api)
            _LOGGER.debug("DNS logs API test result: %s", api_test)

            if not api_test.get("available"):
                _LOGGER.warning(
                    "DNS logs API is not available: %s", api_test.get("message")
                )
                _LOGGER.warning("Disabling DNS log tracking for this update cycle")
                # Return early, leaving all devices with default values
                return processed_leases

            # Get DNS logs for smart activity analysis
            if self.smart_activity_enabled and self.activity_analyzer:
                _LOGGER.info(
                    "Performing smart activity analysis for %d devices",
                    len(ip_addresses),
                )

                # Get comprehensive DNS logs for activity analysis
                # Use a longer window to capture more activity (at least 4 hours)
                analysis_window_hours = max(
                    4, self.activity_analyzer.analysis_window_minutes / 60
                )
                dns_logs = await get_dns_logs_for_analysis(
                    self.api, hours_back=analysis_window_hours
                )

                if dns_logs:
                    # Perform batch activity analysis
                    activity_results = analyze_batch_device_activity(
                        dns_logs, ip_addresses, self.activity_analyzer
                    )

                    # Update leases with activity analysis
                    for ip_address, lease in ip_to_lease_map.items():
                        activity_data = activity_results.get(ip_address, {})

                        lease["activity_score"] = activity_data.get("activity_score", 0)
                        lease["is_actively_used"] = activity_data.get(
                            "is_actively_used", False
                        )
                        lease["activity_summary"] = activity_data.get(
                            "analysis_summary", "No analysis"
                        )

                        # Use smart activity for staleness determination
                        lease["is_stale"] = not activity_data.get(
                            "is_actively_used", False
                        )

                        _LOGGER.debug(
                            "Device %s: activity_score=%.1f, actively_used=%s, summary='%s'",
                            ip_address,
                            lease["activity_score"],
                            lease["is_actively_used"],
                            lease["activity_summary"],
                        )

                    _LOGGER.info(
                        "Smart activity analysis completed for %d devices",
                        len(ip_addresses),
                    )
                else:
                    _LOGGER.warning("No DNS logs available for smart activity analysis")
                    # Fall back to basic last seen tracking
                    await self._perform_basic_last_seen_tracking(
                        ip_addresses, ip_to_lease_map
                    )
            else:
                # Perform basic last seen tracking without smart activity
                await self._perform_basic_last_seen_tracking(
                    ip_addresses, ip_to_lease_map
                )

        except Exception as e:
            _LOGGER.error("Error in DNS log processing: %s", e, exc_info=True)
            # Fall back to marking all devices based on DHCP presence only
            for lease in processed_leases:
                lease["last_seen"] = None
                lease["is_stale"] = False
                lease["minutes_since_seen"] = 0
                lease["activity_score"] = 50  # Neutral score
                lease["is_actively_used"] = True  # Assume active if DHCP lease exists
                lease["activity_summary"] = "DHCP lease active (DNS analysis failed)"

        # Log summary statistics
        if self.smart_activity_enabled:
            active_count = sum(
                1 for lease in processed_leases if lease.get("is_actively_used", False)
            )
            avg_score = (
                sum(lease.get("activity_score", 0) for lease in processed_leases)
                / len(processed_leases)
                if processed_leases
                else 0
            )
            _LOGGER.info(
                "Activity analysis summary: %d/%d devices actively used, average score: %.1f",
                active_count,
                len(processed_leases),
                avg_score,
            )

        return processed_leases

    async def _perform_basic_last_seen_tracking(
        self, ip_addresses: list[str], ip_to_lease_map: dict[str, dict[str, Any]]
    ) -> None:
        """Perform basic last seen tracking without smart activity analysis."""
        _LOGGER.info(
            "Performing basic last seen tracking for %d devices", len(ip_addresses)
        )

        # Single batch call to get last seen times for all devices
        # Start with a shorter time window (6 hours) for better performance
        last_seen_times = await get_last_seen_for_multiple_ips(
            self.api, ip_addresses, hours_back=6
        )

        # Update all leases with the results
        for ip_address, lease in ip_to_lease_map.items():
            last_seen = last_seen_times.get(ip_address)

            if last_seen:
                lease["last_seen"] = last_seen
                _LOGGER.debug("Device %s last seen at %s", ip_address, last_seen)

                # Calculate if device is stale based on time threshold
                try:
                    last_seen_dt = datetime.fromisoformat(
                        last_seen.replace("Z", "+00:00")
                    )
                    now = datetime.now(last_seen_dt.tzinfo)
                    minutes_since_seen = (now - last_seen_dt).total_seconds() / 60
                    lease["is_stale"] = (
                        minutes_since_seen > self.stale_threshold_minutes
                    )
                    lease["minutes_since_seen"] = int(minutes_since_seen)
                    lease["activity_score"] = (
                        100 if not lease["is_stale"] else 0
                    )  # Binary score
                    lease["is_actively_used"] = not lease["is_stale"]
                    lease["activity_summary"] = (
                        f"Last seen {int(minutes_since_seen)} minutes ago"
                    )
                    _LOGGER.debug(
                        "Device %s: %d minutes since last seen, stale=%s",
                        ip_address,
                        int(minutes_since_seen),
                        lease["is_stale"],
                    )
                except Exception as e:
                    _LOGGER.debug(
                        "Error parsing last seen time for %s: %s", ip_address, e
                    )
                    lease["is_stale"] = False
                    lease["minutes_since_seen"] = 0
                    lease["activity_score"] = 50
                    lease["is_actively_used"] = True
                    lease["activity_summary"] = "Recent DHCP activity"
            else:
                _LOGGER.debug("No DNS log entries found for device %s", ip_address)
                lease["last_seen"] = None
                lease["is_stale"] = True  # No DNS activity = stale
                lease["minutes_since_seen"] = 9999
                lease["activity_score"] = 0
                lease["is_actively_used"] = False
                lease["activity_summary"] = "No recent DNS activity"
