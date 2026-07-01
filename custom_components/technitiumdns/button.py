"""TechnitiumDNS button entities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonEntity

from .const import AD_BLOCKING_DURATION_OPTIONS, DOMAIN
from .utils import server_device_info

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity import DeviceInfo
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .models import TechnitiumConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TechnitiumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TechnitiumDNS button entities based on a config entry."""
    runtime_data = entry.runtime_data
    api = runtime_data.api
    server_name = runtime_data.server_name

    sorted_durations = sorted(AD_BLOCKING_DURATION_OPTIONS.keys())

    buttons: list[TechnitiumDNSButton | TechnitiumDNSCleanupButton] = [
        TechnitiumDNSButton(api, duration, server_name, entry)
        for duration in sorted_durations
    ]

    dhcp_enabled = entry.options.get("enable_dhcp_tracking", False)
    if dhcp_enabled:
        buttons.append(TechnitiumDNSCleanupButton(server_name, entry))

    async_add_entities(buttons)


class TechnitiumDNSButton(ButtonEntity):
    """Representation of a TechnitiumDNS button."""

    _attr_has_entity_name = True

    def __init__(
        self,
        api: Any,
        duration: int,
        server_name: str,
        entry: TechnitiumConfigEntry,
    ) -> None:
        """Initialize the button."""
        self._api = api
        self._entry = entry
        self._server_name = server_name
        self._duration = duration
        self._attr_translation_key = f"disable_blocking_{duration}"
        self._attr_unique_id = f"{entry.entry_id}_disable_blocking_{duration}"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            result = await self._api.settings.temporary_disable_blocking(
                minutes=self._duration
            )
            until = result.temporary_disable_blocking_till
            self._entry.runtime_data.blocking_disabled_until = until

            _LOGGER.info(
                "Ad blocking disabled for %d minutes on %s (until %s)",
                self._duration,
                self._server_name,
                until,
            )

            self.hass.bus.async_fire(
                f"{DOMAIN}_blocking_changed",
                {"config_entry_id": self._entry.entry_id},
            )
        except Exception as err:
            _LOGGER.error("Failed to disable ad blocking: %s", err)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this entity."""
        return server_device_info(self._entry.entry_id, self._server_name)


class TechnitiumDNSCleanupButton(ButtonEntity):
    """Button to cleanup orphaned DHCP device entities."""

    _attr_has_entity_name = True

    def __init__(self, server_name: str, entry: TechnitiumConfigEntry) -> None:
        """Initialize the cleanup button."""
        self._server_name = server_name
        self._entry = entry
        self._attr_translation_key = "cleanup_devices"
        self._attr_unique_id = f"{entry.entry_id}_cleanup_devices"
        self._attr_icon = "mdi:delete-sweep"

    async def async_press(self) -> None:
        """Handle the button press to cleanup orphaned entities."""
        try:
            await self.hass.services.async_call(
                DOMAIN,
                "cleanup_devices",
                {"config_entry_id": self._entry.entry_id},
            )
            _LOGGER.info("Manual device cleanup triggered for %s", self._server_name)
        except Exception as err:
            _LOGGER.error("Failed to trigger device cleanup: %s", err)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this entity."""
        return server_device_info(self._entry.entry_id, self._server_name)
