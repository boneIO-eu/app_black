"""Tests for boneio-proxy-config, the root generator of the packaged Caddy's config.

It runs as root and reads files the unprivileged ``boneio`` account writes: the
compose ``.env`` and two certificate pairs. What is worth guarding is that none
of that can steer root — a port is a number or the default, and a certificate
is a small regular file reached without a symlink, or it is not used at all —
and that the Caddyfile it writes means what the container's did.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from tests.tls_material import encrypted_key, make_ca, make_leaf

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER = REPO_ROOT / "boneio" / "migrations" / "assets" / "helpers" / "boneio-proxy-config"

CERT = b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
KEY = b"-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----\n"


@pytest.fixture(scope="module")
def helper():
    """The helper loaded as a module (it has no .py extension)."""
    loader = SourceFileLoader("boneio_proxy_config", str(HELPER))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


@pytest.fixture
def pair(tmp_path):
    """A valid-looking certificate pair in its own directory."""
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "fullchain.pem").write_bytes(CERT)
    (custom / "privkey.pem").write_bytes(KEY)
    return custom / "fullchain.pem", custom / "privkey.pem"


# --------------------------------------------------------------------- ports


def test_ports_read_from_env(helper):
    assert helper.read_ports("WEB_PORT=9000\nHTTPS_PORT=9443\n") == helper.Ports(
        9000, 8091, 9443
    )


def test_ports_default_when_empty(helper):
    assert helper.read_ports("") == helper.Ports(8090, 8091, 8443)


def test_port_injection_falls_back(helper):
    assert helper.read_ports("WEB_PORT=80;rm -rf /\n").web == 8090


def test_port_out_of_range_falls_back(helper):
    assert helper.read_ports("WEB_PORT=70000\n").web == 8090
    assert helper.read_ports("WEB_PORT=0\n").web == 8090


@pytest.mark.parametrize(
    "value", [" 80x", "+80", "8_0", "١٢", "0x50", "80 }\n:1 {", ""]
)
def test_port_that_is_not_plain_digits_falls_back(helper, value):
    assert helper.read_ports(f"HTTP_PORT={value}\n").http == 8091


def test_ports_accept_export_quotes_crlf_and_last_wins(helper):
    text = "# comment\r\nexport WEB_PORT=\"9001\"\r\nHTTP_PORT='8081'\nWEB_PORT=9002\n"
    assert helper.read_ports(text) == helper.Ports(9002, 8081, 8443)


def test_a_port_too_long_for_int_falls_back(helper):
    # int() refuses more than 4300 digits with ValueError, not OSError.
    assert helper.read_ports("WEB_PORT=" + "9" * 5000 + "\n").web == 8090
    assert helper.read_ports("HTTPS_PORT=008443\n").https == 8443


def test_a_privileged_listen_port_falls_back(helper):
    # The unit has no capabilities: Caddy cannot bind below 1024.
    assert helper.read_ports("HTTPS_PORT=443\n").https == 8443
    assert helper.read_ports("HTTP_PORT=80\n").http == 8091
    # The panel itself may still be anywhere.
    assert helper.read_ports("WEB_PORT=80\n").web == 80


def test_colliding_listen_ports_fall_back(helper):
    assert helper.read_ports("HTTP_PORT=9000\nHTTPS_PORT=9000\n") == helper.Ports(
        8090, 8091, 8443
    )
    assert helper.read_ports("HTTPS_PORT=1880\n").https == 8443
    assert helper.read_ports("WEB_PORT=9000\nHTTPS_PORT=9000\n").https == 8443
    # The fallback must not land on the other listener.
    assert helper.read_ports("HTTP_PORT=80\nHTTPS_PORT=8091\n") == helper.Ports(
        8090, 8091, 8443
    )


# ---------------------------------------------------------------- pem pairs


def test_good_pair_is_read(helper, pair):
    assert helper.read_pem_pair(*pair) == (CERT, KEY)


def test_symlinked_key_is_refused(helper, pair, tmp_path):
    # The target is a perfectly good key, so only the symlink can be the reason.
    secret = tmp_path / "shadow"
    secret.write_bytes(KEY)
    pair[1].unlink()
    pair[1].symlink_to(secret)
    assert helper.read_pem_pair(*pair) is None


def test_symlinked_parent_directory_is_refused(helper, pair, tmp_path):
    link = tmp_path / "elsewhere"
    link.symlink_to(pair[0].parent)
    assert helper.read_pem_pair(link / "fullchain.pem", link / "privkey.pem") is None


def test_hard_link_is_refused(helper, pair, tmp_path):
    os.link(pair[1], tmp_path / "second-name")
    assert helper.read_pem_pair(*pair) is None


def test_oversized_file_is_refused(helper, pair):
    pair[1].write_bytes(KEY + b"A" * (1024 * 1024))
    assert helper.read_pem_pair(*pair) is None


def test_directory_instead_of_file_is_refused(helper, pair):
    pair[0].unlink()
    pair[0].mkdir()
    assert helper.read_pem_pair(*pair) is None


def test_fifo_is_refused_without_blocking(helper, pair):
    # A blocking open on a FIFO would hang ExecStartPre until systemd gives up.
    pair[1].unlink()
    os.mkfifo(pair[1])
    assert helper.read_pem_pair(*pair) is None


def test_missing_file_is_none(helper, pair):
    pair[1].unlink()
    assert helper.read_pem_pair(*pair) is None


def test_not_a_pem_is_refused(helper, pair):
    pair[0].write_bytes(b"root:$y$j9T$...:19000:0:99999:7:::\n")
    assert helper.read_pem_pair(*pair) is None
    pair[0].write_bytes(CERT)
    pair[1].write_bytes(CERT)
    assert helper.read_pem_pair(*pair) is None


# ------------------------------------------------------------------- render

DEFAULT = (8090, 8091, 8443)


def _render(helper, **flags):
    return helper.render(helper.Ports(*DEFAULT), **flags)


def test_render_local(helper):
    text = _render(helper, custom=False, cloud=False)
    for needle in (
        "on_demand",
        "lifetime 180d",
        "intermediate_lifetime 365d",
        "127.0.0.1:1880",
        "127.0.0.1:8090",
        "admin unix//run/boneio-proxy/admin.sock",
        "skip_install_trust",
        "http_port 8091",
        "https_port 8443",
        ":8091 {",
        "redir https://{host}:8443{uri}",
        "root * /usr/share/boneio/proxy",
        'respond `{"available": true}` 200',
        "{err.status_code} >= 502",
    ):
        assert needle in text, needle
    assert "host.docker.internal" not in text
    assert "node-red:1880" not in text
    assert "black.boneio.app" not in text
    assert "\\" not in text


def test_render_cloud(helper):
    text = _render(helper, custom=False, cloud=True)
    assert "*.black.boneio.app {" in text
    assert "tls /run/boneio-proxy/tls/cloud.crt /run/boneio-proxy/tls/cloud.key" in text
    # The catch-all keeps the device's own authority.
    assert "on_demand" in text
    assert "\\" not in text


def test_render_custom(helper):
    text = _render(helper, custom=True, cloud=False)
    assert "tls /run/boneio-proxy/tls/custom.crt /run/boneio-proxy/tls/custom.key" in text
    assert "on_demand" not in text


def test_render_follows_ports(helper):
    text = helper.render(helper.Ports(9000, 81, 9443), custom=False, cloud=False)
    assert "127.0.0.1:9000" in text
    assert ":81 {" in text and "http_port 81" in text
    assert "https://{host}:9443{uri}" in text and "https_port 9443" in text


@pytest.mark.parametrize("custom,cloud", [(False, False), (True, False), (False, True)])
def test_render_never_opens_the_tcp_admin_api(helper, custom, cloud):
    assert "localhost:2019" not in _render(helper, custom=custom, cloud=cloud)


@pytest.mark.skipif(shutil.which("caddy") is None, reason="caddy not installed")
@pytest.mark.parametrize("custom,cloud", [(False, False), (True, False), (False, True)])
def test_caddy_adapts_every_variant(helper, tmp_path, custom, cloud):
    config = tmp_path / "Caddyfile"
    config.write_text(_render(helper, custom=custom, cloud=cloud))
    result = subprocess.run(
        ["caddy", "adapt", "--config", str(config), "--adapter", "caddyfile"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr


# --------------------------------------------------------------------- main


@pytest.fixture
def device(helper, tmp_path, monkeypatch):
    """The paths main() touches, moved under tmp_path."""
    home = tmp_path / "home" / "boneio" / "docker" / "nodered"
    custom = home / "caddy" / "data" / "custom"
    ssl = home / "caddy" / "ssl"
    run = tmp_path / "run" / "boneio-proxy"
    state = tmp_path / "var" / "lib" / "boneio" / "proxy"
    data = tmp_path / "var" / "lib" / "caddy" / "data"
    marker = tmp_path / "etc" / "proxy-cloud"
    for directory in (custom, ssl, run, data / "pki" / "authorities" / "local",
                      data / "certificates" / "local" / "10.0.0.5", marker.parent):
        directory.mkdir(parents=True)
    (data / "pki" / "authorities" / "local" / "root.crt").write_bytes(CERT)
    monkeypatch.setattr(helper, "ENV_FILE", home / ".env")
    monkeypatch.setattr(helper, "CUSTOM_DIR", custom)
    monkeypatch.setattr(helper, "CLOUD_DIR", ssl)
    monkeypatch.setattr(helper, "CLOUD_MARKER", marker)
    monkeypatch.setattr(helper, "RUN_DIR", run)
    monkeypatch.setattr(helper, "STATE_DIR", state)
    monkeypatch.setattr(helper, "CADDY_DATA", data)
    monkeypatch.setattr(helper.socket, "gethostname", lambda: "boneio-new")
    return {"home": home, "custom": custom, "ssl": ssl, "run": run,
            "state": state, "data": data, "marker": marker}


def test_main_writes_config_and_exports_root(helper, device):
    (device["home"] / ".env").write_text("WEB_PORT=9000\n")
    assert helper.main([]) == 0
    caddyfile = device["run"] / "Caddyfile"
    assert "127.0.0.1:9000" in caddyfile.read_text()
    assert caddyfile.stat().st_mode & 0o777 == 0o640
    exported = device["state"] / "root.crt"
    assert exported.read_bytes() == CERT
    assert exported.stat().st_mode & 0o777 == 0o644
    assert (device["state"] / "last_hostname").read_text().strip() == "boneio-new"


@pytest.fixture(scope="module")
def real():
    """Two independent, genuine certificate pairs."""
    ca = make_ca()
    return make_leaf(ca, ("boneio",)), make_leaf(ca, ("x.black.boneio.app",))


def _place(directory, cert, key):
    (directory / "fullchain.pem").write_bytes(cert)
    (directory / "privkey.pem").write_bytes(key)


def test_main_copies_custom_pair(helper, device, real):
    _place(device["custom"], real[0].cert, real[0].key)
    assert helper.main([]) == 0
    tls = device["run"] / "tls"
    assert (tls / "custom.key").read_bytes() == real[0].key
    assert (tls / "custom.key").stat().st_mode & 0o777 == 0o640
    assert f"tls {tls}/custom.crt" in (device["run"] / "Caddyfile").read_text()

    # Removed by the user: the copy goes too, and Caddy is back on its own.
    (device["custom"] / "privkey.pem").unlink()
    assert helper.main([]) == 0
    assert not (tls / "custom.key").exists()
    assert "on_demand" in (device["run"] / "Caddyfile").read_text()


def test_main_cloud_needs_the_marker(helper, device, real):
    _place(device["ssl"], real[1].cert, real[1].key)
    assert helper.main([]) == 0
    assert "black.boneio.app" not in (device["run"] / "Caddyfile").read_text()
    device["marker"].touch()
    assert helper.main([]) == 0
    assert "*.black.boneio.app" in (device["run"] / "Caddyfile").read_text()
    assert (device["run"] / "tls" / "cloud.key").read_bytes() == real[1].key


@pytest.mark.parametrize(
    "broken",
    [
        lambda a, b: (a.cert, b.key),  # crossed: each half is genuine
        lambda a, b: (a.cert[: len(a.cert) // 2], a.key),  # cut off mid-write
        lambda a, b: (a.cert, encrypted_key(a)),  # would need a passphrase
    ],
    ids=["crossed", "truncated", "encrypted"],
)
def test_a_pair_caddy_cannot_load_is_not_served(helper, device, real, broken):
    tls = device["run"] / "tls"
    _place(device["custom"], real[0].cert, real[0].key)
    assert helper.main([]) == 0
    assert (tls / "custom.key").exists()

    _place(device["custom"], *broken(real[0], real[1]))
    assert helper.main([]) == 0
    text = (device["run"] / "Caddyfile").read_text()
    assert "custom.crt" not in text and "on_demand" in text
    assert not (tls / "custom.key").exists()

    device["marker"].touch()
    _place(device["ssl"], *broken(real[1], real[0]))
    assert helper.main([]) == 0
    assert "black.boneio.app" not in (device["run"] / "Caddyfile").read_text()
    assert not (tls / "cloud.key").exists()


def test_main_refuses_a_symlinked_tls_directory(helper, device, tmp_path):
    # /run/boneio-proxy belongs to caddy: a link planted there must not turn
    # root's writes into writes somewhere else.
    target = tmp_path / "etc-somewhere"
    target.mkdir()
    (device["run"] / "tls").symlink_to(target)
    (device["custom"] / "fullchain.pem").write_bytes(CERT)
    (device["custom"] / "privkey.pem").write_bytes(KEY)
    assert helper.main([]) == 1
    assert list(target.iterdir()) == []


def test_hostname_change_forgets_the_local_authority(helper, device):
    device["state"].mkdir(parents=True)
    (device["state"] / "last_hostname").write_text("boneio-old\n")
    (device["state"] / "root.crt").write_bytes(CERT)
    assert helper.main([]) == 0
    assert not (device["data"] / "pki").exists()
    assert not (device["data"] / "certificates" / "local").exists()
    # The root that was offered for download is gone with it.
    assert not (device["state"] / "root.crt").exists()


def test_a_reload_keeps_the_authority_after_a_hostname_change(helper, device):
    # Only a start follows the hostname: a reload (cloud on or off, the
    # switch's export) must not pull the authority from under a running Caddy.
    device["state"].mkdir(parents=True)
    (device["state"] / "last_hostname").write_text("boneio-old\n")
    assert helper.main(["--reload"]) == 0
    assert (device["data"] / "pki").exists()
    assert (device["data"] / "certificates" / "local").exists()
    assert (device["state"] / "last_hostname").read_text() == "boneio-old\n"
    assert (device["state"] / "root.crt").read_bytes() == CERT
    assert (device["run"] / "Caddyfile").exists()


def test_first_run_keeps_the_authority(helper, device):
    # No record means the CA was carried over from the container, not stale.
    assert helper.main([]) == 0
    assert (device["data"] / "pki").exists()
    assert (device["data"] / "certificates" / "local").exists()


def test_same_hostname_keeps_the_authority(helper, device):
    device["state"].mkdir(parents=True)
    (device["state"] / "last_hostname").write_text("boneio-new\n")
    assert helper.main([]) == 0
    assert (device["data"] / "pki").exists()


def test_directories_keep_their_modes_under_the_service_umask(helper, device):
    # caddy.service sets UMask=0077; the exported root must stay reachable.
    previous = os.umask(0o077)
    try:
        assert helper.main([]) == 0
    finally:
        os.umask(previous)
    assert device["state"].stat().st_mode & 0o777 == 0o755
    assert (device["run"] / "tls").stat().st_mode & 0o777 == 0o750


def test_unusable_state_does_not_cost_the_proxy(helper, device):
    # A file where the state directory should be: hostname and export fail,
    # the Caddyfile is still written.
    device["state"].parent.mkdir(parents=True, exist_ok=True)
    device["state"].write_text("not a directory")
    assert helper.main([]) == 0
    assert (device["run"] / "Caddyfile").exists()


# --------------------------------------------------------------- export only


def test_export_root_only_exports(helper, device):
    device["state"].mkdir(parents=True)
    (device["state"] / "last_hostname").write_text("boneio-old\n")
    assert helper.main(["--export-root"]) == 0
    assert helper.main(["--export-root"]) == 0
    exported = device["state"] / "root.crt"
    assert exported.read_bytes() == CERT
    assert exported.stat().st_mode & 0o777 == 0o644
    # Neither the Caddyfile nor the hostname is touched.
    assert not (device["run"] / "Caddyfile").exists()
    assert (device["data"] / "pki").exists()
    assert (device["state"] / "last_hostname").read_text() == "boneio-old\n"


def test_export_root_without_a_root_succeeds_and_says_so(helper, device, monkeypatch, caplog):
    monkeypatch.setattr(helper, "EXPORT_WAIT", 0)
    (device["data"] / "pki" / "authorities" / "local" / "root.crt").unlink()
    caplog.set_level(logging.INFO, logger="boneio-proxy-config")
    assert helper.main(["--export-root"]) == 0
    assert not (device["state"] / "root.crt").exists()
    assert "No root certificate yet" in caplog.text


def test_export_root_never_fails_the_unit(helper, device):
    # A file where the state directory should be.
    device["state"].parent.mkdir(parents=True, exist_ok=True)
    device["state"].write_text("not a directory")
    assert helper.main(["--export-root"]) == 0
