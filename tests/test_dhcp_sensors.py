"""Direct tests for the DHCP per-device diagnostic sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.technitiumdns.const import DOMAIN
from custom_components.technitiumdns.dhcp_sensors import (
    TechnitiumDHCPDeviceActivityScoreSensor,
    TechnitiumDHCPDeviceHostnameSensor,
    TechnitiumDHCPDeviceIPSensor,
    TechnitiumDHCPDeviceIsActivelyUsedSensor,
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
    return coordinator


async def test_create_device_sensors_count() -> None:
    sensors = await _create_device_sensors(
        [_LEASE], _coordinator([_LEASE]), "Home DNS", "entry1"
    )
    assert len(sensors) == 11


async def test_ip_sensor_value_and_unique_id() -> None:
    sensors = await _create_device_sensors(
        [_LEASE], _coordinator([_LEASE]), "Home DNS", "entry1"
    )
    ip = next(s for s in sensors if isinstance(s, TechnitiumDHCPDeviceIPSensor))
    assert ip.native_value == "192.168.1.50"
    assert ip.unique_id == "technitiumdns_dhcp_aabbcc000001_ip_address"
    assert ip.available is True


async def test_hostname_and_activity_sensors() -> None:
    sensors = await _create_device_sensors(
        [_LEASE], _coordinator([_LEASE]), "Home DNS", "entry1"
    )
    hostname = next(
        s for s in sensors if isinstance(s, TechnitiumDHCPDeviceHostnameSensor)
    )
    score = next(
        s for s in sensors if isinstance(s, TechnitiumDHCPDeviceActivityScoreSensor)
    )
    active = next(
        s for s in sensors if isinstance(s, TechnitiumDHCPDeviceIsActivelyUsedSensor)
    )
    assert hostname.native_value == "raspberrypi"
    assert score.native_value == 42
    assert active.native_value in (True, "on", "true", "Yes")


async def test_sensor_unavailable_when_device_absent() -> None:
    # coordinator has no devices -> the sensor's device data is missing
    sensors = await _create_device_sensors(
        [_LEASE], _coordinator([]), "Home DNS", "entry1"
    )
    ip = next(s for s in sensors if isinstance(s, TechnitiumDHCPDeviceIPSensor))
    assert ip.native_value is None


async def test_all_diagnostic_sensors_expose_values() -> None:
    """Every diagnostic sensor exposes identity, value and device_info safely."""
    sensors = await _create_device_sensors(
        [_LEASE], _coordinator([_LEASE]), "Home DNS", "entry1"
    )
    for sensor in sensors:
        assert sensor.unique_id
        assert sensor.name
        # exercises native_value (+ _get_device_data) and the device_info build
        _ = sensor.native_value
        assert (DOMAIN, "technitiumdns_dhcp_device_aabbcc000001") in sensor.device_info[
            "identifiers"
        ]

    by_type = {type(s).__name__: s for s in sensors}
    assert by_type["TechnitiumDHCPDeviceIsStaleSensor"].native_value == "No"
    assert by_type["TechnitiumDHCPDeviceMinutesSinceSeenSensor"].native_value == 0
    assert (
        by_type["TechnitiumDHCPDeviceActivitySummarySensor"].native_value
        == "Actively used"
    )
    assert by_type["TechnitiumDHCPDeviceIsActivelyUsedSensor"].native_value == "Yes"
