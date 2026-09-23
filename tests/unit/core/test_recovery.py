"""When boneIO goes into recovery mode, and how it listens there."""

from __future__ import annotations

import pytest

from boneio.core.auth.models import Role
from boneio.core.recovery import (
    CRASH_LOOP_THRESHOLD,
    StartupFailures,
    describe_config_error,
    read_web_settings,
)
from boneio.exceptions import ConfigurationException
from boneio.webui.middleware import policy

# ------------------------------------------------------------ crash counter


def _crash(n: int = 0) -> Exception:
    try:
        raise RuntimeError(f"boom {n}")
    except RuntimeError as err:
        return err


def test_a_crash_loop_takes_threshold_crashes(tmp_path):
    failures = StartupFailures(str(tmp_path / "config.yaml"))
    for i in range(CRASH_LOOP_THRESHOLD - 1):
        failures.record(_crash(i))
        assert not failures.in_crash_loop()
    failures.record(_crash())
    assert failures.in_crash_loop()


def test_last_reason_keeps_the_traceback(tmp_path):
    failures = StartupFailures(str(tmp_path / "config.yaml"))
    failures.record(_crash(7))
    reason = failures.last_reason()
    assert reason.kind == "crash"
    assert "boom 7" in reason.message
    assert "Traceback" in reason.details
    assert reason.failures == 1


def test_leaving_recovery_allows_exactly_one_retry(tmp_path):
    failures = StartupFailures(str(tmp_path / "config.yaml"))
    for _ in range(CRASH_LOOP_THRESHOLD + 2):
        failures.record(_crash())
    failures.allow_one_retry()
    assert not failures.in_crash_loop()
    failures.record(_crash())
    assert failures.in_crash_loop()


def test_clear_forgets_everything(tmp_path):
    failures = StartupFailures(str(tmp_path / "config.yaml"))
    failures.record(_crash())
    failures.clear()
    assert failures.count == 0
    assert not failures.path.exists()


def test_a_corrupt_counter_is_no_crash_loop(tmp_path):
    failures = StartupFailures(str(tmp_path / "config.yaml"))
    failures.path.write_text("{not json")
    assert failures.count == 0
    assert failures.record(_crash()) == 1


# ------------------------------------------------------------ config errors


def test_a_yaml_error_points_at_its_file_and_line(tmp_path):
    from boneio.core.config.yaml_util import load_yaml_file

    config = tmp_path / "config.yaml"
    config.write_text("output:\n  - id: a\n   pin: 1\n")
    with pytest.raises(ConfigurationException) as info:
        load_yaml_file(str(config))
    reason = describe_config_error(info.value, str(config))
    assert reason.kind == "config"
    assert reason.file == str(config)
    assert reason.line == 3


def test_an_error_in_an_include_points_at_the_include(tmp_path):
    from boneio.core.config.yaml_util import load_yaml_file

    config = tmp_path / "config.yaml"
    config.write_text("mqtt: !include mqtt.yaml\n")
    (tmp_path / "mqtt.yaml").write_text("host: a\n  port: [\n")
    with pytest.raises(ConfigurationException) as info:
        load_yaml_file(str(config))
    reason = describe_config_error(info.value, str(config))
    assert reason.file.endswith("mqtt.yaml")


def test_a_validation_error_has_no_position(tmp_path):
    reason = describe_config_error(ConfigurationException("pin: must be integer"), "/x/config.yaml")
    assert reason.file == "/x/config.yaml"
    assert reason.line is None


# ------------------------------------------------------------ web settings


def test_web_settings_from_a_config_that_loads(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("web:\n  port: 8111\n  expose: proxy\n")
    s = read_web_settings(str(config))
    assert (s.enabled, s.port, s.expose) == (True, 8111, "proxy")


def test_proxy_only_survives_a_broken_file(tmp_path):
    # Recovery must not open the panel wider than its owner asked for.
    config = tmp_path / "config.yaml"
    config.write_text("web:\n  port: 8222\n  expose: proxy\noutput:\n  - id: a\n   pin: 1\n")
    s = read_web_settings(str(config))
    assert (s.enabled, s.port, s.expose) == (True, 8222, "proxy")


def test_no_web_section_means_no_recovery_panel(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("boneio:\n  name: x\noutput:\n  - id: a\n   pin: 1\n")
    assert read_web_settings(str(config)).enabled is False


def test_an_unreadable_config_gets_the_defaults(tmp_path):
    s = read_web_settings(str(tmp_path / "missing.yaml"))
    assert (s.enabled, s.port, s.expose) == (True, 8090, "all")


# ------------------------------------------------------------------ policy


@pytest.mark.parametrize("method", ["GET", "POST", "PUT"])
def test_every_recovery_route_is_admin_only(method):
    for path in ("/api/recovery/status", "/api/recovery/file", "/api/recovery/logs"):
        assert policy.required_role(method, path) == Role.ADMIN


# ------------------------------------------------------------- panel link


@pytest.mark.parametrize(
    ("web", "url"),
    [
        ("web:\n  proxy_port: 8443\n", "https://10.0.0.5:8443"),
        ("web:\n  expose: proxy\n", "https://10.0.0.5:8443"),
        ("web:\n  port: 8090\n", "http://10.0.0.5:8090"),
    ],
)
def test_panel_url_follows_the_regular_oled_rule(tmp_path, web, url):
    config = tmp_path / "config.yaml"
    config.write_text(web)
    assert read_web_settings(str(config)).panel_url("10.0.0.5") == url


def test_proxy_port_is_read_from_a_broken_file(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("web:\n  proxy_port: 8443\n  cloud:\n    enabled: true\noutput:\n  - id: a\n   pin: 1\n")
    assert read_web_settings(str(config)).panel_url("10.0.0.5") == "https://10.0.0.5:8443"


@pytest.mark.parametrize("address", [None, "", "none"])
def test_no_address_no_link(tmp_path, address):
    config = tmp_path / "config.yaml"
    config.write_text("web:\n  proxy_port: 8443\n")
    assert read_web_settings(str(config)).panel_url(address) is None
