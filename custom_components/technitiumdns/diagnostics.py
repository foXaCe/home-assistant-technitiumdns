"""Diagnostics support for the TechnitiumDNS integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

TO_REDACT = {"token", "api_url", "username"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime_data = getattr(entry, "runtime_data", None)
    dhcp_coordinator = (
        runtime_data.coordinators.get("dhcp") if runtime_data else None
    )

    return {
        "entry": {
            "version": entry.version,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "server_name": runtime_data.server_name if runtime_data else None,
        "stats_duration": runtime_data.stats_duration if runtime_data else None,
        "loaded_platforms": runtime_data.loaded_platforms if runtime_data else None,
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
