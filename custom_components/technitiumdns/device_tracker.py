"""Support for TechnitiumDNS DHCP device tracking.

This module provides device tracker entities that monitor DHCP lease status.
Diagnostic sensor entities for each tracked device are created by the sensor platform
and are automatically linked to the device through proper device grouping.
"""

import logging

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import (
    CONF_ACTIVITY_ANALYSIS_WINDOW,
    CONF_ACTIVITY_SCORE_THRESHOLD,
    CONF_DHCP_LOG_TRACKING,
    CONF_DHCP_SMART_ACTIVITY,
    CONF_DHCP_STALE_THRESHOLD,
    DEFAULT_ACTIVITY_ANALYSIS_WINDOW,
    DEFAULT_ACTIVITY_SCORE_THRESHOLD,
    DEFAULT_DHCP_LOG_TRACKING,
    DEFAULT_DHCP_SMART_ACTIVITY,
    DEFAULT_DHCP_STALE_THRESHOLD,
    DOMAIN,
)
from .coordinator import TechnitiumDHCPCoordinator
from .utils import (
    manufacturer_from_mac,
    model_from_hostname,
    normalize_mac_address,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up TechnitiumDNS DHCP device trackers."""
    _LOGGER.info(
        "Starting TechnitiumDNS DHCP device tracker setup for entry %s", entry.entry_id
    )

    try:
        config_entry = hass.data[DOMAIN][entry.entry_id]
        api = config_entry["api"]
        server_name = config_entry["server_name"]

        _LOGGER.debug(
            "Retrieved config entry data: api=%s, server_name=%s", api, server_name
        )

        # Get update interval from options, default to 60 seconds
        # (selectors store their choice as a string, so coerce back to int)
        update_interval = int(entry.options.get("dhcp_update_interval", 60))

        # Get IP filtering options
        ip_filter_mode = entry.options.get("dhcp_ip_filter_mode", "disabled")
        ip_ranges = entry.options.get("dhcp_ip_ranges", "")

        # Get DNS log tracking options
        log_tracking = entry.options.get(
            CONF_DHCP_LOG_TRACKING, DEFAULT_DHCP_LOG_TRACKING
        )
        stale_threshold = int(
            entry.options.get(CONF_DHCP_STALE_THRESHOLD, DEFAULT_DHCP_STALE_THRESHOLD)
        )

        # Get smart activity options
        smart_activity = entry.options.get(
            CONF_DHCP_SMART_ACTIVITY, DEFAULT_DHCP_SMART_ACTIVITY
        )
        activity_threshold = int(
            entry.options.get(
                CONF_ACTIVITY_SCORE_THRESHOLD, DEFAULT_ACTIVITY_SCORE_THRESHOLD
            )
        )
        analysis_window = int(
            entry.options.get(
                CONF_ACTIVITY_ANALYSIS_WINDOW, DEFAULT_ACTIVITY_ANALYSIS_WINDOW
            )
        )

        _LOGGER.info(
            "DHCP tracking configuration: interval=%s seconds, filter_mode=%s, ip_ranges=%s, log_tracking=%s, stale_threshold=%s min, smart_activity=%s, activity_threshold=%s, analysis_window=%s min",
            update_interval,
            ip_filter_mode,
            ip_ranges,
            log_tracking,
            stale_threshold,
            smart_activity,
            activity_threshold,
            analysis_window,
        )

        coordinator = TechnitiumDHCPCoordinator(
            hass,
            api,
            update_interval,
            ip_filter_mode,
            ip_ranges,
            log_tracking,
            stale_threshold,
            smart_activity,
            activity_threshold,
            analysis_window,
        )
        _LOGGER.debug("Created TechnitiumDHCPCoordinator: %s", coordinator)

        # Store coordinator in hass.data early so sensor platform can access it
        if "coordinators" not in hass.data[DOMAIN][entry.entry_id]:
            hass.data[DOMAIN][entry.entry_id]["coordinators"] = {}
        hass.data[DOMAIN][entry.entry_id]["coordinators"]["dhcp"] = coordinator
        _LOGGER.debug("Stored DHCP coordinator in hass.data for sensor platform access")

        _LOGGER.info("Performing initial DHCP data refresh...")
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.info("Initial DHCP data refresh completed successfully")

        # Create device trackers only (sensors will be created by sensor platform)
        device_trackers = []
        if coordinator.data:
            _LOGGER.info(
                "Processing %d DHCP leases to create device trackers",
                len(coordinator.data),
            )
            for i, lease in enumerate(coordinator.data):
                _LOGGER.debug("Creating device tracker %d for lease: %s", i + 1, lease)

                # Create device tracker
                device_tracker = TechnitiumDHCPDeviceTracker(
                    coordinator, lease, server_name, entry.entry_id
                )
                device_trackers.append(device_tracker)

            _LOGGER.info("Created %d device trackers", len(device_trackers))
        else:
            _LOGGER.warning(
                "No DHCP lease data available - no device trackers will be created"
            )

        _LOGGER.info(
            "Adding %d device tracker entities to Home Assistant", len(device_trackers)
        )
        async_add_entities(device_trackers, True)

        _LOGGER.info(
            "TechnitiumDNS DHCP device tracker setup completed successfully: %d device trackers",
            len(device_trackers),
        )

    except Exception as e:
        _LOGGER.error(
            "Could not initialize TechnitiumDNS DHCP tracking: %s", e, exc_info=True
        )
        raise ConfigEntryNotReady from e


class TechnitiumDHCPDeviceTracker(CoordinatorEntity, ScannerEntity):
    """Representation of a TechnitiumDNS DHCP device tracker."""

    def __init__(self, coordinator, lease_data, server_name, entry_id):
        """Initialize the device tracker."""
        _LOGGER.debug("Initializing device tracker for lease: %s", lease_data)
        super().__init__(coordinator)
        self._lease_data = lease_data
        self._server_name = server_name
        self._entry_id = entry_id
        self._mac_address = lease_data.get("mac_address", "")
        self._hostname = lease_data.get("hostname", "")

        # Debug MAC address handling
        _LOGGER.debug(
            "Device tracker init: MAC='%s', Hostname='%s'",
            self._mac_address,
            self._hostname,
        )

        # Create a friendly name based on hostname first, then MAC
        if self._hostname and self._hostname.strip():
            self._name = self._hostname.replace(".home.internal", "").replace(
                ".local", ""
            )
        elif self._mac_address:
            self._name = f"Device_{self._mac_address.replace(':', '')[-6:]}"
        else:
            self._name = f"Device_{lease_data.get('ip_address', '').replace('.', '_')}"

        _LOGGER.info(
            "Created device tracker '%s' for MAC %s (IP: %s)",
            self._name,
            self._mac_address,
            lease_data.get("ip_address"),
        )

    @property
    def name(self):
        """Return the name of the device tracker."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID."""
        # Use normalized MAC address for consistent unique_id format
        if self._mac_address:
            normalized_mac = normalize_mac_address(self._mac_address)
            mac_clean = normalized_mac.replace(":", "").lower()
            return f"{self._entry_id}_device_tracker_{mac_clean}"

        # Fallback to IP if no MAC available (shouldn't happen in DHCP context)
        ip_clean = self._lease_data.get("ip_address", "").replace(".", "_")
        return f"{self._entry_id}_device_tracker_ip_{ip_clean}"

    @property
    def source_type(self):
        """Return the source type of the device tracker."""
        return SourceType.ROUTER

    @property
    def is_connected(self):
        """Return if the device is connected."""
        # Check if the device still exists in the current coordinator data
        if not self.coordinator.data:
            _LOGGER.debug(
                "Device %s: no coordinator data available - marking as disconnected",
                self._name,
            )
            return False

        for lease in self.coordinator.data:
            if lease.get("mac_address") == self._mac_address:
                # If smart activity analysis is enabled, use activity-based connection status
                if (
                    self.coordinator.smart_activity_enabled
                    and lease.get("activity_score") is not None
                ):
                    is_actively_used = lease.get("is_actively_used", False)
                    _LOGGER.debug(
                        "Device %s: smart activity analysis - actively_used=%s, score=%.1f - marking as %s",
                        self._name,
                        is_actively_used,
                        lease.get("activity_score", 0),
                        "connected" if is_actively_used else "disconnected",
                    )
                    return is_actively_used
                # If DNS log tracking is enabled but smart activity disabled, consider staleness
                elif lease.get("is_stale") is not None:
                    is_stale = lease.get("is_stale", False)
                    _LOGGER.debug(
                        "Device %s: found lease, is_stale=%s - marking as %s",
                        self._name,
                        is_stale,
                        "disconnected" if is_stale else "connected",
                    )
                    return not is_stale
                else:
                    _LOGGER.debug(
                        "Device %s: found active lease (no activity/staleness check) - marking as connected",
                        self._name,
                    )
                    return True

        _LOGGER.debug(
            "Device %s: no active lease found - marking as disconnected", self._name
        )
        return False

    @property
    def ip_address(self):
        """Return the IP address of the device."""
        if not self.coordinator.data:
            return None

        for lease in self.coordinator.data:
            if lease.get("mac_address") == self._mac_address:
                return lease.get("ip_address")
        return None

    @property
    def mac_address(self):
        """Return the MAC address of the device."""
        return self._mac_address

    @property
    def hostname(self):
        """Return the hostname of the device."""
        if not self.coordinator.data:
            return self._hostname

        for lease in self.coordinator.data:
            if lease.get("mac_address") == self._mac_address:
                return lease.get("hostname", self._hostname)
        return self._hostname

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        attributes = {
            "source": "TechnitiumDNS DHCP",
        }

        # Add minimal lease-specific information
        if self.coordinator.data:
            for lease in self.coordinator.data:
                if lease.get("mac_address") == self._mac_address:
                    attributes.update(
                        {
                            "scope": lease.get("scope", ""),
                            "lease_type": lease.get("type", ""),
                        }
                    )
                    break

        return attributes

    @property
    def device_info(self):
        """Return device information for this entity."""
        # Create proper device registry entry for each DHCP device
        _LOGGER.debug(
            "Device %s: Creating device_info, MAC='%s', has_MAC=%s",
            self._name,
            self._mac_address,
            bool(self._mac_address),
        )

        if self._mac_address and self._mac_address.strip():
            normalized_mac = normalize_mac_address(self._mac_address)
            mac_clean = normalized_mac.replace(":", "").lower()
            device_id = f"{DOMAIN}_dhcp_device_{mac_clean}"
            _LOGGER.debug(
                "Device %s: Using MAC-based device ID: %s (from MAC: %s)",
                self._name,
                device_id,
                self._mac_address,
            )
        else:
            # Fallback to IP-based ID if no MAC
            ip_clean = self._lease_data.get("ip_address", "").replace(".", "_")
            device_id = f"{DOMAIN}_dhcp_device_ip_{ip_clean}"
            _LOGGER.warning(
                "Device %s: No MAC address available (MAC='%s'), using IP-based device ID: %s",
                self._name,
                self._mac_address,
                device_id,
            )

        manufacturer = manufacturer_from_mac(self._mac_address)
        model = model_from_hostname(self._hostname or "")

        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=self._name,
            manufacturer=manufacturer,
            model=model,
            via_device=(
                DOMAIN,
                self._entry_id,
            ),  # Link to the TechnitiumDNS server device
            configuration_url=None,  # Could add device management URL if available
        )

    @property
    def available(self):
        """Return if the device tracker is available."""
        return self.coordinator.last_update_success
