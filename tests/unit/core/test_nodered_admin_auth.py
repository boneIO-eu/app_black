"""The shipped Node-RED settings must actually require authentication (F-01)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from boneio.migrations.versions import v1_6_0_nodered_admin_auth as migration

REPO_ROOT = Path(__file__).resolve().parents[3]
ASSET = REPO_ROOT / "boneio/migrations/assets/docker/nodered/node-red/settings.js"
REFERENCE = REPO_ROOT / "docker/nodered/node-red/settings.js"


@pytest.fixture(scope="module")
def shipped() -> str:
    return ASSET.read_text(encoding="utf-8")


# ----------------------------------------------------------- what ships


def test_the_shipped_settings_require_authentication(shipped):
    """Without adminAuth the admin API answers anyone who reaches the device,
    and deploying a flow with an exec node is remote code execution."""
    assert "adminAuth" in shipped


def test_anonymous_access_is_not_granted(shipped):
    """Node-RED's `default` user is what would hand the editor to a stranger."""
    assert "default:" not in shipped


def test_only_admins_are_admitted(shipped):
    assert 'role !== "admin"' in shipped


def test_authentication_is_delegated_to_boneio(shipped):
    """One account list, and no second copy of the password hashing."""
    assert "/api/login" in shipped


def test_it_fails_closed(shipped):
    """An auth source that cannot be consulted must not be assumed to agree."""
    assert "return null" in shipped


# ------------------------------------------------- the copy that ships wins


def test_the_reference_copy_matches_the_one_that_ships():
    """Devices are only ever given the file under migrations/assets. Editing
    the copy under docker/ and stopping there leaves every controller in the
    field on the old, unauthenticated settings — which is exactly what happened
    while this was being written."""
    asset = hashlib.sha256(ASSET.read_bytes()).hexdigest()
    reference = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    assert asset == reference, (
        "docker/nodered/node-red/settings.js and its copy under "
        "boneio/migrations/assets/ have diverged; devices receive the asset."
    )


def test_the_manifest_records_the_shipped_file():
    """The manifest is what the installer verifies against."""
    manifest = (REPO_ROOT / "boneio/migrations/assets/MANIFEST.sha256").read_text(
        encoding="utf-8"
    )
    digest = hashlib.sha256(ASSET.read_bytes()).hexdigest()
    assert f"{digest}  docker/nodered/node-red/settings.js" in manifest


# ------------------------------------------------------------- the migration


def test_the_migration_installs_the_settings():
    """The file is otherwise only written by the 1.3.0 baseline, so without
    this migration an existing controller keeps the open editor."""
    targets = [action for action in migration.plan() if hasattr(action, "src")]
    assert any(
        action.src == "docker/nodered/node-red/settings.js"
        and action.dst.endswith("/docker/nodered/node-red/settings.js")
        for action in targets
    )


def test_the_migration_leaves_the_compose_file_alone():
    """Cloud registration edits docker-compose.yaml; replacing it to carry one
    optional variable would put those edits at risk for no real gain."""
    touched = [getattr(action, "dst", "") for action in migration.plan()]
    assert not any("docker-compose" in dst for dst in touched)


def test_the_migration_is_numbered_for_this_release():
    assert migration.VERSION == "1.6.0"


# ------------------------------------------------------- the nginx leftover


def test_the_baseline_no_longer_installs_nginx():
    """nginx was replaced by Caddy in 1.4.4, which deletes the file — so the
    baseline was creating something purely for a later migration to remove."""
    from boneio.migrations.versions import v1_3_0_baseline

    sources = [getattr(a, "src", "") for a in v1_3_0_baseline.plan()]
    assert not any("nginx" in src for src in sources)


def test_the_caddy_migration_still_removes_nginx():
    """A controller set up before 1.4.4 still has the file and must lose it;
    RemoveFile is a no-op on the ones that never had it."""
    from boneio.migrations.versions import v1_4_4_caddy

    removed = [getattr(a, "path", "") for a in v1_4_4_caddy.plan()]
    assert any("nginx/default.conf" in path for path in removed)


def test_the_nginx_asset_is_gone():
    assert not (
        REPO_ROOT / "boneio/migrations/assets/docker/nodered/nginx"
    ).exists()


def test_every_installed_asset_exists_on_disk():
    """A migration naming an asset that was deleted would fail on the device,
    not here — so check the whole set."""
    import importlib
    import pkgutil

    from boneio.migrations import versions

    assets = REPO_ROOT / "boneio/migrations/assets"
    missing = []
    for module in pkgutil.iter_modules(versions.__path__):
        plan = importlib.import_module(
            f"boneio.migrations.versions.{module.name}"
        ).plan()
        for action in plan:
            src = getattr(action, "src", None)
            if src and not (assets / src).exists():
                missing.append(f"{module.name}: {src}")
    assert not missing, f"migrations reference missing assets: {missing}"
