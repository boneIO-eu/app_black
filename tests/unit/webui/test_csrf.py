"""Tests for the cross-site request guard (F-07)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.webui.middleware.csrf import CSRFMiddleware


def _client(allowed=None):
    app = FastAPI()

    @app.post("/api/reboot")
    async def reboot():
        return {"rebooting": True}

    @app.get("/api/outputs")
    async def outputs():
        return {"outputs": []}

    @app.post("/not-api")
    async def not_api():
        return {"ok": True}

    app.add_middleware(CSRFMiddleware, allowed_origins=allowed or [])
    return TestClient(app)


@pytest.fixture
def client():
    return _client()


DEVICE = "testserver"


# ------------------------------------------------------------ the report's PoC


def test_a_form_post_from_another_site_is_refused(client):
    """The report's proof: a page on another site submits to /api/reboot."""
    response = client.post(
        "/api/reboot",
        headers={"Origin": "https://evil.example", "Content-Type": "text/plain"},
        content="x=1",
    )
    assert response.status_code == 403
    assert response.json()["code"] == "cross_site_request"


def test_the_backup_call_from_the_report_is_refused(client):
    assert client.post(
        "/api/reboot", headers={"Origin": "https://evil.example"}
    ).status_code == 403


# ---------------------------------------------------------- what must still work


def test_the_panel_itself_is_not_affected(client):
    """Same-origin requests are the normal case and must pass untouched."""
    assert client.post(
        "/api/reboot", headers={"Origin": f"http://{DEVICE}"}
    ).status_code == 200


def test_a_request_with_no_origin_passes(client):
    """curl, a script, another service. None of them can be tricked into
    acting on somebody else's behalf, which is what CSRF is."""
    assert client.post("/api/reboot").status_code == 200


def test_reads_are_never_judged(client):
    assert client.get(
        "/api/outputs", headers={"Origin": "https://evil.example"}
    ).status_code == 200


def test_the_dev_server_is_allowed_when_cors_allows_it():
    """Blocking it would break working on the frontend against a real device."""
    client = _client(["http://localhost:5173"])
    assert client.post(
        "/api/reboot", headers={"Origin": "http://localhost:5173"}
    ).status_code == 200


def test_an_origin_outside_the_cors_list_is_still_refused():
    client = _client(["http://localhost:5173"])
    assert client.post(
        "/api/reboot", headers={"Origin": "http://localhost:9999"}
    ).status_code == 403


def test_non_api_paths_are_left_alone(client):
    assert client.post(
        "/not-api", headers={"Origin": "https://evil.example"}
    ).status_code == 200


# ------------------------------------------------------------------- parsing


@pytest.mark.parametrize(
    "origin",
    ["https://evil.example", "http://evil.example", "https://evil.example:8443", "null"],
)
def test_foreign_origins_in_any_shape_are_refused(client, origin):
    assert client.post("/api/reboot", headers={"Origin": origin}).status_code == 403


def test_a_port_difference_is_a_different_origin(client):
    """testserver:9999 is not testserver."""
    assert client.post(
        "/api/reboot", headers={"Origin": f"http://{DEVICE}:9999"}
    ).status_code == 403


def test_origin_case_does_not_matter(client):
    assert client.post(
        "/api/reboot", headers={"Origin": f"http://{DEVICE.upper()}"}
    ).status_code == 200


def test_a_prefix_of_the_host_is_not_the_host(client):
    """evil-testserver.example must not pass because it ends in the host."""
    assert client.post(
        "/api/reboot", headers={"Origin": "http://evil-testserver.example"}
    ).status_code == 403
