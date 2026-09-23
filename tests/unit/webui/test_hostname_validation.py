"""Tests for the hostname endpoint agreeing with ``boneio-system``.

The endpoint used to accept underscores and capitals, which the helper refuses.
Such a name got past the panel and came back as a 500 carrying the helper's
stderr. The endpoint now applies the helper's rule itself and answers 400.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.webui.routes import system as system_routes

HELPER = (
    Path(system_routes.__file__).parents[2]
    / "migrations" / "assets" / "helpers" / "boneio-system"
)


@pytest.fixture
def calls(monkeypatch) -> list[str]:
    """Names that reached the helper."""
    seen: list[str] = []

    def fake_hostname_set(name: str, timeout: int = 30):
        seen.append(name)
        return SimpleNamespace(ok=True, stderr="")

    monkeypatch.setattr(system_routes.system_ops, "hostname_set", fake_hostname_set)
    return seen


@pytest.fixture
def client() -> TestClient:
    """The system router, with no auth in the way."""
    app = FastAPI()
    app.include_router(system_routes.router)
    return TestClient(app, raise_server_exceptions=False)


def test_the_rule_is_the_helpers_rule():
    """Two copies of one rule are only safe while they stay the same."""
    match = re.search(r'_HOSTNAME_RE = re\.compile\(r"([^"]+)"\)', HELPER.read_text())
    assert match, "boneio-system no longer defines _HOSTNAME_RE"
    assert system_routes._HOSTNAME_RE.pattern == match.group(1)


@pytest.mark.parametrize("name", ["szafa_1", "-front", "back-", "kot.lownia", "a b", "x" * 64])
def test_a_name_the_helper_would_refuse_is_a_400(client, calls, name):
    response = client.post("/api/hostname", json={"hostname": name})
    assert response.status_code == 400
    assert calls == []


def test_capitals_are_lowered_not_refused(client, calls):
    response = client.post("/api/hostname", json={"hostname": "  Kotlownia-2 "})
    assert response.status_code == 200
    assert response.json()["hostname"] == "kotlownia-2"
    assert calls == ["kotlownia-2"]


def test_a_refusal_from_the_helper_is_still_reported(client, monkeypatch):
    """The root side has the final say; its answer must not be swallowed."""
    monkeypatch.setattr(
        system_routes.system_ops,
        "hostname_set",
        lambda name, timeout=30: SimpleNamespace(ok=False, stderr="refused\n"),
    )
    response = client.post("/api/hostname", json={"hostname": "blk1234"})
    assert response.status_code == 500
    assert response.json()["detail"] == "refused"
