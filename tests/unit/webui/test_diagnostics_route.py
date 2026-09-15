"""The diagnostics endpoints.

The capture window is the part with teeth: a device left at DEBUG logs roughly
twenty MQTT publishes a second, so a window that fails to close fills the
journal and evicts the history someone will want tomorrow.
"""

from __future__ import annotations

import logging

import pytest

from boneio.core.auth.models import Role
from boneio.webui.middleware import policy
from boneio.webui.routes import diagnostics as route


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """Reset the module globals and put the log level back after each test."""
    level = logging.getLogger().level
    monkeypatch.setattr(route, "_capture_started", None)
    monkeypatch.setattr(route, "_capture_until", None)
    monkeypatch.setattr(route, "_previous_level", None)
    monkeypatch.setattr(route, "_revert_task", None)
    yield
    task = route._revert_task
    if task is not None and not task.done():
        task.cancel()
    logging.getLogger().setLevel(level)


class _State:
    def __init__(self, config_file):
        self.yaml_config_file = str(config_file)
        self.manager = None
        self.config_helper = None


@pytest.fixture
def device(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("boneio:\n  name: Test\nmqtt:\n  host: localhost\n  password: p\n", encoding="utf-8")
    route.set_app_state(_State(path))
    return path


# ------------------------------------------------------------ capture window


async def test_no_window_is_open_to_begin_with():
    assert await route.get_capture() == {"active": False, "seconds_remaining": 0, "started": None}


async def test_opening_a_window_raises_the_level():
    logging.getLogger().setLevel(logging.INFO)
    state = await route.start_capture(route.CaptureRequest(minutes=5))

    assert state["active"] is True
    assert 0 < state["seconds_remaining"] <= 300
    assert logging.getLogger().level == logging.DEBUG


async def test_the_window_closes_itself():
    """The whole point: nobody has to remember to turn it off."""
    logging.getLogger().setLevel(logging.WARNING)
    await route.start_capture(route.CaptureRequest(minutes=1))
    assert logging.getLogger().level == logging.DEBUG

    # Run the revert now instead of waiting a minute for it.
    route._revert_task.cancel()
    route._restore_level()

    assert logging.getLogger().level == logging.WARNING
    assert (await route.get_capture())["active"] is False


async def test_extending_a_window_does_not_forget_the_original_level():
    """Re-opening while DEBUG is live must not record DEBUG as 'before'."""
    logging.getLogger().setLevel(logging.INFO)
    await route.start_capture(route.CaptureRequest(minutes=5))
    await route.start_capture(route.CaptureRequest(minutes=5))

    await route.stop_capture()
    assert logging.getLogger().level == logging.INFO


async def test_closing_early_restores_immediately():
    logging.getLogger().setLevel(logging.INFO)
    await route.start_capture(route.CaptureRequest(minutes=30))
    state = await route.stop_capture()

    assert state["active"] is False
    assert logging.getLogger().level == logging.INFO


async def test_closing_a_window_that_was_never_open_is_harmless():
    logging.getLogger().setLevel(logging.INFO)
    assert (await route.stop_capture())["active"] is False
    assert logging.getLogger().level == logging.INFO


@pytest.mark.parametrize("minutes", [0, -1, route.MAX_CAPTURE_MINUTES + 1])
async def test_the_window_length_is_bounded(minutes):
    """An unbounded window is the same as forgetting to close one."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        route.CaptureRequest(minutes=minutes)


async def test_a_stale_window_reports_itself_closed(monkeypatch):
    """If the revert task were lost, the state must not still claim to be open."""
    monkeypatch.setattr(route, "_capture_until", 1.0)  # long past
    monkeypatch.setattr(route, "_capture_started", 0.0)
    assert (await route.get_capture())["active"] is False


# -------------------------------------------------------------------- bundle


async def test_the_bundle_downloads_as_a_file(device):
    response = await route.get_bundle()

    assert response.media_type == "application/gzip"
    assert "attachment" in response.headers["content-disposition"]
    assert ".tar.gz" in response.headers["content-disposition"]
    assert response.body[:2] == b"\x1f\x8b"  # gzip magic


async def test_the_bundle_is_produced_even_with_an_unreadable_config(tmp_path):
    route.set_app_state(_State(tmp_path / "missing.yaml"))
    response = await route.get_bundle()
    assert response.body[:2] == b"\x1f\x8b"


async def test_no_configuration_at_all_is_an_honest_error():
    route.set_app_state(_State(""))
    with pytest.raises(Exception) as err:
        await route.get_bundle()
    assert getattr(err.value, "status_code", None) == 503


# -------------------------------------------------------------------- access


def test_diagnostics_are_admin_only():
    """The bundle is the whole configuration and the device log in one file."""
    for method, path in (
        ("GET", "/api/diagnostics/bundle"),
        ("GET", "/api/diagnostics/capture"),
        ("POST", "/api/diagnostics/capture"),
        ("DELETE", "/api/diagnostics/capture"),
    ):
        assert policy.required_role(method, path) is Role.ADMIN, f"{method} {path}"
        assert not policy.role_allows(Role.VIEWER, method, path)


def test_diagnostics_need_a_token():
    assert not policy.is_exempt("/api/diagnostics/bundle")
