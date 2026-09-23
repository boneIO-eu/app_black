"""Recovery mode's panel: who gets in, and what it will touch."""

from __future__ import annotations

import io
import tarfile

import pytest
from fastapi.testclient import TestClient

from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.core.recovery import RecoveryReason
from boneio.webui.middleware.auth import create_token, set_auth_config, set_user_store
from boneio.webui.rate_limit import login_rate_limiter
from boneio.webui.recovery.app import RecoveryState, build_app

SECRET = "test-secret-for-recovery-tests----------"
BROKEN = "boneio:\n  name: x\nweb:\n  port: 8090\noutput:\n  - id: a\n   pin: 1\n"


@pytest.fixture(autouse=True)
def _clean_limiter():
    login_rate_limiter._failures.clear()
    yield
    login_rate_limiter._failures.clear()


@pytest.fixture
def config_dir(tmp_path):
    (tmp_path / "config.yaml").write_text(BROKEN)
    (tmp_path / "mqtt.yaml").write_text("host: 127.0.0.1\npassword: !secret mqtt_password\n")
    (tmp_path / "secrets.yaml").write_text("mqtt_password: Tajne-Haslo-99\n")
    (tmp_path / "backups").mkdir()
    return tmp_path


@pytest.fixture
def store(config_dir):
    store = UserStore(config_dir / USERS_FILENAME)
    store.load()
    store.add_user("pawel", "haslo-admina", Role.ADMIN)
    store.add_user("gosc", "poufne-haslo", Role.VIEWER)
    yield store
    set_user_store(None)


@pytest.fixture
def restarts():
    return []


@pytest.fixture
def client(config_dir, store, restarts):
    # A legacy web.auth pair or allow_anonymous from a previous test must not
    # open anything here.
    set_auth_config({})
    state = RecoveryState(
        config_file=str(config_dir / "config.yaml"),
        reason=RecoveryReason(kind="config", message="bad yaml", file=str(config_dir / "config.yaml"), line=7),
        on_restart=lambda: restarts.append(True),
        can_restart=True,
    )
    return TestClient(build_app(state, jwt_secret=SECRET, user_store=store))


def _as(user: str, role: str) -> dict:
    return {"Authorization": f"Bearer {create_token({'sub': user, 'role': role})}"}


def admin():
    return _as("pawel", "admin")


def viewer():
    return _as("gosc", "viewer")


RECOVERY_ROUTES = [
    ("get", "/api/recovery/status", None),
    ("get", "/api/recovery/files", None),
    ("get", "/api/recovery/file?path=config.yaml", None),
    ("put", "/api/recovery/file", {"path": "config.yaml", "content": "boneio: {}\n"}),
    ("post", "/api/recovery/validate", None),
    ("get", "/api/recovery/logs", None),
    ("get", "/api/recovery/backups", None),
    ("post", "/api/recovery/backups/restore", {"filename": "config_backup_x.tar.gz"}),
    ("post", "/api/recovery/restart", None),
]


# ------------------------------------------------------------------ access


@pytest.mark.parametrize(("method", "path", "body"), RECOVERY_ROUTES)
def test_anonymous_gets_nothing(client, method, path, body):
    response = getattr(client, method)(path, **({"json": body} if body else {}))
    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), RECOVERY_ROUTES)
def test_viewer_gets_nothing(client, config_dir, restarts, method, path, body):
    response = getattr(client, method)(path, headers=viewer(), **({"json": body} if body else {}))
    assert response.status_code == 403
    assert restarts == []
    assert (config_dir / "config.yaml").read_text() == BROKEN


def test_token_of_a_deleted_account_is_refused(client, store):
    token = admin()
    store.delete_user("gosc")  # keep one admin; delete the viewer, then fake a token for it
    assert client.get("/api/recovery/status", headers=_as("gosc", "admin")).status_code == 401
    assert client.get("/api/recovery/status", headers=token).status_code == 200


def test_forged_role_claim_does_not_promote_a_viewer(client):
    # The role comes from users.json, not from what the token says.
    assert client.get("/api/recovery/status", headers=_as("gosc", "admin")).status_code == 403


def test_login_issues_a_token_that_works(client):
    r = client.post("/api/login", json={"username": "pawel", "password": "haslo-admina"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert client.get("/api/recovery/status", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_login_rejects_a_wrong_password(client):
    r = client.post("/api/login", json={"username": "pawel", "password": "zle"})
    assert r.status_code == 401


def test_status_carries_the_reason(client):
    body = client.get("/api/recovery/status", headers=admin()).json()
    assert body["reason"]["kind"] == "config"
    assert body["reason"]["line"] == 7


def test_cross_site_write_is_refused(client, restarts):
    r = client.post("/api/recovery/restart", headers={**admin(), "Origin": "http://evil.example"})
    assert r.status_code == 403
    assert restarts == []


# ------------------------------------------------------------------- files


def test_files_list_leaves_out_secrets(client):
    paths = [f["path"] for f in client.get("/api/recovery/files", headers=admin()).json()["files"]]
    assert paths[0] == "config.yaml"
    assert "mqtt.yaml" in paths
    assert "secrets.yaml" not in paths


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("../../etc/passwd", 403),
        ("/etc/passwd", 403),
        ("secrets.yaml", 403),
        ("users.json", 403),
        ("jwt_secret", 403),
        ("notes.txt", 400),
    ],
)
def test_files_outside_the_config_are_out_of_reach(client, path, status):
    assert client.get("/api/recovery/file", params={"path": path}, headers=admin()).status_code == status
    r = client.put("/api/recovery/file", json={"path": path, "content": "x"}, headers=admin())
    assert r.status_code == status


def test_save_replaces_the_file_and_keeps_its_mode(client, config_dir):
    target = config_dir / "mqtt.yaml"
    target.chmod(0o600)
    r = client.put("/api/recovery/file", json={"path": "mqtt.yaml", "content": "host: 10.0.0.1\n"}, headers=admin())
    assert r.status_code == 200
    assert target.read_text() == "host: 10.0.0.1\n"
    assert target.stat().st_mode & 0o777 == 0o600


def test_save_does_not_create_files(client, config_dir):
    r = client.put("/api/recovery/file", json={"path": "new.yaml", "content": "a: 1\n"}, headers=admin())
    assert r.status_code == 404
    assert not (config_dir / "new.yaml").exists()


# ---------------------------------------------------------------- restart


def test_admin_may_ask_to_leave_recovery(client):
    # The callback itself is scheduled after the response, on the server loop.
    assert client.post("/api/recovery/restart", headers=admin()).status_code == 200


# ---------------------------------------------------------------- backups


def _backup(config_dir, name, files):
    path = config_dir / "backups" / name
    with tarfile.open(path, "w:gz") as tar:
        for arcname, data in files.items():
            info = tarfile.TarInfo(arcname)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def test_restore_puts_yaml_back_and_archives_the_current_config(client, config_dir):
    _backup(config_dir, "config_backup_v1_20260101_000000.tar.gz", {"config.yaml": b"boneio: {}\n"})
    r = client.post(
        "/api/recovery/backups/restore",
        json={"filename": "config_backup_v1_20260101_000000.tar.gz"},
        headers=admin(),
    )
    assert r.status_code == 200, r.text
    assert (config_dir / "config.yaml").read_text() == "boneio: {}\n"
    snapshot = config_dir / "backups" / r.json()["snapshot"]
    with tarfile.open(snapshot) as tar:
        assert tar.extractfile("config.yaml").read().decode() == BROKEN


def test_restore_ignores_members_that_escape_or_are_not_yaml(client, config_dir):
    _backup(
        config_dir,
        "config_backup_evil_20260101_000000.tar.gz",
        {"../escape.yaml": b"x: 1\n", "users.json": b"{}", "run.sh": b"echo", "ok.yaml": b"a: 1\n"},
    )
    r = client.post(
        "/api/recovery/backups/restore",
        json={"filename": "config_backup_evil_20260101_000000.tar.gz"},
        headers=admin(),
    )
    assert r.json()["restored"] == ["ok.yaml"]
    assert not (config_dir.parent / "escape.yaml").exists()
    assert not (config_dir / "run.sh").exists()


@pytest.mark.parametrize("name", ["../config.yaml", "config.yaml", "config_backup_x.zip"])
def test_restore_only_takes_a_backup_from_the_backup_dir(client, name):
    r = client.post("/api/recovery/backups/restore", json={"filename": name}, headers=admin())
    assert r.status_code == 400


# -------------------------------------------------------------------- logs


def test_logs_have_secrets_scrubbed(client, monkeypatch):
    from boneio.models.logs import LogEntry
    from boneio.webui.services import logs as log_service

    monkeypatch.setattr(log_service, "is_running_as_service", lambda: False)
    monkeypatch.setattr(
        log_service,
        "get_standalone_logs",
        lambda limit: ([LogEntry(timestamp="1", message="connect with Tajne-Haslo-99", level="ERROR")], False),
    )
    body = client.get("/api/recovery/logs", headers=admin()).json()
    assert "Tajne-Haslo-99" not in body["logs"][0]["message"]


# ------------------------------------------------------------------- page


def test_page_is_served_without_a_token(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "recovery.js" in r.text
    assert client.get("/recovery.js").status_code == 200


def test_logs_scrub_a_plain_password_from_an_include_that_still_loads(client, config_dir, monkeypatch):
    # How shipped controllers keep it: mqtt.yaml with the password in the clear,
    # while config.yaml - the file that includes it - is the broken one.
    from boneio.models.logs import LogEntry
    from boneio.webui.services import logs as log_service

    (config_dir / "mqtt.yaml").write_text("host: 127.0.0.1\nusername: boneio\npassword: Jawne-Haslo-42\n")
    monkeypatch.setattr(log_service, "is_running_as_service", lambda: False)
    monkeypatch.setattr(
        log_service,
        "get_standalone_logs",
        lambda limit: ([LogEntry(timestamp="1", message="auth Jawne-Haslo-42 refused", level="ERROR")], False),
    )
    body = client.get("/api/recovery/logs", headers=admin()).json()
    assert "Jawne-Haslo-42" not in body["logs"][0]["message"]
