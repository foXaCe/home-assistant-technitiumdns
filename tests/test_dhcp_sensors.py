"""Direct tests for the DHCP per-device diagnostic sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass

from custom_components.technitiumdns.const import DOMAIN
from custom_components.technitiumdns.dhcp_sensors import (
    DHCP_SENSOR_DESCRIPTIONS,
    _create_device_sensors,
)

_LEASE = {
    "mac_address": "AA:BB:CC:00:00:01",
    "ip_address": "192.168.1.50",
    "hostname": "raspberrypi",
    "lease_obtained": "2026-01-01T00:00:00+00:00",
    "lease_expires": "2026-01-02T00:00:00+00:00",
    "last_seen": None,
    "is_stale": False,
    "minutes_since_seen": 0,
    "activity_score": 42,
    "is_actively_used": True,
    "activity_summary": "Actively used",
}


def _coordinator(leases):
    coordinator = MagicMock()
    coordinator.data = leases
    coordinator.last_update_success = True
    coordinator.activity_analyzer = None
    return coordinator


def _by_key(sensors):
    return {s.entity_description.key: s for s in sensors}


async def test_create_device_sensors_count() -> None:
    sensors = await _create_device_sensors(
        [_LEASE], _coordinator([_LEASE]), "Home DNS", "entry1"
    )
    assert len(sensors) == len(DHCP_SENSOR_DESCRIPTIONS) == 11


async def test_ip_sensor_value_and_unique_id() -> None:
    sensors = await _create_device_sensors(
        [_LEASE], _coordinator([_LEASE]), "Home DNS", "entry1"
    )
    ip = _by_key(sensors)["ip_address"]
    assert ip.native_value == "192.168.1.50"
    assert ip.unique_id == "entry1_dhcp_aabbcc000001_ip_address"
    assert ip.available is True
    assert ip.has_entity_name is True


async def test_hostname_and_activity_sensors() -> None:
    by_key = _by_key(
        await _create_device_sensors(
            [_LEASE], _coordinator([_LEASE]), "Home DNS", "entry1"
        )
    )
    assert by_key["hostname"].native_value == "raspberrypi"
    assert by_key["activity_score"].native_value == 42
    # Boolean-ish states are exposed as translatable enum options.
    assert by_key["is_actively_used"].native_value == "active"
    assert by_key["is_actively_used"].device_class == SensorDeviceClass.ENUM


async def test_sensor_unavailable_when_device_absent() -> None:
    # coordinator has no devices -> the sensor's device data is missing
    sensors = await _create_device_sensors(
        [_LEASE], _coordinator([]), "Home DNS", "entry1"
    )
    ip = _by_key(sensors)["ip_address"]
    assert ip.native_value is None


async def test_enum_states_and_icons() -> None:
    """Stale/active enum sensors flip value and icon with the underlying flag."""
    stale_lease = {**_LEASE, "is_stale": True, "is_actively_used": False}
    by_key = _by_key(
        await _create_device_sensors(
            [stale_lease], _coordinator([stale_lease]), "Home DNS", "entry1"
        )
    )
    assert by_key["is_stale"].native_value == "stale"
    assert by_key["is_stale"].icon == "mdi:account-off"
    assert by_key["is_actively_used"].native_value == "inactive"
    assert by_key["is_actively_used"].icon == "mdi:account-off"


async def test_activity_score_attributes() -> None:
    by_key = _by_key(
        await _create_device_sensors(
            [_LEASE], _coordinator([_LEASE]), "Home DNS", "entry1"
        )
    )
    attrs = by_key["activity_score"].extra_state_attributes
    assert attrs["threshold"] == "N/A"
    assert attrs["is_actively_used"] is True


async def test_all_diagnostic_sensors_expose_values() -> None:
    """Every diagnostic sensor exposes identity, value and device_info safely."""
    sensors = await _create_device_sensors(
        [_LEASE], _coordinator([_LEASE]), "Home DNS", "entry1"
    )
    for sensor in sensors:
        assert sensor.unique_id.startswith("entry1_dhcp_aabbcc000001_")
        assert sensor.entity_description.translation_key.startswith("dhcp_")
        # exercises native_value (+ _get_device_data) and the device_info build
        _ = sensor.native_value
        assert (DOMAIN, "technitiumdns_dhcp_device_aabbcc000001") in sensor.device_info[
            "identifiers"
        ]

    by_key = _by_key(sensors)
    assert by_key["is_stale"].native_value == "not_stale"
    assert by_key["minutes_since_seen"].native_value == 0
    assert by_key["activity_summary"].native_value == "Actively used"
