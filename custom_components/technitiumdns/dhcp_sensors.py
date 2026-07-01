"""DHCP device diagnostic sensors and dynamic sensor manager for TechnitiumDNS."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .utils import (
    manufacturer_from_mac,
    model_from_hostname,
    normalize_mac_address,
    parse_timestamp,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class TechnitiumDHCPSensorDescription(SensorEntityDescription):
    """Describes a TechnitiumDNS DHCP device diagnostic sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]
    icon_fn: Callable[[dict[str, Any]], str] | None = None
    attrs_fn: Callable[[dict[str, Any], Any], dict[str, Any]] | None = None


def _activity_score_icon(data: dict[str, Any]) -> str:
    score = data.get("activity_score", 0)
    if score >= 75:
        return "mdi:account-check"
    if score >= 50:
        return "mdi:account"
    if score >= 25:
        return "mdi:account-outline"
    return "mdi:account-off"


def _activity_score_attrs(data: dict[str, Any], coordinator: Any) -> dict[str, Any]:
    if data.get("activity_score", 0) <= 0:
        return {}
    threshold = "N/A"
    analyzer = getattr(coordinator, "activity_analyzer", None)
    if analyzer is not None:
        threshold = analyzer.score_threshold
    return {
        "activity_summary": data.get("activity_summary", ""),
        "is_actively_used": data.get("is_actively_used", False),
        "score_breakdown": data.get("score_breakdown", {}),
        "threshold": threshold,
    }


DHCP_SENSOR_DESCRIPTIONS: tuple[TechnitiumDHCPSensorDescription, ...] = (
    TechnitiumDHCPSensorDescription(
        key="ip_address",
        translation_key="dhcp_ip_address",
        icon="mdi:ip-network",
        value_fn=lambda data: data.get("ip_address"),
    ),
    TechnitiumDHCPSensorDescription(
        key="mac_address",
        translation_key="dhcp_mac_address",
        icon="mdi:network-outline",
        value_fn=lambda data: data.get("mac_address"),
    ),
    TechnitiumDHCPSensorDescription(
        key="hostname",
        translation_key="dhcp_hostname",
        icon="mdi:dns",
        value_fn=lambda data: data.get("hostname") or "Unknown",
    ),
    TechnitiumDHCPSensorDescription(
        key="lease_obtained",
        translation_key="dhcp_lease_obtained",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-clock",
        value_fn=lambda data: parse_timestamp(data.get("lease_obtained")),
    ),
    TechnitiumDHCPSensorDescription(
        key="lease_expires",
        translation_key="dhcp_lease_expires",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-remove",
        value_fn=lambda data: parse_timestamp(data.get("lease_expires")),
    ),
    TechnitiumDHCPSensorDescription(
        key="last_seen",
        translation_key="dhcp_last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:eye-outline",
        value_fn=lambda data: parse_timestamp(data.get("last_seen")),
    ),
    TechnitiumDHCPSensorDescription(
        key="is_stale",
        translation_key="dhcp_is_stale",
        device_class=SensorDeviceClass.ENUM,
        options=["not_stale", "stale"],
        value_fn=lambda data: "stale" if data.get("is_stale", False) else "not_stale",
        icon_fn=lambda data: (
            "mdi:account-off" if data.get("is_stale", False) else "mdi:account-check"
        ),
    ),
    TechnitiumDHCPSensorDescription(
        key="minutes_since_seen",
        translation_key="dhcp_minutes_since_seen",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="min",
        icon="mdi:timer-outline",
        value_fn=lambda data: data.get("minutes_since_seen", 0),
    ),
    TechnitiumDHCPSensorDescription(
        key="activity_score",
        translation_key="dhcp_activity_score",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="points",
        value_fn=lambda data: data.get("activity_score", 0),
        icon_fn=_activity_score_icon,
        attrs_fn=_activity_score_attrs,
    ),
    TechnitiumDHCPSensorDescription(
        key="is_actively_used",
        translation_key="dhcp_is_actively_used",
        device_class=SensorDeviceClass.ENUM,
        options=["inactive", "active"],
        value_fn=lambda data: (
            "active" if data.get("is_actively_used", False) else "inactive"
        ),
        icon_fn=lambda data: (
            "mdi:account-check"
            if data.get("is_actively_used", False)
            else "mdi:account-off"
        ),
    ),
    TechnitiumDHCPSensorDescription(
        key="activity_summary",
        translation_key="dhcp_activity_summary",
        icon="mdi:text-box-outline",
        value_fn=lambda data: data.get("activity_summary", "No activity data"),
    ),
)


async def _create_device_sensors(leases, dhcp_coordinator, server_name, entry_id):
    """Create diagnostic sensors for a list of device leases."""
    device_sensors: list[TechnitiumDHCPDeviceSensor] = []

    for lease in leases:
        mac_address = lease.get("mac_address", "")
        hostname = lease.get("hostname", "")
        ip_address = lease.get("ip_address", "")

        # Create a device name consistent with the device tracker.
        if hostname:
            device_name = hostname
        elif mac_address:
            device_name = f"Device_{mac_address.replace(':', '')[-6:]}"
        else:
            device_name = f"Unknown_Device_{ip_address}"

        device_sensors.extend(
            TechnitiumDHCPDeviceSensor(
                dhcp_coordinator,
                description,
                mac_address,
                server_name,
                entry_id,
                device_name,
            )
            for description in DHCP_SENSOR_DESCRIPTIONS
        )
        _LOGGER.info(
            "Created %d diagnostic sensors for device %s",
            len(DHCP_SENSOR_DESCRIPTIONS),
            device_name,
        )

    return device_sensors


class TechnitiumDHCPDeviceSensor(CoordinatorEntity, SensorEntity):
    """A single diagnostic sensor for a DHCP device, driven by a description."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    entity_description: TechnitiumDHCPSensorDescription

    def __init__(
        self,
        coordinator,
        description: TechnitiumDHCPSensorDescription,
        mac_address,
        server_name,
        entry_id,
        device_name,
    ):
        """Initialize the diagnostic sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        # Normalize MAC address to match coordinator format (uppercase with colons).
        self._mac_address = normalize_mac_address(mac_address)
        self._server_name = server_name
        self._entry_id = entry_id
        self._device_name = device_name

        mac_clean = self._mac_address.replace(":", "").lower() or "unknown"
        self._attr_unique_id = f"{entry_id}_dhcp_{mac_clean}_{description.key}"

    def _get_device_data(self) -> dict[str, Any] | None:
        """Return this device's lease data from the coordinator, if present."""
        if not self.coordinator.data:
            return None
        for device in self.coordinator.data:
            if device.get("mac_address", "") == self._mac_address:
                return device
        return None

    @property
    def native_value(self) -> StateType:
        """Return the current value from the description's value function."""
        device_data = self._get_device_data()
        if device_data is None:
            return None
        return self.entity_description.value_fn(device_data)

    @property
    def icon(self) -> str | None:
        """Return a dynamic icon when the description provides one."""
        if self.entity_description.icon_fn is not None:
            device_data = self._get_device_data()
            if device_data is not None:
                return self.entity_description.icon_fn(device_data)
        return self.entity_description.icon

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes when the description provides them."""
        if self.entity_description.attrs_fn is None:
            return None
        device_data = self._get_device_data()
        if device_data is None:
            return None
        return self.entity_description.attrs_fn(device_data, self.coordinator)

    @property
    def available(self) -> bool:
        """Sensors stay available while the coordinator refreshes successfully."""
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info matching the device tracker exactly."""
        mac_clean = self._mac_address.replace(":", "").lower()
        device_id = (
            f"{DOMAIN}_dhcp_device_{mac_clean}"
            if self._mac_address
            else f"{DOMAIN}_dhcp_device_unknown"
        )

        device_data = self._get_device_data()
        hostname = device_data.get("hostname", "") if device_data else ""

        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=self._device_name,
            manufacturer=manufacturer_from_mac(self._mac_address),
            model=model_from_hostname(hostname),
            via_device=(DOMAIN, self._entry_id),
        )


class DynamicSensorManager:
    """Manager for creating sensors dynamically when new devices are discovered."""

    def __init__(self, hass, entry, async_add_entities, dhcp_coordinator, server_name):
        """Initialize the dynamic sensor manager."""
        self.hass = hass
        self.entry = entry
        self.async_add_entities = async_add_entities
        self.dhcp_coordinator = dhcp_coordinator
        self.server_name = server_name
        self.known_devices = set()  # Track devices we've already created sensors for
        self._listener = None

        _LOGGER.debug("Dynamic sensor manager initialized for entry %s", entry.entry_id)

    async def setup(self):
        """Set up the dynamic sensor manager."""
        # Track currently known devices using normalized MAC addresses
        if self.dhcp_coordinator.data:
            for lease in self.dhcp_coordinator.data:
                mac_address = lease.get("mac_address", "")
                if mac_address:
                    normalized_mac = normalize_mac_address(mac_address)
                    self.known_devices.add(normalized_mac)
                    _LOGGER.debug("Added known device: %s", normalized_mac)

        # Set up listener for coordinator updates
        if hasattr(self.dhcp_coordinator, "async_add_listener"):

            def _sync_listener():
                _LOGGER.debug("DHCP COORDINATOR: async listener triggered")
                self.hass.async_create_task(self._handle_coordinator_update())

            self._listener = self.dhcp_coordinator.async_add_listener(_sync_listener)
            _LOGGER.debug("Successfully added coordinator listener")
        else:
            _LOGGER.error("DHCP coordinator does not have async_add_listener method!")
            # Fall back to manual triggering
            self._listener = None
        _LOGGER.info(
            "Dynamic sensor manager setup complete, tracking %d known devices",
            len(self.known_devices),
        )

        # If we don't know any devices yet but coordinator has data, treat all as new
        if not self.known_devices and self.dhcp_coordinator.data:
            _LOGGER.info(
                "Dynamic sensor manager: No known devices, treating all %d devices as new",
                len(self.dhcp_coordinator.data),
            )
            await self._handle_coordinator_update()

        # Also force a manual check regardless of listener setup
        if self._listener is None:
            _LOGGER.warning(
                "No coordinator listener available, will rely on manual triggering only"
            )
            # Force an immediate update to create any missing sensors
            await self._handle_coordinator_update()

    async def _handle_coordinator_update(self):
        """Handle coordinator data updates and create sensors for new devices."""
        if not self.dhcp_coordinator.data:
            _LOGGER.debug("Dynamic sensor manager: No coordinator data available")
            return

        current_devices = set()
        new_devices = []

        # Process current devices from coordinator
        for lease in self.dhcp_coordinator.data:
            mac_address = lease.get("mac_address", "")
            if not mac_address:
                continue

            normalized_mac = normalize_mac_address(mac_address)
            current_devices.add(normalized_mac)

            # Check if this is a new device we haven't seen before
            if normalized_mac not in self.known_devices:
                new_devices.append(lease)
                self.known_devices.add(normalized_mac)
                _LOGGER.info(
                    "Dynamic sensor manager: Discovered new device: %s (%s)",
                    normalized_mac,
                    lease.get("hostname", "no hostname"),
                )

        # Track removed devices for logging (entities become unavailable naturally)
        removed_devices = self.known_devices - current_devices
        if removed_devices:
            _LOGGER.info(
                "Dynamic sensor manager: Detected %d removed devices: %s",
                len(removed_devices),
                removed_devices,
            )
            self.known_devices -= removed_devices

        # Update known devices to current state
        self.known_devices = current_devices.copy()

        # Create sensors for new devices
        if new_devices:
            _LOGGER.info(
                "Dynamic sensor manager: Creating sensors for %d new devices",
                len(new_devices),
            )
            await self._create_sensors_for_devices(new_devices)

    async def _create_sensors_for_devices(self, devices):
        """Create diagnostic sensors for a list of new devices."""
        try:
            new_sensors = await _create_device_sensors(
                devices, self.dhcp_coordinator, self.server_name, self.entry.entry_id
            )

            if new_sensors:
                _LOGGER.info(
                    "Dynamic sensor manager: Adding %d new sensors to Home Assistant",
                    len(new_sensors),
                )
                self.async_add_entities(new_sensors, True)
            else:
                _LOGGER.warning(
                    "Dynamic sensor manager: No sensors created for %d devices",
                    len(devices),
                )

        except Exception as e:
            _LOGGER.error(
                "Dynamic sensor manager: Error creating sensors for new devices: %s",
                e,
                exc_info=True,
            )

    def cleanup(self):
        """Clean up the sensor manager."""
        if self._listener:
            self._listener()
            self._listener = None
        _LOGGER.debug("Dynamic sensor manager cleaned up")
