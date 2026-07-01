from datetime import timedelta
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import (
    CONF_STATS_UPDATE_INTERVAL,
    DEFAULT_STATS_UPDATE_INTERVAL,
    DOMAIN,
    SENSOR_TYPES,
)
from .coordinator import TechnitiumDNSCoordinator
from .dhcp_sensors import DynamicSensorManager, _create_device_sensors
from .utils import (
    server_device_info,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up TechnitiumDNS sensors: main DNS statistics and device diagnostic sensors."""
    try:
        _LOGGER.info(
            "Setting up TechnitiumDNS sensor platform for entry %s", entry.entry_id
        )
        config_entry = hass.data[DOMAIN][entry.entry_id]
        api = config_entry["api"]
        server_name = config_entry["server_name"]
        stats_duration = config_entry["stats_duration"]

        # Create main DNS statistics coordinator and sensors
        update_interval = entry.options.get(
            CONF_STATS_UPDATE_INTERVAL, DEFAULT_STATS_UPDATE_INTERVAL
        )
        coordinator = TechnitiumDNSCoordinator(
            hass, api, stats_duration, update_interval=update_interval
        )
        await coordinator.async_config_entry_first_refresh()

        sensors = [
            TechnitiumDNSSensor(coordinator, sensor_type, server_name, entry.entry_id)
            for sensor_type in SENSOR_TYPES
        ]
        _LOGGER.info("Created %d main DNS statistics sensors", len(sensors))

        # Create device diagnostic sensors if DHCP coordinator is available
        dhcp_coordinator = None
        coordinators = hass.data[DOMAIN][entry.entry_id].get("coordinators", {})
        _LOGGER.debug(
            "Checking for DHCP coordinator in coordinators: %s", coordinators.keys()
        )

        if "dhcp" in coordinators:
            dhcp_coordinator = coordinators["dhcp"]
            _LOGGER.info("DHCP coordinator found, creating device diagnostic sensors")
            _LOGGER.debug(
                "DHCP coordinator data status: has_data=%s, data_length=%s",
                dhcp_coordinator.data is not None,
                len(dhcp_coordinator.data) if dhcp_coordinator.data else 0,
            )

            # Try to create sensors from current coordinator data
            device_sensors_created = False
            if dhcp_coordinator.data:
                _LOGGER.info(
                    "DHCP coordinator has %d devices, creating diagnostic sensors",
                    len(dhcp_coordinator.data),
                )
                _LOGGER.debug(
                    "DHCP coordinator device MACs: %s",
                    [lease.get("mac_address") for lease in dhcp_coordinator.data],
                )
                device_sensors = await _create_device_sensors(
                    dhcp_coordinator.data, dhcp_coordinator, server_name, entry.entry_id
                )
                sensors.extend(device_sensors)
                device_sensors_created = True
                _LOGGER.info(
                    "Created %d device diagnostic sensors from coordinator data",
                    len(device_sensors),
                )
            else:
                _LOGGER.warning("DHCP coordinator.data is: %s", dhcp_coordinator.data)

            # If no devices in coordinator data yet, rely on dynamic sensor manager
            # to create sensors when devices are discovered
            if not device_sensors_created:
                _LOGGER.info(
                    "DHCP coordinator has no data yet - sensors will be created dynamically when devices are discovered"
                )
        else:
            _LOGGER.info(
                "DHCP coordinator not available yet, only creating main DNS sensors"
            )

        _LOGGER.info("Total sensors to register: %d", len(sensors))
        async_add_entities(sensors, True)
        _LOGGER.info("All sensors registered successfully with Home Assistant")

        # Set up dynamic sensor creation if DHCP coordinator is available
        if dhcp_coordinator:
            _LOGGER.info("Setting up dynamic sensor creation for new DHCP devices")
            sensor_manager = DynamicSensorManager(
                hass, entry, async_add_entities, dhcp_coordinator, server_name
            )
            await sensor_manager.setup()

            # Force immediate sensor creation if coordinator has data but initial creation failed
            if not device_sensors_created and dhcp_coordinator.data:
                _LOGGER.info("Forcing immediate sensor creation for existing devices")
                await sensor_manager._handle_coordinator_update()

            # Store sensor manager for cleanup
            if "sensor_manager" not in hass.data[DOMAIN][entry.entry_id]:
                hass.data[DOMAIN][entry.entry_id]["sensor_manager"] = sensor_manager

    except Exception as e:
        _LOGGER.error(
            "Could not initialize TechnitiumDNS sensor platform: %s", e, exc_info=True
        )
        raise ConfigEntryNotReady from e


async def async_unload_entry(hass, entry):
    """Unload sensor platform and clean up dynamic sensor manager."""
    if sensor_manager := hass.data[DOMAIN][entry.entry_id].get("sensor_manager"):
        sensor_manager.cleanup()
        _LOGGER.info("Dynamic sensor manager cleaned up for entry %s", entry.entry_id)

    return True


class TechnitiumDNSSensor(CoordinatorEntity, SensorEntity):
    """Representation of a TechnitiumDNS sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, sensor_type, server_name, entry_id):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._server_name = server_name
        self._entry_id = entry_id
        self._attr_name = SENSOR_TYPES[sensor_type]["name"]
        self._state_class = SENSOR_TYPES[sensor_type].get("state_class", "measurement")

    @property
    def state_class(self):
        """Return the state class of the sensor."""
        return self._state_class

    @property
    def state(self):
        """Return the state of the sensor."""
        state_value = self.coordinator.data.get(self._sensor_type)
        _LOGGER.debug("State value for %s: %s", self._sensor_type, state_value)

        # Ensure the state value is within the allowable length
        if isinstance(state_value, str) and len(state_value) > 255:
            _LOGGER.error(
                "State value for %s exceeds 255 characters", self._sensor_type
            )
            return state_value[:255]

        if isinstance(state_value, (list, dict)):
            state_value = len(state_value)  # Return length if complex

        return state_value

    @property
    def extra_state_attributes(self):
        """Return additional attributes in a table-friendly format based on sensor type."""
        attributes = {
            "queries": self.coordinator.data.get("queries", 0),
            "blocked_queries": self.coordinator.data.get("blocked_queries", 0),
            "clients": self.coordinator.data.get("clients", 0),
            "update_available": self.coordinator.data.get("update_available", False),
        }

        if self._sensor_type == "top_clients":
            attributes["top_clients_table"] = [
                {"Client": client.get("name", "Unknown"), "Hits": client.get("hits", 0)}
                for client in self.coordinator.data.get("top_clients", [])
            ]
        elif self._sensor_type == "top_domains":
            attributes["top_domains_table"] = [
                {"Domain": domain.get("name", "Unknown"), "Hits": domain.get("hits", 0)}
                for domain in self.coordinator.data.get("top_domains", [])
            ]
        elif self._sensor_type == "top_blocked_domains":
            attributes["top_blocked_domains_table"] = [
                {
                    "Blocked Domain": domain.get("name", "Unknown"),
                    "Hits": domain.get("hits", 0),
                }
                for domain in self.coordinator.data.get("top_blocked_domains", [])
            ]

        return attributes

    @property
    def unique_id(self):
        """Return a unique ID."""
        return f"{DOMAIN}_dns_stats_{self._sensor_type}_{self._server_name.replace(' ', '_').lower()}"

    @property
    def available(self):
        """Return if the sensor is available."""
        return self.coordinator.last_update_success

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def device_info(self):
        """Return device information for this entity."""
        return server_device_info(self._entry_id, self._server_name)


# Diagnostic sensor base class for DHCP devices
