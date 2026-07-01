"""Diagnostics support for the TechnitiumDNS integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {"token", "api_url", "username"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    dhcp_coordinator = entry_data.get("coordinators", {}).get("dhcp")

    return {
        "entry": {
            "version": entry.version,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "server_name": entry_data.get("server_name"),
        "stats_duration": entry_data.get("stats_duration"),
        "loaded_platforms": entry_data.get("loaded_platforms"),
        "dhcp": {
            "enabled": dhcp_coordinator is not None,
            "last_update_success": (
                dhcp_coordinator.last_update_success if dhcp_coordinator else None
            ),
            "device_count": (
                len(dhcp_coordinator.data)
                if dhcp_coordinator and dhcp_coordinator.data
                else 0
            ),
        },
    }
