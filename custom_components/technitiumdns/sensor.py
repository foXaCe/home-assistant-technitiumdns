from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_STATS_UPDATE_INTERVAL,
    DEFAULT_STATS_UPDATE_INTERVAL,
    DOMAIN,
)
from .coordinator import TechnitiumDNSCoordinator
from .dhcp_sensors import DynamicSensorManager, _create_device_sensors
from .utils import server_device_info

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
            TechnitiumDNSSensor(coordinator, description, server_name, entry.entry_id)
            for description in SENSOR_DESCRIPTIONS
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


@dataclass(frozen=True, kw_only=True)
class TechnitiumSensorDescription(SensorEntityDescription):
    """Describes a TechnitiumDNS statistics sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _stat_value(data: dict[str, Any], key: str) -> StateType:
    value = data.get(key)
    if isinstance(value, (list, dict)):
        return len(value)
    if isinstance(value, str) and len(value) > 255:
        return value[:255]
    return value


def _top_table(data: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    return {
        f"{key}_table": [
            {label: item.get("name", "Unknown"), "Hits": item.get("hits", 0)}
            for item in data.get(key, [])
        ]
    }


_MEASUREMENT_KEYS = (
    "queries",
    "blocked_queries",
    "clients",
    "no_error",
    "server_failure",
    "nx_domain",
    "refused",
    "authoritative",
    "recursive",
    "cached",
    "dropped",
    "zones",
    "cached_entries",
    "allowed_zones",
    "blocked_zones",
    "allow_list_zones",
    "block_list_zones",
)
_TOP_KEYS = {
    "top_clients": "Client",
    "top_domains": "Domain",
    "top_blocked_domains": "Blocked Domain",
}

SENSOR_DESCRIPTIONS: tuple[TechnitiumSensorDescription, ...] = (
    *(
        TechnitiumSensorDescription(
            key=key,
            translation_key=key,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda data, k=key: _stat_value(data, k),
        )
        for key in _MEASUREMENT_KEYS
    ),
    TechnitiumSensorDescription(
        key="update_available",
        translation_key="update_available",
        device_class=SensorDeviceClass.ENUM,
        options=["up_to_date", "available"],
        value_fn=lambda data: (
            "available" if data.get("update_available") else "up_to_date"
        ),
    ),
    *(
        TechnitiumSensorDescription(
            key=key,
            translation_key=key,
            value_fn=lambda data, k=key: _stat_value(data, k),
            attrs_fn=lambda data, k=key, lbl=label: _top_table(data, k, lbl),
        )
        for key, label in _TOP_KEYS.items()
    ),
)


class TechnitiumDNSSensor(CoordinatorEntity, SensorEntity):
    """Representation of a TechnitiumDNS statistics sensor."""

    _attr_has_entity_name = True
    entity_description: TechnitiumSensorDescription

    def __init__(self, coordinator, description, server_name, entry_id):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._server_name = server_name
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the current value of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the top-N table attributes, when applicable."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)

    @property
    def device_info(self):
        """Return device information for this entity."""
        return server_device_info(self._entry_id, self._server_name)


# Diagnostic sensor base class for DHCP devices
