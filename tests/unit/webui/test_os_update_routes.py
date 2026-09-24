"""Tests for the operating system update endpoints.

The endpoints only pick a mode; everything apt does is decided in
``boneio-system``. So these are about the modes that reach the helper, about a
device whose helper predates the verbs, and about a second run while one is
still going.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.core.system_ops import Result
from boneio.webui.routes import os_update


@pytest.fixture
def started(monkeypatch) -> list[str]:
    """Modes that reached the helper."""
    seen: list[str] = []

    def fake_start(mode: str, timeout: int = 30) -> Result:
        seen.append(mode)
        return Result(0, json.dumps({"started": mode}), "")

    monkeypatch.setattr(os_update.system_ops, "helper_supports", lambda verb: True)
    monkeypatch.setattr(os_update.system_ops, "os_update_start", fake_start)
    return seen


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(os_update.router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(("path", "mode"), [
    ("/api/os-update/check", "check"),
    ("/api/os-update/upgrade", "upgrade"),
])
def test_each_endpoint_starts_exactly_its_mode(client, started, path, mode):
    response = client.post(path)
    assert response.status_code == 200
    assert started == [mode]


def test_the_body_cannot_choose_the_mode(client, started):
    """There is nothing in a request that reaches apt."""
    client.post("/api/os-update/check", json={"mode": "upgrade", "packages": ["x"]})
    assert started == ["check"]


def test_a_run_in_progress_is_a_conflict(client, monkeypatch):
    monkeypatch.setattr(os_update.system_ops, "helper_supports", lambda verb: True)
    monkeypatch.setattr(
        os_update.system_ops, "os_update_start",
        lambda mode, timeout=30: Result(
            1, "", "[ERROR] REFUSED: an operating system update is already running"
        ),
    )
    assert client.post("/api/os-update/upgrade").status_code == 409


def test_an_old_helper_says_the_migration_is_pending(client, monkeypatch):
    monkeypatch.setattr(os_update.system_ops, "helper_supports", lambda verb: False)
    state = client.get("/api/os-update/state").json()
    assert state["supported"] is False
    assert "1.6.18" in state["message"]
    assert client.post("/api/os-update/upgrade").status_code == 409


def test_the_state_carries_where_the_recovery_images_are(client, monkeypatch):
    monkeypatch.setattr(os_update.system_ops, "helper_supports", lambda verb: True)
    monkeypatch.setattr(
        os_update.system_ops, "os_update_state",
        lambda timeout=30: Result(0, json.dumps({"running": False, "reboot_required": True}), ""),
    )
    state = client.get("/api/os-update/state").json()
    assert state["reboot_required"] is True
    assert state["recovery_images_url"] == "https://github.com/boneIO-eu/black_debian_images"


# ------------------------------------------------- automatic security updates


def test_the_switch_reaches_the_helper_as_on_or_off(client, monkeypatch):
    seen: list[bool] = []
    monkeypatch.setattr(os_update.system_ops, "helper_supports", lambda verb: True)

    def fake(enabled, timeout=60):
        seen.append(enabled)
        return Result(0, json.dumps({"enabled": enabled}), "")

    monkeypatch.setattr(os_update.system_ops, "os_autoupdate_set", fake)
    assert client.post("/api/os-update/autoupdate", json={"enabled": False}).status_code == 200
    assert client.post("/api/os-update/autoupdate", json={"enabled": "maybe"}).status_code == 422
    assert seen == [False]


def test_the_switch_needs_the_migration(client, monkeypatch):
    monkeypatch.setattr(os_update.system_ops, "helper_supports", lambda verb: False)
    response = client.post("/api/os-update/autoupdate", json={"enabled": True})
    assert response.status_code == 409
    assert "1.6.22" in response.json()["detail"]


# ---------------------------------------------------------------------- Caddy


@pytest.fixture
def caddy(monkeypatch):
    applied: list[int] = []
    monkeypatch.setattr(os_update.containers, "helper_supports", lambda verb: True)
    monkeypatch.setattr(
        os_update.containers, "caddy_image_state",
        lambda timeout=30: Result(0, json.dumps(
            {"pinned": "caddy:2.11.4-alpine@sha256:" + "a" * 64,
             "configured": "caddy:2-alpine", "update_available": True}), ""),
    )
    monkeypatch.setattr(
        os_update.containers, "caddy_image_apply",
        lambda timeout=1300: applied.append(1) or Result(0, "", ""),
    )
    monkeypatch.setitem(os_update._caddy_task, "status", "idle")
    return applied


def test_caddy_state_says_an_update_is_available(client, caddy):
    state = client.get("/api/os-update/caddy").json()
    assert state["supported"] is True
    assert state["update_available"] is True


def test_applying_caddy_runs_in_the_background_and_finishes(client, caddy):
    import time as _time

    assert client.post("/api/os-update/caddy/apply").status_code == 200
    for _ in range(50):
        if os_update._caddy_task["status"] != "running":
            break
        _time.sleep(0.02)
    assert os_update._caddy_task["status"] == "success"
    assert caddy == [1]


def test_a_second_caddy_apply_is_a_conflict(client, caddy, monkeypatch):
    monkeypatch.setitem(os_update._caddy_task, "status", "running")
    assert client.post("/api/os-update/caddy/apply").status_code == 409
    assert caddy == []
