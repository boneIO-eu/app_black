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
