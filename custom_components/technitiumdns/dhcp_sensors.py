"""DHCP device diagnostic sensors and dynamic sensor manager for TechnitiumDNS."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import (
    DOMAIN,
)
from .utils import (
    manufacturer_from_mac,
    model_from_hostname,
    normalize_mac_address,
    parse_timestamp,
)

_LOGGER = logging.getLogger(__name__)


async def _create_device_sensors(leases, dhcp_coordinator, server_name, entry_id):
    """Create diagnostic sensors for a list of device leases."""
    device_sensors = []

    for lease in leases:
        mac_address = lease.get("mac_address", "")
        hostname = lease.get("hostname", "")
        ip_address = lease.get("ip_address", "")

        # Create a device name consistent with device tracker
        if hostname:
            device_name = hostname
        elif mac_address:
            device_name = f"Device_{mac_address.replace(':', '')[-6:]}"
        else:
            device_name = f"Unknown_Device_{ip_address}"

        _LOGGER.info(
            "Creating diagnostic sensors for device: %s (MAC: %s, IP: %s)",
            device_name,
            mac_address,
            ip_address,
        )

        diagnostic_sensors = [
            TechnitiumDHCPDeviceIPSensor(
                dhcp_coordinator, mac_address, server_name, entry_id, device_name
            ),
            TechnitiumDHCPDeviceMaCSensor(
                dhcp_coordinator, mac_address, server_name, entry_id, device_name
            ),
            TechnitiumDHCPDeviceHostnameSensor(
                dhcp_coordinator, mac_address, server_name, entry_id, device_name
            ),
            TechnitiumDHCPDeviceLeaseObtainedSensor(
                dhcp_coordinator, mac_address, server_name, entry_id, device_name
            ),
            TechnitiumDHCPDeviceLeaseExpiresSensor(
                dhcp_coordinator, mac_address, server_name, entry_id, device_name
            ),
            TechnitiumDHCPDeviceLastSeenSensor(
                dhcp_coordinator, mac_address, server_name, entry_id, device_name
            ),
            TechnitiumDHCPDeviceIsStaleSensor(
                dhcp_coordinator, mac_address, server_name, entry_id, device_name
            ),
            TechnitiumDHCPDeviceMinutesSinceSeenSensor(
                dhcp_coordinator, mac_address, server_name, entry_id, device_name
            ),
            TechnitiumDHCPDeviceActivityScoreSensor(
                dhcp_coordinator, mac_address, server_name, entry_id, device_name
            ),
            TechnitiumDHCPDeviceIsActivelyUsedSensor(
                dhcp_coordinator, mac_address, server_name, entry_id, device_name
            ),
            TechnitiumDHCPDeviceActivitySummarySensor(
                dhcp_coordinator, mac_address, server_name, entry_id, device_name
            ),
        ]

        device_sensors.extend(diagnostic_sensors)
        _LOGGER.info(
            "Created %d diagnostic sensors for device %s",
            len(diagnostic_sensors),
            device_name,
        )

    return device_sensors


class TechnitiumDHCPDeviceDiagnosticSensor(CoordinatorEntity, SensorEntity):
    """Base class for DHCP device diagnostic sensors."""

    def __init__(
        self, coordinator, mac_address, server_name, entry_id, sensor_type, device_name
    ):
        """Initialize the diagnostic sensor."""
        super().__init__(coordinator)
        # Normalize MAC address to match coordinator format (uppercase with colons)
        self._mac_address = normalize_mac_address(mac_address)

        self._server_name = server_name
        self._entry_id = entry_id
        self._sensor_type = sensor_type
        self._device_name = device_name

        _LOGGER.debug(
            "Sensor %s initialized with normalized MAC: %s -> %s",
            sensor_type,
            mac_address,
            self._mac_address,
        )

    def _get_device_data(self):
        """Get device data from coordinator."""
        if not self.coordinator.data:
            _LOGGER.debug("Sensor %s: No coordinator data available", self._sensor_type)
            return None

        _LOGGER.debug(
            "Sensor %s: Looking for MAC %s in %d devices",
            self._sensor_type,
            self._mac_address,
            len(self.coordinator.data),
        )

        for i, device in enumerate(self.coordinator.data):
            device_mac = device.get("mac_address", "")
            _LOGGER.debug(
                "Sensor %s: Device %d MAC: '%s' vs sensor MAC: '%s'",
                self._sensor_type,
                i,
                device_mac,
                self._mac_address,
            )
            if device_mac == self._mac_address:  # Both should now be in same format
                _LOGGER.debug(
                    "Sensor %s: Found matching device data", self._sensor_type
                )
                return device

        _LOGGER.debug(
            "Sensor %s: No matching device found for MAC %s",
            self._sensor_type,
            self._mac_address,
        )
        return None

    @property
    def device_info(self):
        """Return device information for this entity - must match device tracker exactly."""
        # Use same device identifier pattern as device tracker
        if self._mac_address:
            normalized_mac = normalize_mac_address(self._mac_address)
            mac_clean = normalized_mac.replace(":", "").lower()
            device_id = f"{DOMAIN}_dhcp_device_{mac_clean}"
        else:
            # This shouldn't happen for DHCP devices, but include fallback
            device_id = f"{DOMAIN}_dhcp_device_unknown"

        manufacturer = manufacturer_from_mac(self._mac_address)

        # Try to get hostname from device data for better model detection
        device_data = self._get_device_data()
        hostname = device_data.get("hostname", "") if device_data else ""
        model = model_from_hostname(hostname)

        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=self._device_name,
            manufacturer=manufacturer,
            model=model,
            via_device=(
                DOMAIN,
                self._entry_id,
            ),  # Link to the TechnitiumDNS server device
        )

    @property
    def entity_category(self):
        """Return the entity category."""
        return EntityCategory.DIAGNOSTIC

    @property
    def available(self):
        """Return if the sensor is available."""
        coordinator_success = self.coordinator.last_update_success

        # If coordinator is successful but no data available yet, still mark as available
        # This allows sensors to show up in UI even before device data is loaded
        if coordinator_success:
            device_data = self._get_device_data()
            has_device_data = device_data is not None

            _LOGGER.debug(
                "Sensor %s availability check: coordinator_success=%s, has_device_data=%s",
                self._sensor_type,
                coordinator_success,
                has_device_data,
            )

            # Mark as available if coordinator is working, even if device data isn't available yet
            return True

        _LOGGER.debug(
            "Sensor %s availability check: coordinator failed", self._sensor_type
        )
        return False

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def unique_id(self):
        """Return a unique ID for this diagnostic sensor."""
        if self._mac_address:
            normalized_mac = normalize_mac_address(self._mac_address)
            mac_clean = normalized_mac.replace(":", "").lower()
            return f"{DOMAIN}_dhcp_sensor_{mac_clean}_{self._sensor_type}"
        else:
            # Fallback for sensors without MAC (shouldn't happen)
            return f"{DOMAIN}_dhcp_sensor_unknown_{self._sensor_type}"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._device_name} {self._sensor_type.replace('_', ' ').title()}"


class TechnitiumDHCPDeviceIPSensor(TechnitiumDHCPDeviceDiagnosticSensor):
    """IP Address diagnostic sensor for a DHCP device."""

    def __init__(self, coordinator, mac_address, server_name, entry_id, device_name):
        """Initialize the IP sensor."""
        super().__init__(
            coordinator, mac_address, server_name, entry_id, "ip_address", device_name
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"IP Address"
        # return f"{self._device_name} IP Address"

    @property
    def unique_id(self):
        """Return a unique ID."""
        mac_clean = self._mac_address.replace(":", "").lower()
        return f"technitiumdns_dhcp_{mac_clean}_ip_address"

    @property
    def native_value(self):
        """Return the IP address."""
        device_data = self._get_device_data()
        return device_data.get("ip_address") if device_data else None

    @property
    def icon(self):
        """Return the icon for this sensor."""
        return "mdi:ip-network"


class TechnitiumDHCPDeviceMaCSensor(TechnitiumDHCPDeviceDiagnosticSensor):
    """MAC Address diagnostic sensor for a DHCP device."""

    def __init__(self, coordinator, mac_address, server_name, entry_id, device_name):
        """Initialize the MAC sensor."""
        super().__init__(
            coordinator, mac_address, server_name, entry_id, "mac_address", device_name
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"MAC Address"
        # return f"{self._device_name} MAC Address"

    @property
    def unique_id(self):
        """Return a unique ID."""
        mac_clean = self._mac_address.replace(":", "").lower()
        return f"technitiumdns_dhcp_{mac_clean}_mac_address"

    @property
    def native_value(self):
        """Return the MAC address."""
        device_data = self._get_device_data()
        return device_data.get("mac_address") if device_data else None

    @property
    def icon(self):
        """Return the icon for this sensor."""
        return "mdi:network-outline"


class TechnitiumDHCPDeviceHostnameSensor(TechnitiumDHCPDeviceDiagnosticSensor):
    """Hostname diagnostic sensor for a DHCP device."""

    def __init__(self, coordinator, mac_address, server_name, entry_id, device_name):
        """Initialize the hostname sensor."""
        super().__init__(
            coordinator, mac_address, server_name, entry_id, "hostname", device_name
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"Hostname"
        # return f"{self._device_name} Hostname"

    @property
    def unique_id(self):
        """Return a unique ID."""
        mac_clean = self._mac_address.replace(":", "").lower()
        return f"technitiumdns_dhcp_{mac_clean}_hostname"

    @property
    def native_value(self):
        """Return the hostname."""
        device_data = self._get_device_data()
        hostname = device_data.get("hostname") if device_data else None
        return hostname if hostname else "Unknown"

    @property
    def icon(self):
        """Return the icon for this sensor."""
        return "mdi:dns"


class TechnitiumDHCPDeviceLeaseObtainedSensor(TechnitiumDHCPDeviceDiagnosticSensor):
    """Lease Obtained diagnostic sensor for a DHCP device."""

    def __init__(self, coordinator, mac_address, server_name, entry_id, device_name):
        """Initialize the lease obtained sensor."""
        super().__init__(
            coordinator,
            mac_address,
            server_name,
            entry_id,
            "lease_obtained",
            device_name,
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"Lease Obtained"
        # return f"{self._device_name} Lease Obtained"

    @property
    def unique_id(self):
        """Return a unique ID."""
        mac_clean = self._mac_address.replace(":", "").lower()
        return f"technitiumdns_dhcp_{mac_clean}_lease_obtained"

    @property
    def native_value(self):
        """Return the lease obtained time as a datetime object."""
        device_data = self._get_device_data()
        if device_data:
            timestamp_str = device_data.get("lease_obtained")
            return parse_timestamp(timestamp_str)
        return None

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TIMESTAMP

    @property
    def icon(self):
        """Return the icon for this sensor."""
        return "mdi:calendar-clock"


class TechnitiumDHCPDeviceLeaseExpiresSensor(TechnitiumDHCPDeviceDiagnosticSensor):
    """Lease Expires diagnostic sensor for a DHCP device."""

    def __init__(self, coordinator, mac_address, server_name, entry_id, device_name):
        """Initialize the lease expires sensor."""
        super().__init__(
            coordinator,
            mac_address,
            server_name,
            entry_id,
            "lease_expires",
            device_name,
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"Lease Expires"
        # return f"{self._device_name} Lease Expires"

    @property
    def unique_id(self):
        """Return a unique ID."""
        mac_clean = self._mac_address.replace(":", "").lower()
        return f"technitiumdns_dhcp_{mac_clean}_lease_expires"

    @property
    def native_value(self):
        """Return the lease expires time as a datetime object."""
        device_data = self._get_device_data()
        if device_data:
            timestamp_str = device_data.get("lease_expires")
            return parse_timestamp(timestamp_str)
        return None

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TIMESTAMP

    @property
    def icon(self):
        """Return the icon for this sensor."""
        return "mdi:calendar-remove"


class TechnitiumDHCPDeviceLastSeenSensor(TechnitiumDHCPDeviceDiagnosticSensor):
    """Last Seen diagnostic sensor for a DHCP device."""

    def __init__(self, coordinator, mac_address, server_name, entry_id, device_name):
        """Initialize the last seen sensor."""
        super().__init__(
            coordinator, mac_address, server_name, entry_id, "last_seen", device_name
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"Last Seen"
        # return f"{self._device_name} Last Seen"

    @property
    def unique_id(self):
        """Return a unique ID."""
        mac_clean = self._mac_address.replace(":", "").lower()
        return f"technitiumdns_dhcp_{mac_clean}_last_seen"

    @property
    def native_value(self):
        """Return the last seen time as a datetime object."""
        device_data = self._get_device_data()
        if device_data:
            timestamp_str = device_data.get("last_seen")
            return parse_timestamp(timestamp_str)
        return None

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TIMESTAMP

    @property
    def icon(self):
        """Return the icon for this sensor."""
        return "mdi:eye-outline"


class TechnitiumDHCPDeviceIsStaleSensor(TechnitiumDHCPDeviceDiagnosticSensor):
    """Is Stale diagnostic sensor for a DHCP device."""

    def __init__(self, coordinator, mac_address, server_name, entry_id, device_name):
        """Initialize the is stale sensor."""
        super().__init__(
            coordinator, mac_address, server_name, entry_id, "is_stale", device_name
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"Is Stale"
        # return f"{self._device_name} Is Stale"

    @property
    def unique_id(self):
        """Return a unique ID."""
        mac_clean = self._mac_address.replace(":", "").lower()
        return f"technitiumdns_dhcp_{mac_clean}_is_stale"

    @property
    def native_value(self):
        """Return whether the device is stale."""
        device_data = self._get_device_data()
        if device_data:
            return "Yes" if device_data.get("is_stale", False) else "No"
        return None

    @property
    def icon(self):
        """Return the icon for this sensor."""
        device_data = self._get_device_data()
        if device_data and device_data.get("is_stale", False):
            return "mdi:account-off"
        return "mdi:account-check"


class TechnitiumDHCPDeviceMinutesSinceSeenSensor(TechnitiumDHCPDeviceDiagnosticSensor):
    """Minutes Since Seen diagnostic sensor for a DHCP device."""

    def __init__(self, coordinator, mac_address, server_name, entry_id, device_name):
        """Initialize the minutes since seen sensor."""
        super().__init__(
            coordinator,
            mac_address,
            server_name,
            entry_id,
            "minutes_since_seen",
            device_name,
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"Minutes Since Seen"
        # return f"{self._device_name} Minutes Since Seen"

    @property
    def unique_id(self):
        """Return a unique ID."""
        mac_clean = self._mac_address.replace(":", "").lower()
        return f"technitiumdns_dhcp_{mac_clean}_minutes_since_seen"

    @property
    def native_value(self):
        """Return the minutes since last seen."""
        device_data = self._get_device_data()
        return device_data.get("minutes_since_seen", 0) if device_data else None

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return "min"

    @property
    def icon(self):
        """Return the icon for this sensor."""
        return "mdi:timer-outline"


class TechnitiumDHCPDeviceActivityScoreSensor(TechnitiumDHCPDeviceDiagnosticSensor):
    """Activity Score diagnostic sensor for a DHCP device."""

    def __init__(self, coordinator, mac_address, server_name, entry_id, device_name):
        """Initialize the activity score sensor."""
        super().__init__(
            coordinator,
            mac_address,
            server_name,
            entry_id,
            "activity_score",
            device_name,
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"Activity Score"
        # return f"{self._device_name} Activity Score"

    @property
    def unique_id(self):
        """Return a unique ID."""
        mac_clean = self._mac_address.replace(":", "").lower()
        return f"technitiumdns_dhcp_{mac_clean}_activity_score"

    @property
    def native_value(self):
        """Return the activity score."""
        device_data = self._get_device_data()
        return device_data.get("activity_score", 0) if device_data else None

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return "points"

    @property
    def icon(self):
        """Return the icon for this sensor."""
        device_data = self._get_device_data()
        if device_data:
            score = device_data.get("activity_score", 0)
            if score >= 75:
                return "mdi:account-check"
            elif score >= 50:
                return "mdi:account"
            elif score >= 25:
                return "mdi:account-outline"
            else:
                return "mdi:account-off"
        return "mdi:account-question"

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        device_data = self._get_device_data()
        if device_data and device_data.get("activity_score", 0) > 0:
            # Get score threshold from activity analyzer if available
            threshold = "N/A"
            if (
                hasattr(self.coordinator, "activity_analyzer")
                and self.coordinator.activity_analyzer
            ):
                threshold = self.coordinator.activity_analyzer.score_threshold
                # threshold = getattr(self.coordinator.activity_analyzer, 'score_threshold', "N/A")

            return {
                "activity_summary": device_data.get("activity_summary", ""),
                "is_actively_used": device_data.get("is_actively_used", False),
                "score_breakdown": device_data.get("score_breakdown", {}),
                "threshold": threshold,
            }
        return {}


class TechnitiumDHCPDeviceIsActivelyUsedSensor(TechnitiumDHCPDeviceDiagnosticSensor):
    """Is Actively Used diagnostic sensor for a DHCP device."""

    def __init__(self, coordinator, mac_address, server_name, entry_id, device_name):
        """Initialize the actively used sensor."""
        super().__init__(
            coordinator,
            mac_address,
            server_name,
            entry_id,
            "is_actively_used",
            device_name,
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"Is Actively Used"
        # return f"{self._device_name} Is Actively Used"

    @property
    def unique_id(self):
        """Return a unique ID."""
        mac_clean = self._mac_address.replace(":", "").lower()
        return f"technitiumdns_dhcp_{mac_clean}_is_actively_used"

    @property
    def native_value(self):
        """Return whether the device is actively used."""
        device_data = self._get_device_data()
        if device_data:
            return "Yes" if device_data.get("is_actively_used", False) else "No"
        return None

    @property
    def icon(self):
        """Return the icon for this sensor."""
        device_data = self._get_device_data()
        if device_data and device_data.get("is_actively_used", False):
            return "mdi:account-check"
        return "mdi:account-off"


class TechnitiumDHCPDeviceActivitySummarySensor(TechnitiumDHCPDeviceDiagnosticSensor):
    """Activity Summary diagnostic sensor for a DHCP device."""

    def __init__(self, coordinator, mac_address, server_name, entry_id, device_name):
        """Initialize the activity summary sensor."""
        super().__init__(
            coordinator,
            mac_address,
            server_name,
            entry_id,
            "activity_summary",
            device_name,
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"Activity Summary"
        # return f"{self._device_name} Activity Summary"

    @property
    def unique_id(self):
        """Return a unique ID."""
        mac_clean = self._mac_address.replace(":", "").lower()
        return f"technitiumdns_dhcp_{mac_clean}_activity_summary"

    @property
    def native_value(self):
        """Return the activity summary."""
        device_data = self._get_device_data()
        return (
            device_data.get("activity_summary", "No activity data")
            if device_data
            else None
        )

    @property
    def icon(self):
        """Return the icon for this sensor."""
        return "mdi:text-box-outline"


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
                _LOGGER.debug(
                    "Dynamic sensor manager - lease.get.mac_address: %s", mac_address
                )
                if mac_address:
                    normalized_mac = normalize_mac_address(mac_address)
                    self.known_devices.add(normalized_mac)
                    _LOGGER.debug("Added known device: %s", normalized_mac)

        # Set up listener for coordinator updates
        _LOGGER.debug(
            "Setting up coordinator listener, coordinator type: %s",
            type(self.dhcp_coordinator),
        )
        _LOGGER.debug(
            "Available coordinator methods: %s",
            [m for m in dir(self.dhcp_coordinator) if "listener" in m.lower()],
        )

        if hasattr(self.dhcp_coordinator, "async_add_listener"):

            def _sync_listener():
                _LOGGER.debug("DHCP COORDINATOR: async listener triggered")
                self.hass.async_create_task(self._handle_coordinator_update())

            self._listener = self.dhcp_coordinator.async_add_listener(_sync_listener)
            _LOGGER.debug("Successfully added coordinator listener")
        else:
            _LOGGER.error("DHCP coordinator does not have async_add_listener method!")
            _LOGGER.error("Coordinator class: %s", type(self.dhcp_coordinator))
            _LOGGER.error("Available methods: %s", dir(self.dhcp_coordinator))
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
        _LOGGER.debug("Dynamic sensor manager: _handle_coordinator_update called")
        if not self.dhcp_coordinator.data:
            _LOGGER.debug("Dynamic sensor manager: No coordinator data available")
            return

        current_devices = set()
        new_devices = []

        # Process current devices from coordinator
        for lease in self.dhcp_coordinator.data:
            mac_address = lease.get("mac_address", "")
            if not mac_address:
                _LOGGER.debug(
                    "Dynamic sensor manager: Skipping lease with no MAC address: %s",
                    lease,
                )
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

        # Track removed devices for logging (entities will become unavailable naturally)
        removed_devices = self.known_devices - current_devices
        if removed_devices:
            _LOGGER.info(
                "Dynamic sensor manager: Detected %d removed devices: %s",
                len(removed_devices),
                removed_devices,
            )
            _LOGGER.info(
                "Sensors for removed devices will become unavailable automatically"
            )
            # Remove them from our known devices set
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
        else:
            _LOGGER.debug(
                "Dynamic sensor manager: No new devices found in coordinator update"
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
                _LOGGER.info(
                    "Dynamic sensor manager: Successfully added %d sensors for %d new devices",
                    len(new_sensors),
                    len(devices),
                )
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
