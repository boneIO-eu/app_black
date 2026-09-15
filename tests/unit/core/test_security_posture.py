"""Tests for the security posture model."""

from __future__ import annotations

import pytest

from boneio.core.security.posture import (
    DEFAULT_FRAME_ANCESTORS,
    DEFAULT_MQTT_PASSWORD,
    Severity,
    State,
    evaluate,
)

SECURE = {
    "mqtt": {"host": "localhost", "password": "wlasne-haslo"},
    "web": {"port": 8090, "security": {"frame_ancestors": "'self'"}},
}


def _posture(config=None, **kw):
    defaults = dict(
        is_provisioned=True,
        anonymous_allowed=False,
        auth_required=True,
        cloud_active=True,
    )
    defaults.update(kw)
    return evaluate(config if config is not None else SECURE, **defaults)


def _check(posture, check_id):
    return next(c for c in posture.checks if c.id == check_id)


# ------------------------------------------------------------- a clean device


def test_a_hardened_device_reports_nothing_outstanding(monkeypatch):
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    posture = _posture()
    assert posture.failed == []
    assert posture.worst is None


# ----------------------------------------------------------- what it catches


def test_a_device_with_no_account_is_critical(monkeypatch):
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    posture = _posture(is_provisioned=False)
    check = _check(posture, "admin_account")
    assert check.state is State.FAILED
    assert check.severity is Severity.CRITICAL


def test_unauthenticated_access_is_critical(monkeypatch):
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    posture = _posture(anonymous_allowed=True, auth_required=False)
    assert _check(posture, "anonymous_access").state is State.FAILED


def test_the_opt_out_is_not_flagged_once_it_stops_applying(monkeypatch):
    """allow_anonymous has no effect once an account exists, so reporting it
    would send people chasing a setting that is already inert."""
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    posture = _posture(anonymous_allowed=True, auth_required=True)
    assert _check(posture, "anonymous_access").state is State.OK


def test_the_factory_mqtt_password_is_caught(monkeypatch):
    """It is published and identical on every device ever shipped."""
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    config = {"mqtt": {"password": DEFAULT_MQTT_PASSWORD}}
    check = _check(_posture(config), "mqtt_password")
    assert check.state is State.FAILED
    assert check.severity is Severity.CRITICAL


def test_a_changed_mqtt_password_passes(monkeypatch):
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    assert _check(_posture({"mqtt": {"password": "cos-innego"}}), "mqtt_password").state is State.OK


def test_no_broker_is_not_a_finding(monkeypatch):
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    assert _check(_posture({}), "mqtt_password").state is State.OK


def test_leftover_credentials_in_config_are_flagged(monkeypatch):
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    config = {"web": {"auth": {"username": "pawel", "password": "stare"}}}
    assert _check(_posture(config), "legacy_web_auth").state is State.FAILED


def test_a_self_signed_certificate_is_information_not_alarm(monkeypatch):
    """It is the honest default without a domain, not a way in."""
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    check = _check(_posture(cloud_active=False), "certificate")
    assert check.state is State.FAILED
    assert check.severity is Severity.INFO


def test_dev_mode_is_reported_when_set(monkeypatch):
    monkeypatch.setenv("BONEIO_DEV", "1")
    assert _check(_posture(), "dev_mode").state is State.FAILED


def test_dev_mode_is_absent_when_unset(monkeypatch):
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    assert not any(c.id == "dev_mode" for c in _posture().checks)


# ----------------------------------------------------------------- reporting


def test_failures_are_ordered_worst_first(monkeypatch):
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    posture = _posture(
        {"mqtt": {"password": DEFAULT_MQTT_PASSWORD}}, cloud_active=False
    )
    severities = [c.severity for c in posture.failed]
    assert severities == sorted(
        severities, key=lambda s: {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}[s]
    )
    assert posture.worst is Severity.CRITICAL


def test_the_summary_counts_by_severity(monkeypatch):
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    summary = _posture(
        {"mqtt": {"password": DEFAULT_MQTT_PASSWORD}}, cloud_active=False
    ).to_dict()["summary"]
    assert summary["critical"] >= 1
    assert summary["worst"] == "critical"


def test_an_unreadable_config_does_not_crash_the_evaluation(monkeypatch):
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    posture = evaluate(
        None,
        is_provisioned=True,
        anonymous_allowed=False,
        auth_required=True,
        cloud_active=False,
    )
    assert posture.checks


def test_every_failure_says_how_to_fix_it():
    """A finding nobody can act on is just noise."""
    posture = _posture({"mqtt": {"password": DEFAULT_MQTT_PASSWORD}}, is_provisioned=False)
    assert all(c.remedy for c in posture.failed)


def test_info_findings_do_not_drive_the_badge():
    """A default device must not wear a permanent red badge.

    A self-signed certificate is INFO and applies to almost every controller.
    If it counted, the badge would always be red and would stop meaning
    anything.
    """
    posture = evaluate(
        {"mqtt": {"password": "changed"}},
        is_provisioned=True,
        anonymous_allowed=False,
        auth_required=True,
        cloud_active=False,
    )
    assert posture.failed  # the advice is still reported
    assert posture.actionable == []
    assert posture.to_dict()["summary"]["actionable"] == 0


def test_a_real_problem_is_actionable():
    """Critical and warning findings do drive it."""
    posture = evaluate(
        {"mqtt": {"password": DEFAULT_MQTT_PASSWORD}},
        is_provisioned=True,
        anonymous_allowed=False,
        auth_required=True,
        cloud_active=False,
    )
    assert [c.id for c in posture.actionable] == ["mqtt_password"]
    assert posture.to_dict()["summary"]["actionable"] == 1


def _framing(config: dict):
    """The frame_ancestors check for one configuration."""
    posture = evaluate(
        config,
        is_provisioned=True,
        anonymous_allowed=False,
        auth_required=True,
        cloud_active=False,
    )
    return next(c for c in posture.checks if c.id == "frame_ancestors")


def test_an_unconfigured_device_is_already_protected():
    """Saying nothing now means 'self', so it must not read as a problem.

    'self' is also what the boneIO Black add-on needs: it proxies each device,
    so the framed page is on Home Assistant's own origin.
    """
    check = _framing({})
    assert check.state is State.OK
    assert DEFAULT_FRAME_ANCESTORS in check.detail


def test_explicitly_unrestricted_framing_is_a_warning():
    """`*` is a deliberate choice, and worth saying out loud."""
    check = _framing({"web": {"security": {"frame_ancestors": "*"}}})
    assert check.state is State.FAILED
    assert check.severity is Severity.WARNING
    assert "'self'" in check.remedy


def test_an_extra_origin_alongside_self_still_passes():
    """A dashboard framing the device directly is a supported setup."""
    check = _framing(
        {"web": {"security": {"frame_ancestors": "'self' https://ha.local:8123"}}}
    )
    assert check.state is State.OK
    assert "https://ha.local:8123" in check.detail


def test_a_wildcard_hidden_among_origins_is_still_a_wildcard():
    """`'self' *` permits everything, whatever it looks like."""
    assert _framing(
        {"web": {"security": {"frame_ancestors": "'self' *"}}}
    ).state is State.FAILED
