"""Tests for the signed migration plans that ship with a release.

The point of signing is that the privileged helper stops trusting anything the
unprivileged process hands it (CVE-2026-77055). These tests guard the two ways
that can quietly fail: a plan on disk drifting from the module it came from, and
a plan being frozen from something this build machine happened to have.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PLANS_DIR = REPO_ROOT / "boneio" / "migrations" / "plans"
PUBKEY = REPO_ROOT / "boneio" / "migrations" / "assets" / "migrations.pem"
GENERATOR = REPO_ROOT / "scripts" / "generate_signed_plans.py"


def _load_generator():
    """Import the release-time generator as a module."""
    spec = importlib.util.spec_from_file_location("generate_signed_plans", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_signed_plans"] = module
    spec.loader.exec_module(module)
    return module


gen = _load_generator()
openssl = shutil.which("openssl")


def _manifest() -> dict:
    return json.loads((PLANS_DIR / "manifest.json").read_bytes())


# ----------------------------------------------------------------- completeness


def test_every_migration_is_either_signed_or_excluded_on_purpose():
    """No migration may fall through the cracks.

    A version with neither a signed plan nor an entry in NON_PORTABLE would
    simply never run under the signing helper, and nothing would say so.
    """
    unaccounted = []
    for version, _module in gen._discover():
        signed = (PLANS_DIR / f"{version}.json").exists()
        excluded = version in gen.NON_PORTABLE
        if not signed and not excluded:
            unaccounted.append(version)
    assert not unaccounted, (
        f"these migrations are neither signed nor listed in NON_PORTABLE: {unaccounted}"
    )


def test_excluded_migrations_carry_a_reason():
    for version, reason in gen.NON_PORTABLE.items():
        assert reason and len(reason) > 30, (
            f"{version} is excluded from signing without explaining why"
        )


def test_excluded_migrations_have_no_stale_plan_on_disk():
    """Removing a migration from the signed set must remove its plan too."""
    for version in gen.NON_PORTABLE:
        assert not (PLANS_DIR / f"{version}.json").exists(), (
            f"{version} is in NON_PORTABLE but a signed plan is still shipped"
        )


# --------------------------------------------------------------------- contents


def test_each_plan_matches_the_module_it_came_from():
    """The frozen plan must still equal what plan() produces.

    This is the check that catches a migration edited without re-running the
    generator — the device would then apply the old, signed behaviour while the
    source says something else.
    """
    drifted = []
    for version, module in gen._discover():
        plan_path = PLANS_DIR / f"{version}.json"
        if not plan_path.exists():
            continue
        expected = gen._canonical([a.to_dict() for a in module.plan()])
        if plan_path.read_bytes() != expected:
            drifted.append(version)
    assert not drifted, (
        f"plans on disk differ from plan() output for {drifted} — "
        "re-run scripts/generate_signed_plans.py"
    )


def test_no_signed_plan_is_empty():
    for plan_path in PLANS_DIR.glob("*.json"):
        if plan_path.name == "manifest.json":
            continue
        assert json.loads(plan_path.read_bytes()), (
            f"{plan_path.name} is an empty plan; it would be a permanent no-op"
        )


def test_plans_are_canonical_json():
    """Byte-for-byte determinism is what makes a signature reproducible."""
    for plan_path in PLANS_DIR.glob("*.json"):
        payload = json.loads(plan_path.read_bytes())
        assert plan_path.read_bytes() == gen._canonical(payload), (
            f"{plan_path.name} is not in canonical form"
        )


# --------------------------------------------------------------------- manifest


def test_manifest_covers_exactly_the_signed_plans():
    on_disk = {
        p.stem for p in PLANS_DIR.glob("*.json") if p.name != "manifest.json"
    }
    assert set(_manifest()["plans"]) == on_disk


def test_manifest_hashes_match_the_plans():
    """The manifest is what stops a validly-signed plan from another release
    being presented for a version this device has not applied."""
    for version, digest in _manifest()["plans"].items():
        data = (PLANS_DIR / f"{version}.json").read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, f"{version}: hash mismatch"


def test_manifest_names_the_release_it_belongs_to():
    from boneio.version import __version__

    assert _manifest()["release"] == __version__


# ------------------------------------------------------------------- signatures


@pytest.mark.skipif(not openssl, reason="openssl not available")
def test_every_plan_signature_verifies():
    for plan_path in PLANS_DIR.glob("*.json"):
        sig = plan_path.with_suffix(".sig")
        assert sig.exists(), f"{plan_path.name} has no signature"
        assert gen._verify(PUBKEY, plan_path.read_bytes(), sig), (
            f"{plan_path.name}: signature does not verify against the shipped key"
        )


@pytest.mark.skipif(not openssl, reason="openssl not available")
def test_a_tampered_plan_fails_verification(tmp_path):
    """The whole mechanism rests on this."""
    plan_path = next(
        p for p in PLANS_DIR.glob("*.json") if p.name != "manifest.json"
    )
    payload = json.loads(plan_path.read_bytes())
    payload.append({"action": "install_file", "dst": "/etc/sudoers.d/zzz"})
    assert not gen._verify(PUBKEY, gen._canonical(payload), plan_path.with_suffix(".sig"))


@pytest.mark.skipif(not openssl, reason="openssl not available")
def test_the_public_key_is_an_ed25519_key():
    out = subprocess.run(
        ["openssl", "pkey", "-pubin", "-in", str(PUBKEY), "-text", "-noout"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "ED25519" in out.upper()


# ---------------------------------------------------------------- trust anchors


@pytest.mark.skipif(not openssl, reason="openssl not available")
def test_both_trust_anchors_ship():
    """A release has to pin two keys, not one.

    Re-pinning needs a migration signed by a key the device already trusts, so
    with a single anchor a lost release key leaves the installed base working
    but unable to ever accept a signed migration again — recoverable only by
    reflashing every controller.
    """
    assert not gen._anchor_problems()


@pytest.mark.skipif(not openssl, reason="openssl not available")
def test_the_two_anchors_are_different_keys():
    """Two names for one key is one anchor."""
    assert gen._key_id(gen.PUBKEY) != gen._key_id(gen.RECOVERY_PUBKEY)


@pytest.mark.skipif(not openssl, reason="openssl not available")
def test_the_recovery_anchor_is_an_ed25519_key():
    out = subprocess.run(
        ["openssl", "pkey", "-pubin", "-in", str(gen.RECOVERY_PUBKEY), "-text",
         "-noout"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "ED25519" in out.upper()


@pytest.mark.skipif(not openssl, reason="openssl not available")
def test_no_private_key_is_committed():
    """The signing keys live outside the repo; only public halves ship."""
    leaked = [
        path
        for path in (REPO_ROOT / "boneio").rglob("*.pem")
        if "PRIVATE KEY" in path.read_text(errors="ignore")
    ]
    assert not leaked, f"private key material committed: {leaked}"


@pytest.mark.skipif(not openssl, reason="openssl not available")
def test_a_missing_recovery_anchor_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(gen, "RECOVERY_PUBKEY", tmp_path / "absent.pem")
    problems = gen._anchor_problems()
    assert any("recovery public key is missing" in p for p in problems)


@pytest.mark.skipif(not openssl, reason="openssl not available")
def test_pointing_both_anchors_at_one_key_is_refused(monkeypatch):
    monkeypatch.setattr(gen, "RECOVERY_PUBKEY", gen.PUBKEY)
    problems = gen._anchor_problems()
    assert any("same key" in p for p in problems)


# ------------------------------------------------------------------ the guards


def test_the_portability_guard_rejects_a_local_path():
    """A plan naming this machine's interpreter would be nonsense on a device."""
    payload = [{"action": "pip_install_wheel", "python": sys.executable}]
    with pytest.raises(gen.NotDeterministic, match="interpreter"):
        gen._assert_portable("9.9.9", payload)


def test_the_portability_guard_rejects_the_build_user():
    import getpass

    payload = [{"action": "pip_install_wheel", "run_as": getpass.getuser()}]
    with pytest.raises(gen.NotDeterministic, match="current user"):
        gen._assert_portable("9.9.9", payload)


def test_the_portability_guard_passes_a_device_agnostic_plan():
    payload = [
        {"action": "remove_file", "path": "/etc/sudoers.d/boneio-setup"},
        {"action": "systemctl_reload", "unit": "ssh"},
    ]
    gen._assert_portable("9.9.9", payload)


def test_the_stability_guard_rejects_a_plan_that_changes_between_calls():
    class Flaky:
        def __init__(self):
            self.n = 0

        def plan(self):
            self.n += 1

            class Action:
                def __init__(self, n):
                    self.n = n

                def to_dict(self):
                    return {"action": "remove_file", "path": f"/tmp/{self.n}"}

            return [Action(self.n)]

    with pytest.raises(gen.NotDeterministic, match="different on each call"):
        gen._assert_stable("9.9.9", Flaky())


def test_canonical_form_is_order_independent():
    a = gen._canonical({"b": 1, "a": 2})
    b = gen._canonical({"a": 2, "b": 1})
    assert a == b
