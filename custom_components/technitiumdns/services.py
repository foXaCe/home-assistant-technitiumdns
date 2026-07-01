"""Service handlers for the TechnitiumDNS integration."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import DOMAIN
from .models import async_loaded_runtime_data
from .utils import normalize_mac_address

_LOGGER = logging.getLogger(__name__)


async def async_register_services(hass: HomeAssistant):
    """Register integration services."""
    if hass.services.has_service(DOMAIN, "cleanup_devices"):
        return  # Service already registered

    async def handle_cleanup_devices(call):
        """Handle cleanup_devices service call."""
        config_entry_id = call.data.get("config_entry_id")
        _LOGGER.debug(
            "Cleanup service called with config_entry_id: %s", config_entry_id
        )

        runtime_map = async_loaded_runtime_data(hass)

        if config_entry_id:
            # Clean up specific entry
            _LOGGER.debug("Cleaning up specific entry: %s", config_entry_id)
            entry_runtime = runtime_map.get(config_entry_id)
            if entry_runtime:
                # Get the actual config entry to check if DHCP is enabled
                config_entry = hass.config_entries.async_get_entry(config_entry_id)

                if config_entry:
                    dhcp_enabled = config_entry.options.get(
                        "enable_dhcp_tracking", False
                    )
                    _LOGGER.debug(
                        "Config entry %s DHCP tracking enabled: %s",
                        config_entry_id,
                        dhcp_enabled,
                    )
                    _LOGGER.debug("Config entry options: %s", config_entry.options)

                dhcp_coordinator = entry_runtime.coordinators.get("dhcp")
                _LOGGER.debug(
                    "DHCP coordinator status for %s: coordinator=%s, has_data=%s",
                    config_entry_id,
                    dhcp_coordinator is not None,
                    dhcp_coordinator.data is not None if dhcp_coordinator else False,
                )
                if dhcp_coordinator and dhcp_coordinator.data:
                    # Normalize MAC addresses to uppercase with colons for consistent comparison
                    current_macs = set()
                    for lease in dhcp_coordinator.data:
                        mac = lease.get("mac_address")
                        if mac:
                            normalized_mac = normalize_mac_address(mac)
                            current_macs.add(normalized_mac)
                            _LOGGER.debug(
                                "Normalized MAC %s -> %s", mac, normalized_mac
                            )
                    _LOGGER.debug(
                        "Found %d current MAC addresses for entry %s: %s",
                        len(current_macs),
                        config_entry_id,
                        sorted(current_macs),
                    )
                    await async_cleanup_orphaned_entities(
                        hass, config_entry_id, current_macs
                    )
                    _LOGGER.info(
                        "Manual cleanup completed for entry %s", config_entry_id
                    )
                else:
                    _LOGGER.warning(
                        "No DHCP coordinator found for entry %s (coordinator: %s, data: %s). "
                        "DHCP tracking may not be enabled for this entry.",
                        config_entry_id,
                        dhcp_coordinator is not None,
                        dhcp_coordinator.data if dhcp_coordinator else None,
                    )
                    # Still attempt cleanup with empty MAC set to remove any orphaned entities
                    _LOGGER.info(
                        "Attempting cleanup with empty device set to remove any orphaned DHCP entities"
                    )
                    await async_cleanup_orphaned_entities(hass, config_entry_id, set())
            else:
                _LOGGER.error(
                    "Config entry %s not found. Available entries: %s",
                    config_entry_id,
                    list(runtime_map),
                )
        else:
            # Clean up all entries
            _LOGGER.debug(
                "Cleaning up all entries. Found %d total entries: %s",
                len(runtime_map),
                list(runtime_map),
            )
            cleaned_entries = 0
            for entry_id, entry_runtime in runtime_map.items():
                dhcp_coordinator = entry_runtime.coordinators.get("dhcp")
                _LOGGER.debug(
                    "DHCP coordinator status for %s: coordinator=%s, has_data=%s",
                    entry_id,
                    dhcp_coordinator is not None,
                    dhcp_coordinator.data is not None if dhcp_coordinator else False,
                )
                if dhcp_coordinator and dhcp_coordinator.data:
                    # Normalize MAC addresses to uppercase with colons for consistent comparison
                    current_macs = set()
                    for lease in dhcp_coordinator.data:
                        mac = lease.get("mac_address")
                        if mac:
                            normalized_mac = normalize_mac_address(mac)
                            current_macs.add(normalized_mac)
                            _LOGGER.debug(
                                "Normalized MAC %s -> %s", mac, normalized_mac
                            )
                    _LOGGER.debug(
                        "Found %d current MAC addresses for entry %s: %s",
                        len(current_macs),
                        entry_id,
                        sorted(current_macs),
                    )
                    await async_cleanup_orphaned_entities(hass, entry_id, current_macs)
                    _LOGGER.info("Manual cleanup completed for entry %s", entry_id)
                    cleaned_entries += 1
                else:
                    _LOGGER.debug(
                        "Entry %s has no DHCP coordinator or data (coordinator: %s, data: %s). "
                        "DHCP tracking may not be enabled for this entry.",
                        entry_id,
                        dhcp_coordinator is not None,
                        dhcp_coordinator.data if dhcp_coordinator else None,
                    )
                    # Still attempt cleanup with empty MAC set to remove any orphaned entities
                    _LOGGER.debug(
                        "Attempting cleanup for entry %s with empty device set",
                        entry_id,
                    )
                    await async_cleanup_orphaned_entities(hass, entry_id, set())
                    cleaned_entries += 1
            _LOGGER.debug(
                "Cleanup completed for %d out of %d entries",
                cleaned_entries,
                len(runtime_map),
            )

    async def handle_get_dhcp_leases(call):
        """Handle get_dhcp_leases service call."""
        config_entry_id = call.data.get("config_entry_id")
        include_inactive = call.data.get("include_inactive", False)
        filter_scope = call.data.get("filter_scope")

        _LOGGER.debug(
            "DHCP leases service called with config_entry_id: %s, include_inactive: %s, filter_scope: %s",
            config_entry_id,
            include_inactive,
            filter_scope,
        )

        # Find the appropriate config entry
        runtime_map = async_loaded_runtime_data(hass)
        target_entry_id = config_entry_id
        if not target_entry_id:
            # Use the first available entry if none specified
            _LOGGER.debug(
                "No config_entry_id specified, searching available entries: %s",
                list(runtime_map),
            )
            if runtime_map:
                target_entry_id = next(iter(runtime_map))
                _LOGGER.debug("Using first available entry: %s", target_entry_id)

        if not target_entry_id:
            _LOGGER.error("No TechnitiumDNS config entries found")
            return

        _LOGGER.debug("Using target entry ID: %s", target_entry_id)
        entry_runtime = runtime_map.get(target_entry_id)
        if not entry_runtime:
            _LOGGER.error(
                "Config entry %s not found. Available entries: %s",
                target_entry_id,
                list(runtime_map),
            )
            return

        # Get the API instance
        api = entry_runtime.api
        if not api:
            _LOGGER.error("No API instance found for entry %s", target_entry_id)
            return

        _LOGGER.debug("API instance found, making DHCP leases request")

        try:
            leases_data = await api.dhcp.leases_list()
            _LOGGER.debug(
                "DHCP API response received: leases_count=%d",
                len(leases_data) if leases_data else 0,
            )

            if not leases_data:
                _LOGGER.warning("No DHCP leases data returned from API")
                return

            leases = [
                {
                    "address": lease.address,
                    "hardwareAddress": lease.hardware_address,
                    "hostName": lease.host_name,
                    "clientIdentifier": lease.client_identifier,
                    "addressStatus": lease.address_status,
                    "scope": lease.scope,
                    "type": lease.type,
                    "leaseObtained": (
                        lease.lease_obtained.isoformat()
                        if lease.lease_obtained
                        else None
                    ),
                    "leaseExpires": (
                        lease.lease_expires.isoformat() if lease.lease_expires else None
                    ),
                }
                for lease in leases_data
            ]
            original_count = len(leases)
            _LOGGER.debug("Retrieved %d total leases from API", original_count)

            # Filter leases if requested
            if not include_inactive:
                active_leases = [
                    lease for lease in leases if lease.get("addressStatus") == "InUse"
                ]
                _LOGGER.debug(
                    "Filtered to %d active leases (was %d total)",
                    len(active_leases),
                    len(leases),
                )
                leases = active_leases

            if filter_scope:
                scope_filtered = [
                    lease for lease in leases if lease.get("scope") == filter_scope
                ]
                _LOGGER.debug(
                    "Filtered to %d leases matching scope '%s' (was %d)",
                    len(scope_filtered),
                    filter_scope,
                    len(leases),
                )
                leases = scope_filtered

            _LOGGER.debug("Final lease count after filtering: %d", len(leases))
            if leases:
                _LOGGER.debug(
                    "Sample lease data: %s",
                    {
                        k: v
                        for k, v in leases[0].items()
                        if k in ["address", "hostName", "addressStatus", "scope"]
                    },
                )

            # Fire event with the lease data
            event_data = {
                "config_entry_id": target_entry_id,
                "total_leases": len(leases),
                "leases": leases,
                "include_inactive": include_inactive,
                "filter_scope": filter_scope,
            }
            _LOGGER.debug(
                "Firing event %s_dhcp_leases_retrieved with %d leases",
                DOMAIN,
                len(leases),
            )
            hass.bus.async_fire(f"{DOMAIN}_dhcp_leases_retrieved", event_data)

            _LOGGER.info(
                "Retrieved %d DHCP leases for entry %s (include_inactive=%s, filter_scope=%s)",
                len(leases),
                target_entry_id,
                include_inactive,
                filter_scope,
            )

        except Exception as e:
            _LOGGER.error("Failed to retrieve DHCP leases: %s", e)
            _LOGGER.debug("DHCP leases retrieval exception details", exc_info=True)

    hass.services.async_register(
        DOMAIN,
        "cleanup_devices",
        handle_cleanup_devices,
        schema=vol.Schema(
            {
                vol.Optional("config_entry_id"): cv.string,
            }
        ),
    )
    _LOGGER.info("Registered cleanup_devices service")

    hass.services.async_register(
        DOMAIN,
        "get_dhcp_leases",
        handle_get_dhcp_leases,
        schema=vol.Schema(
            {
                vol.Optional("config_entry_id"): cv.string,
                vol.Optional("include_inactive", default=False): cv.boolean,
                vol.Optional("filter_scope"): cv.string,
            }
        ),
    )
    _LOGGER.info("Registered get_dhcp_leases service")


async def async_cleanup_orphaned_entities(
    hass: HomeAssistant, entry_id: str, current_devices: set
):
    """Log information about devices that should be cleaned up.

    Note: Instead of manually manipulating entity registry (which can cause issues),
    we now rely on the coordinator update pattern to naturally handle entity lifecycle.
    Device entities will become unavailable when their data is no longer in the coordinator,
    and can be manually removed by the user if needed.

    Args:
        hass: Home Assistant instance
        entry_id: Config entry ID
        current_devices: Set of MAC addresses for devices that should exist
    """
    _LOGGER.info("Checking for orphaned entities for entry %s", entry_id)
    _LOGGER.debug(
        "Current devices that should exist: %s (%d total)",
        sorted(current_devices),
        len(current_devices),
    )

    entity_registry = er.async_get(hass)

    # Find all DHCP entities belonging to this integration
    dhcp_entities = []
    total_entities_checked = 0

    for entity_id, entity in entity_registry.entities.items():
        if entity.config_entry_id == entry_id:
            total_entities_checked += 1

            # Check if this is a DHCP device entity using the new standardized unique_id patterns
            unique_id_str = str(entity.unique_id)
            if (
                "_dhcp_device_" in unique_id_str
                or "_dhcp_sensor_" in unique_id_str
                or "_device_tracker_" in unique_id_str
            ):
                dhcp_entities.append((entity_id, entity))

    _LOGGER.debug(
        "Found %d DHCP entities out of %d total entities for this integration",
        len(dhcp_entities),
        total_entities_checked,
    )

    # Analyze which devices should be orphaned
    orphaned_entities = []
    current_entities = []

    for entity_id, entity in dhcp_entities:
        mac_from_entity = None
        unique_id_str = str(entity.unique_id)

        # Extract MAC from standardized unique_id patterns
        if "_dhcp_device_" in unique_id_str:
            # Format: {DOMAIN}_dhcp_device_{mac_clean}
            parts = unique_id_str.split("_dhcp_device_")
            if len(parts) > 1:
                mac_clean = parts[1]
                # Convert MAC back to normalized format
                if len(mac_clean) == 12:
                    mac_formatted = ":".join(
                        [mac_clean[i : i + 2] for i in range(0, 12, 2)]
                    ).upper()
                    mac_from_entity = normalize_mac_address(mac_formatted)

        elif "_dhcp_sensor_" in unique_id_str:
            # Format: {DOMAIN}_dhcp_sensor_{mac_clean}_{sensor_type}
            parts = unique_id_str.split("_dhcp_sensor_")
            if len(parts) > 1:
                mac_clean = parts[1].split("_")[0]  # Get MAC part before sensor type
                if len(mac_clean) == 12:
                    mac_formatted = ":".join(
                        [mac_clean[i : i + 2] for i in range(0, 12, 2)]
                    ).upper()
                    mac_from_entity = normalize_mac_address(mac_formatted)

        elif "_device_tracker_" in unique_id_str:
            # Format: {DOMAIN}_device_tracker_{mac_clean}
            parts = unique_id_str.split("_device_tracker_")
            if len(parts) > 1:
                mac_clean = parts[1]
                if len(mac_clean) == 12:
                    mac_formatted = ":".join(
                        [mac_clean[i : i + 2] for i in range(0, 12, 2)]
                    ).upper()
                    mac_from_entity = normalize_mac_address(mac_formatted)

        # Check if this entity should still exist
        if mac_from_entity:
            if mac_from_entity not in current_devices:
                orphaned_entities.append((entity_id, mac_from_entity, entity.platform))
            else:
                current_entities.append((entity_id, mac_from_entity, entity.platform))

    # Log information about orphaned entities (but don't remove them)
    if orphaned_entities:
        _LOGGER.info(
            "Found %d orphaned DHCP entities (devices no longer in coordinator data):",
            len(orphaned_entities),
        )
        for entity_id, mac, platform in orphaned_entities:
            _LOGGER.info(
                "  - %s (%s, MAC: %s) - will become unavailable automatically",
                entity_id,
                platform,
                mac,
            )
        _LOGGER.info(
            "These entities will become 'unavailable' automatically when coordinator updates."
        )
        _LOGGER.info(
            "If you want to remove them permanently, you can do so manually from the HA UI."
        )
    else:
        _LOGGER.info(
            "No orphaned DHCP entities found - all entities match current coordinator data"
        )

    if current_entities:
        _LOGGER.debug(
            "Found %d current DHCP entities that should remain:", len(current_entities)
        )
        for entity_id, mac, platform in current_entities:
            _LOGGER.debug("  - %s (%s, MAC: %s)", entity_id, platform, mac)

    _LOGGER.info(
        "Entity cleanup analysis completed - relying on coordinator pattern for entity lifecycle management"
    )
