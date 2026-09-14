"""Tests for the response security headers (F-13)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.webui.security_headers import (
    HSTS_MAX_AGE,
    apply_security_headers,
    build_csp,
)


def _app(frame_ancestors=None):
    app = FastAPI()

    @app.get("/api/anything")
    async def anything():
        return {"ok": True}

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        apply_security_headers(request, response, frame_ancestors)
        return response

    return TestClient(app)


@pytest.fixture
def client():
    return _app()


def _headers(client, **kw):
    return client.get("/api/anything", **kw).headers


# ------------------------------------------------------------------ the set


def test_the_headers_the_pentest_asked_for_are_present(client):
    headers = _headers(client)
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "same-origin"
    assert "Content-Security-Policy" in headers
    assert "Permissions-Policy" in headers


def test_x_frame_options_stays_absent(client):
    """It cannot name an allowed origin, so it could not express the Home
    Assistant ingress case. Framing is handled by CSP frame-ancestors."""
    assert "X-Frame-Options" not in _headers(client)


def test_permissions_policy_denies_hardware_the_panel_never_uses(client):
    policy = _headers(client)["Permissions-Policy"]
    for feature in ("camera", "microphone", "geolocation", "usb", "payment"):
        assert f"{feature}=()" in policy


# -------------------------------------------------------------------- CSP


def test_csp_locks_down_what_costs_nothing_to_lock_down():
    csp = build_csp()
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "form-action 'self'" in csp


def test_csp_still_allows_what_the_panel_needs():
    """A policy that breaks the YAML editor is a policy that gets turned off."""
    csp = build_csp()
    # Monaco runs its workers from blob: URLs.
    assert "worker-src 'self' blob:" in csp
    # The WebSocket carries every state update.
    assert "connect-src 'self' ws: wss:" in csp
    # A reverse proxy injects the base path as an inline script.
    assert "'unsafe-inline'" in csp


def test_frame_ancestors_is_omitted_by_default():
    """Turning it on blindly would break whatever embeds the panel today."""
    assert "frame-ancestors" not in build_csp()


def test_frame_ancestors_is_included_when_configured():
    assert "frame-ancestors 'self'" in build_csp("'self'")


def test_frame_ancestors_reaches_the_response():
    headers = _headers(_app("'self' https://ha.local:8123"))
    assert "frame-ancestors 'self' https://ha.local:8123" in headers["Content-Security-Policy"]


# ------------------------------------------------------------------- HSTS


def test_no_hsts_over_plain_http(client):
    """Pinning HTTPS from an HTTP response would be meaningless anyway."""
    assert "Strict-Transport-Security" not in _headers(client)


def test_hsts_when_a_proxy_reports_https(client):
    headers = _headers(client, headers={"X-Forwarded-Proto": "https"})
    assert headers["Strict-Transport-Security"] == f"max-age={HSTS_MAX_AGE}"


def test_hsts_honours_only_the_first_forwarded_proto(client):
    headers = _headers(client, headers={"X-Forwarded-Proto": "https, http"})
    assert "Strict-Transport-Security" in headers


def test_hsts_max_age_is_short_enough_to_recover_from():
    """A device can lose its real certificate — cloud registration switched
    off — and fall back to self-signed on the same hostname. A year-long pin
    would leave the owner unable to click through; a day expires."""
    assert HSTS_MAX_AGE <= 86400
