"""Tests for the SmartActivityAnalyzer heuristic engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.technitiumdns.activity_analyzer import (
    SmartActivityAnalyzer,
    analyze_batch_device_activity,
)


def _log(ip: str, domain: str, protocol: str = "Udp", when: datetime | None = None):
    ts = (when or datetime.now(timezone.utc)).isoformat()
    return {
        "clientIpAddress": ip,
        "qname": domain,
        "protocol": protocol,
        "timestamp": ts,
    }


def _analyzer() -> SmartActivityAnalyzer:
    return SmartActivityAnalyzer(score_threshold=55, analysis_window_minutes=120)


def test_no_activity_for_empty_logs() -> None:
    result = _analyzer().analyze_device_activity([], "192.168.1.10")
    assert result["activity_score"] == 0
    assert result["is_actively_used"] is False
    assert result["total_queries"] == 0
    assert result["analysis_summary"] == "No DNS activity found"


def test_activity_is_scored() -> None:
    logs = [
        _log("192.168.1.10", f"site{i}.example.com", "Tcp" if i % 3 else "Udp")
        for i in range(20)
    ]
    result = _analyzer().analyze_device_activity(logs, "192.168.1.10")

    assert result["total_queries"] == 20
    assert 0 <= result["activity_score"] <= 100
    assert result["protocol_diversity"] == 2
    assert set(result["score_breakdown"]) == {
        "background_score",
        "protocol_score",
        "diversity_score",
        "frequency_score",
        "timing_score",
    }


def test_other_ip_and_stale_logs_are_ignored() -> None:
    stale = datetime.now(timezone.utc) - timedelta(hours=5)
    logs = [
        _log("192.168.1.99", "other.example.com"),  # different device
        _log("192.168.1.10", "old.example.com", when=stale),  # outside window
    ]
    result = _analyzer().analyze_device_activity(logs, "192.168.1.10")
    assert result["total_queries"] == 0


def test_high_diversity_scores_higher_than_single_domain() -> None:
    analyzer = _analyzer()
    diverse = [_log("192.168.1.10", f"host{i}.example{i}.com") for i in range(15)]
    monotonous = [_log("192.168.1.10", "same.example.com") for _ in range(15)]

    diverse_score = analyzer.analyze_device_activity(diverse, "192.168.1.10")
    mono_score = analyzer.analyze_device_activity(monotonous, "192.168.1.10")

    assert (
        diverse_score["score_breakdown"]["diversity_score"]
        >= mono_score["score_breakdown"]["diversity_score"]
    )


def test_batch_analysis() -> None:
    logs = [_log("192.168.1.10", "a.example.com"), _log("192.168.1.11", "b.example.com")]
    results = analyze_batch_device_activity(
        logs, ["192.168.1.10", "192.168.1.11", "192.168.1.12"], _analyzer()
    )
    assert set(results) == {"192.168.1.10", "192.168.1.11", "192.168.1.12"}
    assert results["192.168.1.10"]["total_queries"] == 1
    assert results["192.168.1.12"]["total_queries"] == 0
