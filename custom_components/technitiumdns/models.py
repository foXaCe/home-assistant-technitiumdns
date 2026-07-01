"""Typed runtime data for the TechnitiumDNS integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState

from .const import DOMAIN

if TYPE_CHECKING:
    # The technitiumdns-api client library has the same top-level name as this
    # custom component; mypy's flat module resolution (no `custom_components`
    # package marker) resolves the bare "technitiumdns" name to this
    # integration instead of the installed library, hence the attr-defined
    # false positive.
    from datetime import datetime

    from homeassistant.core import HomeAssistant

    from technitiumdns import AsyncClient  # type: ignore[attr-defined]


@dataclass
class TechnitiumRuntimeData:
    """Data attached to a config entry via ``entry.runtime_data``."""

    api: AsyncClient
    server_name: str
    stats_duration: str
    loaded_platforms: list[str]
    coordinators: dict[str, Any] = field(default_factory=dict)
    sensor_manager: Any = None
    blocking_disabled_until: datetime | str | None = None


type TechnitiumConfigEntry = ConfigEntry[TechnitiumRuntimeData]


def async_loaded_runtime_data(
    hass: HomeAssistant,
) -> dict[str, TechnitiumRuntimeData]:
    """Return a mapping of entry_id -> runtime data for loaded entries."""
    return {
        entry.entry_id: entry.runtime_data
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and isinstance(entry.runtime_data, TechnitiumRuntimeData)
    }
