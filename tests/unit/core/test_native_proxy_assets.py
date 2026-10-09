"""The files a packaged Caddy needs must stay consistent with the container setup."""

from __future__ import annotations

from importlib.resources import files

import yaml

_A = files("boneio.migrations.assets")


def _text(path: str) -> str:
    return _A.joinpath(path).read_text()


def test_native_compose_has_no_caddy_and_binds_1880_to_loopback() -> None:
    native = yaml.safe_load(_text("docker/nodered/docker-compose-native-proxy.yaml"))
    assert "caddy" not in native["services"]
    assert native["services"]["node-red"]["ports"] == ["127.0.0.1:1880:1880"]


def test_native_compose_is_the_stock_one_minus_caddy() -> None:
    stock = yaml.safe_load(_text("docker/nodered/docker-compose.yaml"))
    native = yaml.safe_load(_text("docker/nodered/docker-compose-native-proxy.yaml"))
    del stock["services"]["caddy"]
    del native["services"]["node-red"]["ports"]
    assert native == stock


def test_dropin_gates_on_marker_and_drops_privileges() -> None:
    dropin = _text("systemd/caddy-boneio.conf")
    assert "ConditionPathExists=/etc/boneio/proxy-native" in dropin
    assert "\nAmbientCapabilities=\n" in dropin
    assert "\nUMask=0077\n" in dropin
    assert "\nCapabilityBoundingSet=\n" in dropin


def test_dropin_restarts_a_crashed_caddy() -> None:
    dropin = _text("systemd/caddy-boneio.conf")
    assert "\nRestart=on-failure\n" in dropin
    assert "\nRestartSec=5s\n" in dropin


def test_dropin_reload_skips_the_hostname_and_start_exports_the_root() -> None:
    dropin = _text("systemd/caddy-boneio.conf")
    assert "\nExecReload=+/usr/lib/boneio/proxy-config --reload\n" in dropin
    # "-": a failed export must not fail, and so restart, a running Caddy.
    assert "\nExecStartPost=-+/usr/lib/boneio/proxy-config --export-root\n" in dropin


def test_apt_list_is_signed_and_https() -> None:
    line = _text("apt/caddy-stable.list")
    assert "signed-by=" in line and "https://" in line


def test_pin_is_a_release_series_pin() -> None:
    pin = _text("apt/caddy-pin.pref")
    assert "Pin: version 2.11.*" in pin and "Pin-Priority: 1001" in pin


def test_502_copies_are_identical() -> None:
    assert (
        _A.joinpath("caddy/502.html").read_bytes()
        == _A.joinpath("docker/nodered/caddy/502.html").read_bytes()
    )


def test_the_cloudsmith_repository_is_taken_off_again() -> None:
    """1.6.44: an apt source that answers 402 fails every apt-get update."""
    from boneio.migrations.versions import v1_6_44_caddy_from_github as m

    actions = [a.to_dict() for a in m.plan()]
    removed = {a["path"] for a in actions if a["action"] == "remove_file"}
    assert removed == {
        "/etc/apt/apt.conf.d/53boneio-caddy",
        "/etc/apt/sources.list.d/caddy-stable.list",
        "/etc/apt/preferences.d/caddy",
        "/usr/share/keyrings/caddy-stable-archive-keyring.gpg",
    }
    # The helper that installs from GitHub goes in first, pristine copy included.
    installs = [a["dst"] for a in actions[:2]]
    assert installs == ["/usr/lib/boneio/trusted/boneio-containers", "/usr/sbin/boneio-containers"]


def test_etc_boneio_is_made_readable_again() -> None:
    """1.6.45: the proxy markers live there; the password file keeps its own 0600."""
    from boneio.migrations.versions import v1_6_45_etc_boneio_readable as m

    assert [a.to_dict() for a in m.plan()] == [{
        "action": "set_file_permissions", "path": "/etc/boneio",
        "mode": 0o755, "owner": "root", "group": "root",
    }]
