"""Tests for boneio-migrate-v2, the privileged migration helper.

The helper is the thing standing between the ``boneio`` account and root, so
these tests are mostly about what it *refuses*. Each one drives ``main()`` end
to end against a throwaway package tree with real Ed25519 signatures, because
the interesting failures live in the interaction between the manifest, the plan
digest and the signature — not in any one function.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER = REPO_ROOT / "boneio" / "migrations" / "assets" / "helpers" / "boneio-migrate-v2"

openssl = shutil.which("openssl")
pytestmark = pytest.mark.skipif(not openssl, reason="openssl not available")


@pytest.fixture(scope="module")
def helper():
    """The helper loaded as a module (it has no .py extension)."""
    return SourceFileLoader("boneio_migrate_v2", str(HELPER)).load_module()


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _genkey(path: Path) -> Path:
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(path)],
        check=True, capture_output=True,
    )
    return path


def _pubkey(private: Path, out: Path) -> Path:
    subprocess.run(
        ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(out)],
        check=True, capture_output=True,
    )
    return out


def _sign(private: Path, data: bytes, out: Path) -> None:
    data_file = out.with_suffix(".data")
    data_file.write_bytes(data)
    subprocess.run(
        ["openssl", "pkeyutl", "-sign", "-inkey", str(private), "-rawin",
         "-in", str(data_file), "-out", str(out)],
        check=True, capture_output=True,
    )
    data_file.unlink()


class Device:
    """A throwaway controller: pinned anchors, a package tree, applied flags."""

    def __init__(self, root: Path):
        self.root = root
        self.keys = root / "keys"
        self.etc = root / "etc-boneio"
        self.applied = root / "applied"
        self.package = root / "pkg" / "boneio"
        self.plans = self.package / "migrations" / "plans"
        self.assets = self.package / "migrations" / "assets"
        for path in (self.keys, self.etc, self.applied, self.plans, self.assets):
            path.mkdir(parents=True, exist_ok=True)

        self.release_key = _genkey(self.keys / "release.pem")
        self.recovery_key = _genkey(self.keys / "recovery.pem")
        _pubkey(self.release_key, self.etc / "migrations.pem")
        _pubkey(self.recovery_key, self.etc / "migrations-recovery.pem")
        self.release = "1.6.0"

    def add_asset(self, rel: str, content: bytes) -> str:
        """Write an asset and return its digest."""
        path = self.assets / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return hashlib.sha256(content).hexdigest()

    def publish(self, plans: dict[str, list], key: Path | None = None,
                release: str | None = None) -> None:
        """Sign and write plans plus the manifest, as a release would."""
        signing = key or self.release_key
        digests = {}
        for version, actions in plans.items():
            data = _canonical(actions)
            (self.plans / f"{version}.json").write_bytes(data)
            _sign(signing, data, self.plans / f"{version}.sig")
            digests[version] = hashlib.sha256(data).hexdigest()
        manifest = {"release": release or self.release, "plans": digests}
        data = _canonical(manifest)
        (self.plans / "manifest.json").write_bytes(data)
        _sign(signing, data, self.plans / "manifest.sig")

    def install(self, helper, monkeypatch) -> None:
        """Point the helper at this device instead of the real filesystem."""
        monkeypatch.setattr(helper, "PINNED_DIR", self.etc)
        monkeypatch.setattr(helper, "RELEASE_ANCHOR", self.etc / "migrations.pem")
        monkeypatch.setattr(
            helper, "RECOVERY_ANCHOR", self.etc / "migrations-recovery.pem"
        )
        monkeypatch.setattr(helper, "DEV_HATCH", self.etc / "allow-unsigned-migrations")
        monkeypatch.setattr(helper, "APPLIED_DIR", self.applied)
        monkeypatch.setattr(helper, "RELEASE_FLOOR", self.applied / ".release-floor")
        monkeypatch.setattr(
            helper, "RECOVERY_ALLOWED_PATHS",
            {str(self.etc / "migrations.pem"), str(self.etc / "migrations-recovery.pem")},
        )
        # The suite does not run as root, so nothing on disk is root-owned.
        # Ownership itself is covered by test_root_owned_* below; here we keep
        # every other property of the check.
        monkeypatch.setattr(
            helper, "_root_owned",
            lambda path: (
                os.path.isfile(path)
                and not os.path.islink(path)
                and not path.lstat().st_mode & 0o022
            ),
        )
        monkeypatch.setattr(helper, "_assert_root", lambda: None)

    def run(self, helper, monkeypatch, request: dict) -> int:
        """Feed *request* to the helper on stdin and return its exit status."""
        monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(request)))
        return helper.main([])

    def ask(self, helper, monkeypatch, version: str, **extra) -> int:
        """Ask for *version* with a well-formed protocol 2 request."""
        request = {
            "protocol": 2,
            "version": version,
            "package_root": str(self.package),
        }
        request.update(extra)
        return self.run(helper, monkeypatch, request)


class _Stdin:
    def __init__(self, text: str):
        self._text = text

    def read(self) -> str:
        return self._text


@pytest.fixture
def device(tmp_path, helper, monkeypatch) -> Device:
    dev = Device(tmp_path)
    dev.install(helper, monkeypatch)
    return dev


def _touch_plan(device: Device, target: Path) -> list:
    """A minimal, valid plan that writes one asset to *target*."""
    digest = device.add_asset("hello.conf", b"hello\n")
    return [{
        "action": "install_file",
        "src": "hello.conf",
        "dst": str(target),
        "mode": 0o644,
        "expected_sha256": digest,
    }]


# ------------------------------------------------------------------ happy path


def test_a_signed_plan_is_applied(device, helper, monkeypatch, tmp_path):
    target = tmp_path / "out" / "hello.conf"
    device.publish({"1.6.1": _touch_plan(device, target)})

    assert device.ask(helper, monkeypatch, "1.6.1") == 0
    assert target.read_bytes() == b"hello\n"
    assert (device.applied / "1.6.1.applied").exists()


def test_applying_records_the_release_floor(device, helper, monkeypatch, tmp_path):
    device.publish({"1.6.1": _touch_plan(device, tmp_path / "out.conf")})
    device.ask(helper, monkeypatch, "1.6.1")
    assert (device.applied / ".release-floor").read_text().strip() == "1.6.0"


def test_an_already_applied_migration_is_a_no_op(device, helper, monkeypatch, tmp_path):
    target = tmp_path / "out.conf"
    device.publish({"1.6.1": _touch_plan(device, target)})
    (device.applied / "1.6.1.applied").write_text("applied_at=earlier\n")

    assert device.ask(helper, monkeypatch, "1.6.1") == 0
    assert not target.exists(), "the plan ran again for an applied migration"


# ------------------------------------------------------------- the v1 protocol


def test_a_plan_sent_over_stdin_is_refused(device, helper, monkeypatch, tmp_path):
    """The whole of F-04 in one request."""
    evil = tmp_path / "pwned"
    status = device.run(helper, monkeypatch, {
        "protocol": 2,
        "version": "1.6.1",
        "actions": [{
            "action": "install_file", "src": "x", "dst": str(evil),
            "validate_cmd": f"touch {evil};",
        }],
        "assets_base": str(device.assets),
    })
    assert status == 1
    assert not evil.exists()


def test_a_caller_cannot_suppress_the_applied_flag(device, helper, monkeypatch):
    status = device.run(helper, monkeypatch, {
        "protocol": 2, "version": "1.6.1", "skip_applied_flag": True,
    })
    assert status == 1


def test_protocol_1_requests_are_refused(device, helper, monkeypatch):
    status = device.run(helper, monkeypatch, {"version": "1.6.1", "actions": []})
    assert status == 1


def test_an_unknown_protocol_is_refused(device, helper, monkeypatch):
    assert device.run(helper, monkeypatch, {"protocol": 3, "version": "1.6.1"}) == 1


def test_unknown_request_fields_are_refused(device, helper, monkeypatch, tmp_path):
    device.publish({"1.6.1": _touch_plan(device, tmp_path / "out.conf")})
    status = device.ask(helper, monkeypatch, "1.6.1", surprise="hello")
    assert status == 1


@pytest.mark.parametrize("version", ["", "../../etc/passwd", "1.6.1; rm -rf /", "x"])
def test_malformed_versions_are_refused(device, helper, monkeypatch, version):
    assert device.run(
        helper, monkeypatch,
        {"protocol": 2, "version": version, "package_root": str(device.package)},
    ) == 1


def test_stdin_that_is_not_json_is_refused(device, helper, monkeypatch):
    monkeypatch.setattr("sys.stdin", _Stdin("not json at all"))
    assert helper.main([]) == 1


# -------------------------------------------------------------- the trust path


def test_a_manifest_signed_by_an_unknown_key_is_refused(
    device, helper, monkeypatch, tmp_path
):
    stranger = _genkey(device.keys / "stranger.pem")
    device.publish({"1.6.1": _touch_plan(device, tmp_path / "out.conf")}, key=stranger)
    assert device.ask(helper, monkeypatch, "1.6.1") == 1


def test_a_tampered_plan_is_refused(device, helper, monkeypatch, tmp_path):
    """Digest mismatch against the manifest."""
    victim = tmp_path / "victim"
    victim.write_text("still here\n")
    device.publish({"1.6.1": _touch_plan(device, tmp_path / "out.conf")})

    plan = json.loads((device.plans / "1.6.1.json").read_bytes())
    plan.append({"action": "remove_file", "path": str(victim)})
    (device.plans / "1.6.1.json").write_bytes(_canonical(plan))

    assert device.ask(helper, monkeypatch, "1.6.1") == 1
    assert victim.exists(), "the appended action ran despite the digest mismatch"


def test_a_tampered_plan_with_a_matching_manifest_is_still_refused(
    device, helper, monkeypatch, tmp_path
):
    """The digest alone is not the defence — the plan signature has to hold.

    An attacker who can rewrite the plan can also rewrite the manifest's digest
    for it. What they cannot do is produce a signature for either.
    """
    device.publish({"1.6.1": _touch_plan(device, tmp_path / "out.conf")})

    plan = [{"action": "remove_file", "path": str(tmp_path / "victim")}]
    data = _canonical(plan)
    (device.plans / "1.6.1.json").write_bytes(data)
    manifest = json.loads((device.plans / "manifest.json").read_bytes())
    manifest["plans"]["1.6.1"] = hashlib.sha256(data).hexdigest()
    (device.plans / "manifest.json").write_bytes(_canonical(manifest))

    assert device.ask(helper, monkeypatch, "1.6.1") == 1


def test_a_version_absent_from_the_manifest_is_refused(
    device, helper, monkeypatch, tmp_path
):
    device.publish({"1.6.1": _touch_plan(device, tmp_path / "out.conf")})
    assert device.ask(helper, monkeypatch, "1.6.2") == 1


def test_a_missing_package_root_is_refused(device, helper, monkeypatch):
    assert device.run(helper, monkeypatch, {
        "protocol": 2, "version": "1.6.1", "package_root": "/nonexistent",
    }) == 1


# -------------------------------------------------------------- release floor


def test_an_older_release_cannot_replay_a_migration(
    device, helper, monkeypatch, tmp_path
):
    """Every signature in an older package tree is genuine.

    So without a floor, an attacker restores an old release wholesale and
    presents a migration this device never applied.
    """
    (device.applied / ".release-floor").write_text("1.6.4\n")
    device.publish(
        {"1.6.1": _touch_plan(device, tmp_path / "out.conf")}, release="1.5.0"
    )
    assert device.ask(helper, monkeypatch, "1.6.1") == 1


def test_the_same_release_is_still_accepted(device, helper, monkeypatch, tmp_path):
    (device.applied / ".release-floor").write_text("1.6.0\n")
    device.publish({"1.6.1": _touch_plan(device, tmp_path / "out.conf")})
    assert device.ask(helper, monkeypatch, "1.6.1") == 0


def test_the_floor_only_moves_forward(device, helper, monkeypatch, tmp_path):
    (device.applied / ".release-floor").write_text("1.7.0\n")
    device.publish({"1.6.1": _touch_plan(device, tmp_path / "out.conf")})
    device.ask(helper, monkeypatch, "1.6.1")
    assert (device.applied / ".release-floor").read_text().strip() == "1.7.0"


# ------------------------------------------------------------- recovery anchor


def test_a_recovery_signed_plan_may_repin_the_anchors(device, helper, monkeypatch):
    new_release = _genkey(device.keys / "new-release.pem")
    fresh = _pubkey(new_release, device.keys / "new-release.pub.pem")
    digest = device.add_asset("new-release.pem", fresh.read_bytes())
    plan = [{
        "action": "install_file",
        "src": "new-release.pem",
        "dst": str(device.etc / "migrations.pem"),
        "mode": 0o444,
        "expected_sha256": digest,
    }]
    device.publish({"1.6.9": plan}, key=device.recovery_key)

    assert device.ask(helper, monkeypatch, "1.6.9") == 0
    assert (device.etc / "migrations.pem").read_bytes() == fresh.read_bytes()


def test_a_recovery_signed_plan_may_not_do_anything_else(
    device, helper, monkeypatch, tmp_path
):
    """The sheet in the safe is a key to one operation, not to the fleet."""
    target = tmp_path / "elsewhere.conf"
    device.publish({"1.6.9": _touch_plan(device, target)}, key=device.recovery_key)

    assert device.ask(helper, monkeypatch, "1.6.9") == 1
    assert not target.exists()


def test_a_recovery_signed_plan_may_not_touch_other_paths(
    device, helper, monkeypatch, tmp_path
):
    plan = [{"action": "remove_file", "path": str(tmp_path / "victim")}]
    device.publish({"1.6.9": plan}, key=device.recovery_key)
    assert device.ask(helper, monkeypatch, "1.6.9") == 1


# ------------------------------------------------------------------ validators


def test_validate_cmd_inside_a_signed_plan_is_refused(
    device, helper, monkeypatch, tmp_path
):
    """Signed by the vendor is not the same as allowed to run anything.

    If the signing key could authorise an arbitrary root command, a compromised
    release would own every controller in the field.
    """
    marker = tmp_path / "ran"
    plan = _touch_plan(device, tmp_path / "out.conf")
    plan[0]["validate_cmd"] = f"touch {marker};"
    device.publish({"1.6.1": plan})

    assert device.ask(helper, monkeypatch, "1.6.1") == 1
    assert not marker.exists()


def test_an_unknown_validator_name_is_refused(device, helper, monkeypatch, tmp_path):
    plan = _touch_plan(device, tmp_path / "out.conf")
    plan[0]["validate"] = "definitely-not-a-validator"
    device.publish({"1.6.1": plan})
    assert device.ask(helper, monkeypatch, "1.6.1") == 1


def test_the_validator_inventory_covers_what_migrations_use(helper):
    """visudo and sshd are the only validators any migration asks for."""
    assert {"sudoers", "sshd"} <= set(helper.VALIDATORS)
    assert helper.VALIDATORS["sudoers"] == ["visudo", "-cf"]
    assert helper.VALIDATORS["sshd"] == ["sshd", "-t", "-f"]


def _every_action():
    """Every action of every migration in the tree, with its version."""
    import importlib
    import pkgutil

    from boneio.migrations import versions

    for info in pkgutil.iter_modules(versions.__path__):
        module = importlib.import_module(f"{versions.__name__}.{info.name}")
        if not hasattr(module, "plan"):
            continue
        for action in module.plan():
            yield module.VERSION, action.to_dict()


def test_the_helper_accepts_every_action_in_the_tree(helper):
    """The check that was missing.

    The old test asked whether the helper's own vocabulary was well formed,
    which it always was, and never whether the migrations were written in it.
    Three were not: 1.3.0, 1.4.0 and 1.6.4 carried only ``validate_cmd``, which
    v2 refuses by design — that refusal is the F-04 fix. On a device they were
    refused one by one, and a refusal stops the queue, so a controller stalled
    at 1.6.4 with six later migrations behind it and no boneio-system.

    Every action is put through the helper's own gate rather than a copy of its
    rules, so this cannot drift from what the helper actually does.
    """
    problems = []
    for version, action in _every_action():
        if action["action"] not in helper.ALLOWED_ACTIONS:
            problems.append(f"{version}: unknown action {action['action']!r}")
            continue
        try:
            helper._validator_for(action)
        except helper.Refused as err:
            problems.append(f"{version}: {err}")

    assert not problems, "migrations this helper would refuse:\n  " + "\n  ".join(problems)


def test_a_validator_name_the_helper_does_not_have_is_caught(helper):
    """Guards the test above: it has to fail when something is wrong."""
    with pytest.raises(helper.Refused):
        helper._validator_for({"action": "install_file", "validate": "rspec"})


# ---------------------------------------------------------------- asset digest


def test_an_install_without_a_digest_in_the_plan_is_refused(
    device, helper, monkeypatch, tmp_path
):
    plan = _touch_plan(device, tmp_path / "out.conf")
    del plan[0]["expected_sha256"]
    device.publish({"1.6.1": plan})
    assert device.ask(helper, monkeypatch, "1.6.1") == 1


def test_an_asset_that_does_not_match_the_signed_digest_is_refused(
    device, helper, monkeypatch, tmp_path
):
    """The asset lives in the same writable tree as the plan."""
    target = tmp_path / "out.conf"
    device.publish({"1.6.1": _touch_plan(device, target)})
    (device.assets / "hello.conf").write_bytes(b"malicious\n")

    assert device.ask(helper, monkeypatch, "1.6.1") == 1
    assert not target.exists()


def test_an_asset_path_cannot_escape_the_assets_directory(
    device, helper, monkeypatch, tmp_path
):
    secret = tmp_path / "secret"
    secret.write_bytes(b"secret\n")
    plan = [{
        "action": "install_file",
        "src": "../../../" + str(secret.relative_to(tmp_path)),
        "dst": str(tmp_path / "leaked"),
        "expected_sha256": hashlib.sha256(b"secret\n").hexdigest(),
    }]
    device.publish({"1.6.1": plan})
    assert device.ask(helper, monkeypatch, "1.6.1") == 1


def test_a_disallowed_action_type_is_refused(device, helper, monkeypatch):
    device.publish({"1.6.1": [{"action": "run_shell", "cmd": "id"}]})
    assert device.ask(helper, monkeypatch, "1.6.1") == 1


# -------------------------------------------------------------------- dev hatch


def test_the_dev_hatch_allows_an_unsigned_plan(device, helper, monkeypatch, tmp_path):
    (device.etc / "allow-unsigned-migrations").write_text("dev\n")
    target = tmp_path / "unsigned.conf"
    digest = device.add_asset("hello.conf", b"hello\n")
    status = device.run(helper, monkeypatch, {
        "protocol": 2,
        "version": "1.6.1",
        "actions": [{
            "action": "install_file", "src": "hello.conf", "dst": str(target),
            "expected_sha256": digest,
        }],
        "assets_base": str(device.assets),
    })
    assert status == 0
    assert target.read_bytes() == b"hello\n"


def test_without_the_hatch_the_same_request_is_refused(
    device, helper, monkeypatch, tmp_path
):
    target = tmp_path / "unsigned.conf"
    digest = device.add_asset("hello.conf", b"hello\n")
    status = device.run(helper, monkeypatch, {
        "protocol": 2,
        "version": "1.6.1",
        "actions": [{
            "action": "install_file", "src": "hello.conf", "dst": str(target),
            "expected_sha256": digest,
        }],
        "assets_base": str(device.assets),
    })
    assert status == 1
    assert not target.exists()


# --------------------------------------------------------------------- selftest


def test_selftest_passes_on_a_healthy_device(device, helper):
    assert helper.selftest() == 0


def test_selftest_fails_without_the_recovery_anchor(device, helper):
    (device.etc / "migrations-recovery.pem").unlink()
    assert helper.selftest() == 1


def test_selftest_fails_without_the_release_anchor(device, helper):
    (device.etc / "migrations.pem").unlink()
    assert helper.selftest() == 1


def test_selftest_exercises_the_real_verification_path(helper):
    """A known-answer vector, in both directions.

    Syntax checking cannot tell the difference between a helper that verifies
    signatures and one that accepts everything; this can.
    """
    assert helper._verify(helper._KAT_PUBKEY, helper._KAT_MESSAGE,
                          helper._KAT_SIGNATURE)
    assert not helper._verify(helper._KAT_PUBKEY, helper._KAT_MESSAGE + b"!",
                              helper._KAT_SIGNATURE)


def test_protocol_version_is_reported(helper, capsys):
    assert helper.main(["--protocol-version"]) == 0
    assert capsys.readouterr().out.strip() == str(helper.PROTOCOL_VERSION)


# ------------------------------------------------------------------ root_owned


def test_root_owned_rejects_a_symlink(helper, tmp_path):
    real = tmp_path / "real"
    real.write_text("x")
    link = tmp_path / "link"
    link.symlink_to(real)
    assert not helper._root_owned(link)


def test_root_owned_rejects_a_group_writable_file(helper, tmp_path):
    path = tmp_path / "loose"
    path.write_text("x")
    os.chmod(path, 0o664)
    assert not helper._root_owned(path)


def test_root_owned_rejects_a_missing_file(helper, tmp_path):
    assert not helper._root_owned(tmp_path / "absent")


def test_root_owned_requires_root_ownership(helper, tmp_path):
    """The suite does not run as root, so this file is not root-owned."""
    path = tmp_path / "mine"
    path.write_text("x")
    os.chmod(path, 0o644)
    assert path.stat().st_uid == os.getuid()
    assert helper._root_owned(path) == (os.getuid() == 0)


# --------------------------------------------------------------- version order


@pytest.mark.parametrize("lower,higher", [
    ("1.5.9", "1.5.10"),
    ("1.6.0.dev1", "1.6.0"),
    ("1.9.0", "1.10.0"),
    ("1.6.0", "1.6.1"),
])
def test_release_ordering(helper, lower, higher):
    assert helper._version_key(lower) < helper._version_key(higher)


# ------------------------------------------------- portable wheel installation


@pytest.fixture
def unit(tmp_path, helper, monkeypatch):
    """A root-owned systemd unit naming an interpreter and a service account."""
    interpreter = tmp_path / "venv" / "bin" / "python3"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("#!/bin/sh\nexit 0\n")
    os.chmod(interpreter, 0o755)

    path = tmp_path / "boneio.service"
    path.write_text(
        "[Service]\n"
        f"ExecStart={interpreter.parent / 'boneio'} run -c /home/boneio/config.yaml\n"
        "User=boneio\n"
    )
    os.chmod(path, 0o644)
    monkeypatch.setattr(helper, "SERVICE_UNITS", (path,))
    monkeypatch.setattr(
        helper, "_root_owned",
        lambda p: (
            os.path.isfile(p) and not os.path.islink(p)
            and not p.lstat().st_mode & 0o022
        ),
    )
    return path, str(interpreter)


def test_the_interpreter_comes_from_the_root_owned_unit(helper, unit):
    """Not from the request: the caller is the account being constrained."""
    _path, interpreter = unit
    assert helper._service_context() == (interpreter, "boneio")


def test_placeholders_are_resolved(helper, unit):
    _path, interpreter = unit
    action = {"python": "@venv", "run_as": "@service_user"}
    assert helper._resolve_interpreter(action) == (interpreter, "boneio")


def test_an_explicit_interpreter_is_left_alone(helper, unit):
    action = {"python": "/usr/bin/python3", "run_as": "someone"}
    assert helper._resolve_interpreter(action) == ("/usr/bin/python3", "someone")


def test_a_unit_that_is_not_root_owned_is_not_trusted(helper, unit, monkeypatch):
    path, _interpreter = unit
    os.chmod(path, 0o666)
    with pytest.raises(helper.Refused, match="root-owned"):
        helper._service_context()


def test_a_unit_naming_a_missing_interpreter_is_refused(helper, unit, tmp_path):
    path, interpreter = unit
    Path(interpreter).unlink()
    with pytest.raises(helper.Refused, match="not executable"):
        helper._service_context()


def test_the_wheel_is_chosen_by_this_device_s_tags(helper, monkeypatch):
    """A plan frozen in CI must not pick the wheel; CI's tags are not the device's."""
    monkeypatch.setattr(
        helper, "_interpreter_tags", lambda python, run_as: ("cp313", "linux_armv7l")
    )
    action = {
        "wheel_candidates": [
            "wheels/pyyaml-6.0.3-cp311-cp311-linux_x86_64.whl",
            "wheels/pyyaml-6.0.3-cp313-cp313-linux_armv7l.whl",
        ],
        "wheel_digests": {
            "wheels/pyyaml-6.0.3-cp311-cp311-linux_x86_64.whl": "a" * 64,
            "wheels/pyyaml-6.0.3-cp313-cp313-linux_armv7l.whl": "b" * 64,
        },
    }
    chosen, digest = helper._select_wheel(action, "/x/python3", "boneio")
    assert chosen == "wheels/pyyaml-6.0.3-cp313-cp313-linux_armv7l.whl"
    assert digest == "b" * 64


def test_no_matching_wheel_is_refused(helper, monkeypatch):
    monkeypatch.setattr(
        helper, "_interpreter_tags", lambda python, run_as: ("cp399", "linux_riscv64")
    )
    action = {
        "wheel_candidates": ["wheels/pyyaml-6.0.3-cp313-cp313-linux_armv7l.whl"],
        "wheel_digests": {"wheels/pyyaml-6.0.3-cp313-cp313-linux_armv7l.whl": "b" * 64},
    }
    with pytest.raises(helper.Refused, match="no bundled wheel matches"):
        helper._select_wheel(action, "/x/python3", "boneio")


def test_a_chosen_wheel_without_a_pinned_digest_is_refused(helper, monkeypatch):
    """The selection happens on the device, so every candidate needs a digest."""
    monkeypatch.setattr(
        helper, "_interpreter_tags", lambda python, run_as: ("cp313", "linux_armv7l")
    )
    action = {
        "wheel_candidates": ["wheels/pyyaml-6.0.3-cp313-cp313-linux_armv7l.whl"],
        "wheel_digests": {},
    }
    with pytest.raises(helper.Refused, match="no digest"):
        helper._select_wheel(action, "/x/python3", "boneio")


# --------------------------------------------------------------- group removal
#
# Membership of ``docker`` is root without a password, so taking it away is the
# last step of the hardening. The verb that does it is the one action in the
# vocabulary that changes an account rather than a file, which is why these
# tests are mostly about the pairs it will *not* touch.


class _FakeGroup:
    def __init__(self, gid, members):
        self.gr_gid = gid
        self.gr_mem = members


class _FakePasswd:
    def __init__(self, gid):
        self.pw_gid = gid


@pytest.fixture
def groups(helper, monkeypatch, tmp_path):
    """A device where boneio is in docker and the replacement is installed."""
    containers = tmp_path / "boneio-containers"
    containers.write_text("#!/usr/bin/env python3\n")
    os.chmod(containers, 0o755)
    monkeypatch.setattr(helper, "CONTAINERS_HELPER", containers)
    monkeypatch.setattr(helper, "_root_owned", lambda path: path == containers)

    state = {"groups": {"docker": _FakeGroup(999, ["boneio"])},
             "users": {"boneio": _FakePasswd(1000)},
             "calls": []}

    def getgrnam(name):
        try:
            return state["groups"][name]
        except KeyError:
            raise KeyError(name)

    def getpwnam(name):
        try:
            return state["users"][name]
        except KeyError:
            raise KeyError(name)

    def run(argv, **kwargs):
        state["calls"].append(argv)
        return subprocess.CompletedProcess(argv, state.get("rc", 0), "", "")

    monkeypatch.setattr(helper.grp, "getgrnam", getgrnam)
    monkeypatch.setattr(helper.pwd, "getpwnam", getpwnam)
    monkeypatch.setattr(helper.subprocess, "run", run)
    return state


def _remove(helper, account="boneio", group="docker"):
    helper.handle_remove_from_group(
        {"action": "remove_from_group", "account": account, "group": group}, ""
    )


def test_the_docker_group_is_removed_with_gpasswd(helper, groups):
    _remove(helper)
    assert groups["calls"] == [["gpasswd", "--delete", "boneio", "docker"]]


@pytest.mark.parametrize(
    "account,group",
    [
        ("boneio", "admin"),   # the operator's own way back in, kept on purpose
        ("boneio", "sudo"),
        ("boneio", "boneio"),
        ("root", "docker"),
        ("mosquitto", "docker"),
        ("", ""),
    ],
)
def test_only_the_listed_membership_may_be_taken_away(helper, groups, account, group):
    with pytest.raises(helper.Refused):
        _remove(helper, account, group)
    assert groups["calls"] == []


def test_the_vocabulary_is_a_closed_list_of_pairs(helper):
    assert helper.REMOVABLE_MEMBERSHIPS == {("boneio", "docker")}


def test_docker_is_not_removed_without_the_replacement(helper, groups, monkeypatch):
    """The plan cannot assert that boneio-containers is there; the device can.

    Removing the group on a controller whose container helper never arrived
    would leave Node-RED unmanageable with no way to put it back that does not
    need somebody physically present.
    """
    monkeypatch.setattr(helper, "_root_owned", lambda path: False)
    with pytest.raises(helper.Refused):
        _remove(helper)
    assert groups["calls"] == []


def test_a_group_that_does_not_exist_is_not_an_error(helper, groups):
    """A device imaged after this change never had the group."""
    del groups["groups"]["docker"]
    _remove(helper)
    assert groups["calls"] == []


def test_an_account_that_does_not_exist_is_not_an_error(helper, groups):
    del groups["users"]["boneio"]
    _remove(helper)
    assert groups["calls"] == []


def test_an_account_already_out_of_the_group_is_not_an_error(helper, groups):
    """Re-running the migration on a device that has had it must not fail."""
    groups["groups"]["docker"] = _FakeGroup(999, [])
    _remove(helper)
    assert groups["calls"] == []


def test_a_primary_group_is_refused(helper, groups):
    """gpasswd would refuse too, but not before the account is left groupless
    on a system where it is the only thing holding the home directory."""
    groups["users"]["boneio"] = _FakePasswd(999)
    with pytest.raises(helper.Refused):
        _remove(helper)
    assert groups["calls"] == []


def test_a_failing_gpasswd_is_reported_not_swallowed(helper, groups):
    groups["rc"] = 1
    with pytest.raises(helper.Refused):
        _remove(helper)


def test_group_removal_is_not_available_to_the_recovery_key(helper):
    """The offline anchor exists to re-pin a signing key and nothing else."""
    assert "remove_from_group" in helper.ALLOWED_ACTIONS
    assert "remove_from_group" not in helper.RECOVERY_ALLOWED_ACTIONS


def test_group_removal_has_a_handler(helper):
    assert helper.ACTION_HANDLERS["remove_from_group"] is helper.handle_remove_from_group


def test_the_migration_asks_for_a_pair_the_helper_accepts(helper):
    """Cross-check: the plan is written in one repo and enforced in another
    file that deliberately does not import it."""
    from boneio.migrations.versions import v1_6_11_drop_docker_group as migration

    for action in (a.to_dict() for a in migration.plan()):
        assert action["action"] in helper.ALLOWED_ACTIONS
        assert (action["account"], action["group"]) in helper.REMOVABLE_MEMBERSHIPS
