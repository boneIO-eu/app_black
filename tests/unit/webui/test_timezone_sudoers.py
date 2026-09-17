"""Tests for taking the sudo password out of the timezone flow.

The rule that lets boneIO run ``timedatectl set-timezone`` used to be created by
an endpoint that accepted the operator's sudo password over HTTP. The password
for that account is shared across controllers, so an endpoint collecting it is a
way to intercept it — the rule now arrives with a system migration instead.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.webui.routes import system as system_routes
from boneio.webui.routes.timezone_sudoers import (
    SUDOERS_ASSET,
    get_sudoers_content,
)


@pytest.fixture
def client() -> TestClient:
    """The system router, with no auth in the way."""
    app = FastAPI()
    app.include_router(system_routes.router, prefix="/api")
    return TestClient(app, raise_server_exceptions=False)


# ------------------------------------------------------------- the endpoint


def test_the_password_endpoint_is_gone(client):
    """It took a sudo password over HTTP to write a sudoers file."""
    response = client.post("/api/timezone/sudoers/fix", json={"password": "hunter2"})
    assert response.status_code in (404, 405)


def test_no_route_accepts_a_sudo_password_for_timezone(client):
    """A renamed endpoint would defeat the point of removing this one."""
    paths = [route.path for route in client.app.routes]
    assert not [p for p in paths if "sudoers" in p and "fix" in p]


def test_the_read_only_check_is_still_there():
    """Removing the fix must not take away the ability to see the state."""
    paths = [route.path for route in system_routes.router.routes]
    assert "/api/timezone/sudoers/check" in paths


def test_the_request_model_is_gone():
    assert not hasattr(system_routes, "TimezoneSudoersFixRequest")


def test_the_function_that_took_the_password_is_gone():
    import boneio.webui.routes.timezone_sudoers as module

    assert not hasattr(module, "create_timedatectl_sudoers_file")


# ------------------------------------------------------- one source of truth


def test_the_expected_rule_comes_from_the_shipped_asset():
    """A second copy in the module drifted from the asset once already.

    The module said ``ALL=(ALL)`` while the asset said the narrower
    ``ALL=(root)``, which would have made the check report a mismatch on a
    correctly configured controller.
    """
    assert SUDOERS_ASSET.is_file()
    shipped = [
        line.rstrip()
        for line in SUDOERS_ASSET.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert get_sudoers_content().strip().splitlines() == shipped


def test_the_rule_names_the_service_account_not_the_logged_in_user(monkeypatch):
    """It used to read $USER, so the expected content depended on who was in."""
    monkeypatch.setenv("USER", "somebody-else")
    assert "somebody-else" not in get_sudoers_content()
    assert get_sudoers_content().startswith("boneio ")


def test_the_rule_only_grants_the_two_timedatectl_verbs():
    for line in get_sudoers_content().strip().splitlines():
        assert line.startswith("boneio ALL=(root) NOPASSWD: /usr/bin/timedatectl ")
        assert " set-timezone " in line or " set-ntp " in line


# ------------------------------------------------------- timezone validation


@pytest.mark.parametrize("tz", ["Europe/Warsaw", "UTC"])
def test_a_real_timezone_is_accepted(tz):
    assert system_routes._is_known_timezone(tz) is True


@pytest.mark.parametrize("tz", [
    "../../etc/passwd",
    "../../../etc/shadow",
    "Europe/../../etc/hostname",
    "Nope/Nope",
    "",
])
def test_a_name_that_walks_out_of_zoneinfo_is_rejected(tz):
    """The old check was os.path.isfile(f"/usr/share/zoneinfo/{tz}").

    That passes for "../../etc/passwd", because it resolves to a file that
    exists. timedatectl rejects such a name itself, so it was not an
    escalation — but a check that can be walked out of its own directory is
    not a check.
    """
    assert system_routes._is_known_timezone(tz) is False


def test_the_filesystem_fallback_also_refuses_traversal(monkeypatch):
    """When tzdata is unavailable the fallback must not be the old bug."""
    import builtins

    real_import = builtins.__import__

    def _no_zoneinfo(name, *args, **kwargs):
        if name == "zoneinfo":
            raise ImportError("no tzdata")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_zoneinfo)
    assert system_routes._is_known_timezone("../../etc/passwd") is False


# ----------------------------------------------------------- the migration


def test_the_migration_installs_the_rule_with_validation():
    from boneio.migrations.versions.v1_6_7_timedatectl_sudoers import VERSION, plan

    assert VERSION == "1.6.7"
    actions = [action.to_dict() for action in plan()]
    assert len(actions) == 1
    action = actions[0]
    assert action["dst"] == "/etc/sudoers.d/boneio-timedatectl"
    assert action["mode"] == 0o440
    assert action["owner"] == "root"
    # A bad fragment can lock out every privileged operation, so both helpers
    # have to be able to validate it before it moves into place.
    assert action["validate"] == "sudoers"
    assert action["validate_cmd"] == "visudo -cf"


# ------------------------------------------- the endpoint that undid the fix


def test_the_endpoint_that_chowned_the_compose_file_is_gone(client):
    """It handed docker-compose.yaml back to the logged-in user.

    Migration 1.6.5 makes that file root-owned precisely because it is what
    `docker compose up` executes. An endpoint that chowns it back on request
    reopens F-04, so it cannot stay however convenient it was.
    """
    response = client.post("/api/cloud/fix-permissions", json={"password": "hunter2"})
    assert response.status_code in (404, 405)


def test_the_compose_diagnostic_still_reports_the_state(client):
    """Removing the fix must not remove the ability to see the problem."""
    paths = [route.path for route in system_routes.router.routes]
    assert "/api/cloud/test-permissions" in paths


def test_nothing_in_the_system_routes_chowns_the_compose_file():
    import inspect

    source = inspect.getsource(system_routes)
    assert '"chown"' not in source, "the compose file is chowned again somewhere"


def test_the_ui_no_longer_advises_chowning_it_back():
    """The old message told the operator to run `sudo chown $USER` on it."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "frontend" / "src" / "locales"
    for locale in ("en", "pl"):
        text = (root / locale / "common.json").read_text(encoding="utf-8")
        strings = json.loads(text)
        blob = json.dumps(strings, ensure_ascii=False)
        assert "chown $USER" not in blob, f"{locale} still advises chowning it back"
