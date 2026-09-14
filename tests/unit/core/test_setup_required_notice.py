"""Tests for the boot-time 'setup required' notice."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from boneio.core.auth.models import Role
from boneio.core.auth.store import UserStore
from boneio.runner import _warn_if_setup_required


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("web:\n  port: 8090\n", encoding="utf-8")
    return str(path)


def _run(config_file, web_config):
    """Call the notice with the OLED draw captured."""
    with patch("boneio.runner._draw_startup_status") as draw:
        _warn_if_setup_required(object(), config_file, web_config)
    return draw


def test_unprovisioned_device_is_announced(config_file):
    draw = _run(config_file, {"port": 8090})
    draw.assert_called_once()
    assert "SETUP REQUIRED" in draw.call_args.args[1]


def test_port_is_taken_from_the_config(config_file):
    draw = _run(config_file, {"port": 8443})
    assert "8443" in draw.call_args.args[1]


def test_provisioned_device_is_silent(config_file):
    store = UserStore.for_config_file(config_file)
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    draw = _run(config_file, {"port": 8090})
    draw.assert_not_called()


def test_viewer_only_device_still_needs_setup(config_file):
    """A viewer is not an owner, so the device is still unmanageable."""
    store = UserStore.for_config_file(config_file)
    store.add_user("gosc", "haslo-goscia", Role.VIEWER)
    draw = _run(config_file, {"port": 8090})
    draw.assert_called_once()


def test_explicit_opt_out_is_silent(config_file):
    """Someone who deliberately set allow_anonymous does not need nagging here;
    init_app already logs a standing warning for that state."""
    draw = _run(config_file, {"port": 8090, "auth": {"allow_anonymous": True}})
    draw.assert_not_called()


def test_a_broken_store_never_blocks_boot(tmp_path):
    """A notice must not be able to stop the controller from starting."""
    broken = tmp_path / "config.yaml"
    broken.write_text("web:\n", encoding="utf-8")
    (tmp_path / "users.json").write_text("{ not json", encoding="utf-8")

    with patch("boneio.runner._draw_startup_status") as draw:
        _warn_if_setup_required(object(), str(broken), {"port": 8090})
    draw.assert_not_called()


def test_missing_display_is_fine(config_file):
    """Controllers without an OLED must not trip over this."""
    with patch("boneio.runner._draw_startup_status") as draw:
        _warn_if_setup_required(None, config_file, {"port": 8090})
    draw.assert_called_once()
