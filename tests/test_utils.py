"""Tests for the pure helper functions in utils.py."""

from __future__ import annotations

from datetime import datetime

import pytest

from custom_components.technitiumdns.const import DOMAIN
from custom_components.technitiumdns.utils import (
    manufacturer_from_mac,
    model_from_hostname,
    normalize_mac_address,
    parse_ip_ranges,
    parse_timestamp,
    server_device_info,
    should_track_ip,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("aabbccddeeff", "AA:BB:CC:DD:EE:FF"),
        ("aa-bb-cc-dd-ee-ff", "AA:BB:CC:DD:EE:FF"),
        ("aa:bb:cc:dd:ee:ff", "AA:BB:CC:DD:EE:FF"),
        ("", ""),
        ("weird", "WEIRD"),
    ],
)
def test_normalize_mac_address(value: str, expected: str) -> None:
    assert normalize_mac_address(value) == expected


@pytest.mark.parametrize(
    ("mac", "expected"),
    [
        ("00:21:5A:11:22:33", "Apple"),
        ("B8:27:EB:00:00:01", "Raspberry Pi Foundation"),
        ("de:ad:be:ef:00:00", "Unknown"),
        ("", "Unknown"),
    ],
)
def test_manufacturer_from_mac(mac: str, expected: str) -> None:
    assert manufacturer_from_mac(mac) == expected


@pytest.mark.parametrize(
    ("hostname", "expected"),
    [
        ("raspberrypi", "Raspberry Pi"),
        ("rpi-node", "Raspberry Pi"),
        ("Johns-iPhone", "iOS Device"),
        ("my-ipad", "iOS Device"),
        ("android-1234", "Android Device"),
        ("WINDOWS-PC", "Windows PC"),
        ("MacBook", "Mac Computer"),
        ("switch01", "Network Device"),
        ("", "Network Device"),
    ],
)
def test_model_from_hostname(hostname: str, expected: str) -> None:
    assert model_from_hostname(hostname) == expected


def test_parse_ip_ranges_single() -> None:
    assert parse_ip_ranges("192.168.1.100") == {"192.168.1.100"}


def test_parse_ip_ranges_cidr() -> None:
    result = parse_ip_ranges("192.168.1.0/30")
    assert "192.168.1.1" in result
    assert "192.168.1.2" in result


def test_parse_ip_ranges_span() -> None:
    assert parse_ip_ranges("10.0.0.1-10.0.0.3") == {
        "10.0.0.1",
        "10.0.0.2",
        "10.0.0.3",
    }


def test_parse_ip_ranges_empty_and_invalid() -> None:
    assert parse_ip_ranges("") == set()
    assert parse_ip_ranges("not-an-ip") == set()


def test_should_track_ip_disabled() -> None:
    assert should_track_ip("1.2.3.4", "disabled", "") is True


def test_should_track_ip_include() -> None:
    assert should_track_ip("192.168.1.5", "include", "192.168.1.0/24") is True
    assert should_track_ip("10.0.0.1", "include", "192.168.1.0/24") is False


def test_should_track_ip_exclude() -> None:
    assert should_track_ip("192.168.1.5", "exclude", "192.168.1.0/24") is False
    assert should_track_ip("10.0.0.1", "exclude", "192.168.1.0/24") is True


def test_should_track_ip_invalid_address() -> None:
    assert should_track_ip("nope", "include", "192.168.1.0/24") is False


def test_parse_timestamp() -> None:
    assert parse_timestamp("") is None
    assert parse_timestamp("not-a-date") is None
    parsed = parse_timestamp("2026-01-15T10:30:00Z")
    assert isinstance(parsed, datetime)


def test_server_device_info() -> None:
    info = server_device_info("entry123", "Home DNS")
    assert (DOMAIN, "entry123") in info["identifiers"]
    assert info["manufacturer"] == "Technitium"
