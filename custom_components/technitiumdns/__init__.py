"""TechnitiumDNS integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from technitiumdns import InvalidTokenError, TransportError

from .const import (
    DOMAIN,
    DEFAULT_DHCP_LOG_TRACKING,
    DEFAULT_DHCP_STALE_THRESHOLD,
    DEFAULT_DHCP_SMART_ACTIVITY,
    DEFAULT_ACTIVITY_SCORE_THRESHOLD,
    DEFAULT_ACTIVITY_ANALYSIS_WINDOW,
)
from .config_flow import CONFIG_VERSION
from .client import create_api_client
from .const import KEY_BLOCKING_DISABLED_UNTIL
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

async def _async_migrate_unique_ids(hass: HomeAssistant, entry: ConfigEntry):
    """Migrate the unique_ids of existing sensors to the new format, handling duplicates."""
    _LOGGER.info("Starting unique_id migration for TechnitiumDNS sensors.")
    entity_registry = er.async_get(hass)

    entities_to_check = er.async_entries_for_config_entry(entity_registry, entry.entry_id)

    migrated_count = 0
    for entity in entities_to_check:
        # Check if the unique_id matches the OLD format: "Technitiumdns_{type}_{server}"
        if entity.unique_id and entity.unique_id.startswith("Technitiumdns_"):
            try:
                parts = entity.unique_id.split('_', 2)
                if len(parts) != 3:
                    continue

                _, sensor_type, server_name = parts

                # Construct the NEW unique_id that this entity SHOULD have
                new_unique_id = f"{DOMAIN}_dns_stats_{sensor_type}_{server_name.replace(' ', '_').lower()}"

                # --- START OF NEW LOGIC ---
                # Check if another entity (the _2 duplicate) is already using the new unique_id
                conflicting_entity_id = entity_registry.async_get_entity_id(
                    "sensor", DOMAIN, new_unique_id
                )

                if conflicting_entity_id and conflicting_entity_id != entity.entity_id:
                    _LOGGER.warning(
                        "Found conflicting entity %s with the target unique_id. Removing it to resolve duplication.",
                        conflicting_entity_id
                    )
                    entity_registry.async_remove_entity(conflicting_entity_id)
                # --- END OF NEW LOGIC ---

                _LOGGER.debug(
                    "Migrating unique_id for entity %s from '%s' to '%s'",
                    entity.entity_id, entity.unique_id, new_unique_id
                )

                # Now, update the original entity's unique_id
                entity_registry.async_update_entity(
                    entity.entity_id, new_unique_id=new_unique_id
                )
                migrated_count += 1
            except Exception as e:
                _LOGGER.error(
                    "Error migrating unique_id for entity %s: %s", entity.entity_id, e
                )

    if migrated_count > 0:
        _LOGGER.info("Successfully migrated %d sensor unique_ids.", migrated_count)
    else:
        _LOGGER.info("No sensor unique_ids required migration for this entry.")

async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate an old config entry to a new version."""
    _LOGGER.info(
        "Migrating config entry '%s' from version %s to %s",
        config_entry.title,
        config_entry.version,
        CONFIG_VERSION,
    )

    # --- Migration from version 1 to 2 ---
    if config_entry.version == 1:
        # --- 1. Migrate Core Data (add 'check_ssl') ---
        new_data = {**config_entry.data, "check_ssl": True}

        # --- 2. Migrate Options (add all new DHCP keys) ---
        new_options = {**config_entry.options}

        # Add DHCP tracking options with defaults
        new_options.setdefault("enable_dhcp_tracking", False)
        new_options.setdefault("dhcp_update_interval", 60)
        new_options.setdefault("dhcp_ip_filter_mode", "disabled")
        new_options.setdefault("dhcp_ip_ranges", "")

        # Add DNS log tracking options with defaults
        new_options.setdefault("dhcp_log_tracking", DEFAULT_DHCP_LOG_TRACKING)
        new_options.setdefault("dhcp_stale_threshold", DEFAULT_DHCP_STALE_THRESHOLD)

        # Add Smart Activity options with defaults
        new_options.setdefault("dhcp_smart_activity", DEFAULT_DHCP_SMART_ACTIVITY)
        new_options.setdefault("activity_score_threshold", DEFAULT_ACTIVITY_SCORE_THRESHOLD)
        new_options.setdefault("activity_analysis_window", DEFAULT_ACTIVITY_ANALYSIS_WINDOW)

        # Update the config entry with new data, options, and version
        hass.config_entries.async_update_entry(
            config_entry, data=new_data, options=new_options, version=2
        )
        _LOGGER.info("Successfully migrated config entry to version 2.")


    # --- Migration from version 2 to 3 ---
    # This handles users who were on 2.4.0 and need the unique_id fix.
    # It will also run for users who were just migrated from v1.
    if config_entry.version == 2:
        # Only run the unique_id migration
        await _async_migrate_unique_ids(hass, config_entry)

        # Update the version to 3
        hass.config_entries.async_update_entry(config_entry, version=3)
        _LOGGER.info("Successfully migrated config entry to version 3.")

    # --- Migration from version 3 to 4 ---
    if config_entry.version == 3:
        new_data = {**config_entry.data}
        new_data.setdefault("cluster_mode", False)
        hass.config_entries.async_update_entry(
            config_entry, data=new_data, version=4
        )
        _LOGGER.info("Successfully migrated config entry to version 4.")

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TechnitiumDNS from a config entry."""
    if entry.version < CONFIG_VERSION and not await async_migrate_entry(hass, entry):
        _LOGGER.error("Migration failed for config entry %s. Cannot setup integration.", entry.title)
        return False
    _LOGGER.info("Setting up TechnitiumDNS integration for entry %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})

    try:
        api = await create_api_client(
            hass,
            api_url=entry.data["api_url"],
            token=entry.data["token"],
            check_ssl=entry.data.get("check_ssl", True),
            cluster_mode=entry.data.get("cluster_mode", False),
        )
    except InvalidTokenError as err:
        raise ConfigEntryAuthFailed("Invalid Technitium DNS API token") from err
    except TransportError as err:
        raise ConfigEntryNotReady(
            f"Cannot connect to Technitium DNS server: {err}"
        ) from err

    # Determine which platforms to load based on options
    platforms = ["button", "switch"]

    # Add device_tracker if DHCP tracking is enabled (load before sensor)
    dhcp_enabled = entry.options.get("enable_dhcp_tracking", False)
    _LOGGER.info("DHCP tracking enabled: %s", dhcp_enabled)
    if dhcp_enabled:
        platforms.append("device_tracker")
        _LOGGER.info("Added device_tracker platform to load list")


    # Always add sensor platform last so it can access other coordinators
    platforms.append("sensor")

    _LOGGER.debug("Options: %s", entry.options)
    _LOGGER.info("Platforms to load: %s", platforms)


    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "server_name": entry.data["server_name"],
        "stats_duration": entry.data["stats_duration"],
        "loaded_platforms": platforms,
        KEY_BLOCKING_DISABLED_UNTIL: None,
    }

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Technitium",
        name=entry.data["server_name"],
        model="DNS Server",
    )

    # Forward the setup to the appropriate platforms in order
    _LOGGER.info("Starting platform setup for: %s", platforms)

    # Set up all platforms (order is preserved: device_tracker before sensor)
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    _LOGGER.info("All platforms setup completed successfully")

    # Set up options flow listener to handle configuration changes
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # Register cleanup service for manual entity cleanup
    await async_register_services(hass)

    _LOGGER.info("TechnitiumDNS integration setup completed for entry %s", entry.entry_id)
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        # Get the platforms that were actually loaded during setup
        entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
        if platforms := entry_data.get(
            "loaded_platforms", ["button", "switch", "sensor"]
        ):
            await hass.config_entries.async_unload_platforms(entry, platforms)

        hass.data[DOMAIN].pop(entry.entry_id, None)
        return True

    except Exception as e:
        _LOGGER.error("Error unloading TechnitiumDNS integration: %s", e)
        # Still try to clean up data even if platform unload failed
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return True

