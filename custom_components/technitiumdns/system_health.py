"""Provide info to the system health page for TechnitiumDNS."""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return info for the system health page."""
    entries = hass.config_entries.async_entries(DOMAIN)
    info: dict[str, Any] = {"configured_servers": len(entries)}

    # Prefer a loaded entry, otherwise fall back to the first configured one.
    entry = next(
        (e for e in entries if e.state is ConfigEntryState.LOADED),
        entries[0] if entries else None,
    )
    if entry is not None and (api_url := entry.data.get("api_url")):
        info["can_reach_server"] = system_health.async_check_can_reach_url(
            hass, api_url
        )

    return info
