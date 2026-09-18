"""Structural checks over every migration module.

These guard the class of mistake that only shows up on a device: a migration
that installs an asset missing from MANIFEST.sha256 fails at apply time, after
the helper has already been asked for root, and the failure stops every later
migration for that controller.
"""

from __future__ import annotations

import re
import hashlib
import importlib
import pkgutil
from pathlib import Path

import pytest

from boneio.migrations.actions import InstallFile

VERSIONS_PKG = "boneio.migrations.versions"
MIGRATIONS_DIR = Path(importlib.import_module(VERSIONS_PKG).__file__).parent
ASSETS_DIR = MIGRATIONS_DIR.parent / "assets"
MANIFEST = ASSETS_DIR / "MANIFEST.sha256"


def _migration_modules():
    """Import and return every migration module."""
    modules = []
    for _, name, _ in pkgutil.iter_modules([str(MIGRATIONS_DIR)]):
        modules.append(importlib.import_module(f"{VERSIONS_PKG}.{name}"))
    return modules


def _manifest() -> dict[str, str]:
    """Parse MANIFEST.sha256 into {relative path: sha256}."""
    entries = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, path = line.partition("  ")
        entries[path.strip()] = digest.strip()
    return entries


MODULES = _migration_modules()
ALL_INSTALLS = [
    (mod.VERSION, action)
    for mod in MODULES
    for action in mod.plan()
    if isinstance(action, InstallFile)
]


def test_there_are_migrations_to_check():
    # Guards the discovery itself: an empty list would make every test below
    # pass without looking at anything.
    assert len(MODULES) > 10


@pytest.mark.parametrize("mod", MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
class TestModuleShape:
    def test_declares_the_required_attributes(self, mod):
        assert isinstance(mod.VERSION, str) and mod.VERSION
        assert isinstance(mod.DESCRIPTION, str) and mod.DESCRIPTION
        assert isinstance(mod.REQUIRES_ROOT, bool)

    def test_plan_returns_serialisable_actions(self, mod):
        # An empty plan is legitimate: v1_5_2_libyaml and friends inspect the
        # running system and plan nothing when the work is already done.
        plan = mod.plan()
        assert isinstance(plan, list)
        for action in plan:
            # Every action has to survive the trip to the helper as a dict.
            assert isinstance(action.to_dict(), dict)
            assert action.to_dict().get("action")


def test_versions_are_unique():
    versions = [mod.VERSION for mod in MODULES]
    duplicates = {v for v in versions if versions.count(v) > 1}
    assert not duplicates, f"duplicate migration versions: {sorted(duplicates)}"


def test_module_name_matches_its_version():
    # v1_6_2_drop_build_sudo_rule.py must declare VERSION "1.6.2", or the
    # ordering the filenames imply is not the ordering that runs.
    for mod in MODULES:
        stem = mod.__name__.rsplit(".", 1)[-1]
        parts = stem.lstrip("v").split("_")
        expected = ".".join(parts[:3])
        assert mod.VERSION == expected, (
            f"{stem} declares VERSION {mod.VERSION}, expected {expected}"
        )


@pytest.mark.parametrize(
    "version, action",
    ALL_INSTALLS,
    ids=[f"{v}:{a.src}" for v, a in ALL_INSTALLS],
)
class TestInstalledAssets:
    def test_the_asset_exists(self, version, action):
        assert (ASSETS_DIR / action.src).is_file(), (
            f"migration {version} installs {action.src}, which is not in assets/"
        )

    def test_the_asset_is_in_the_manifest(self, version, action):
        # The helper refuses to write a file whose hash it cannot confirm, so a
        # missing entry is a migration that always fails.
        assert action.src in _manifest(), (
            f"{action.src} is missing from MANIFEST.sha256 — "
            "run scripts/generate_manifest.py"
        )

    def test_the_manifest_hash_is_current(self, version, action):
        # Only meaningful for assets without template substitution; the runner
        # hashes the rendered content for those.
        if action.template_vars:
            pytest.skip("hash is computed after template substitution")
        on_disk = hashlib.sha256((ASSETS_DIR / action.src).read_bytes()).hexdigest()
        assert _manifest()[action.src] == on_disk, (
            f"{action.src} changed without regenerating MANIFEST.sha256"
        )

    def test_the_destination_is_absolute(self, version, action):
        assert action.dst.startswith("/"), f"{version} installs to {action.dst}"


class TestTheSecurityMigrations:
    """The three added for the 1.6 pentest findings, by behaviour."""

    def _module(self, version):
        found = [m for m in MODULES if m.VERSION == version]
        assert found, f"no migration declares version {version}"
        return found[0]

    def test_162_removes_the_build_time_sudo_rule(self):
        paths = [a.to_dict().get("path") for a in self._module("1.6.2").plan()]
        assert "/etc/sudoers.d/boneio-setup" in paths

    def test_163_allows_ssh_and_the_tls_panel(self):
        ports = {a.to_dict().get("port") for a in self._module("1.6.3").plan()}
        # Without 22 the first 'ufw enable' locks the operator out; without
        # 8443 it takes the TLS panel with it.
        assert {22, 8443} <= ports

    def test_163_does_not_enable_the_firewall(self):
        actions = {a.to_dict()["action"] for a in self._module("1.6.3").plan()}
        assert actions == {"ufw_allow"}

    def test_164_validates_before_replacing_the_sshd_config(self):
        install = self._module("1.6.4").plan()[0]
        assert isinstance(install, InstallFile)
        assert install.validate_cmd, "an unvalidated sshd config can lock a device out"
        assert install.validate_cmd.startswith("sshd -t")

    def test_164_reloads_the_debian_unit_name(self):
        install = self._module("1.6.4").plan()[0]
        assert install.on_change is not None
        # sshd.service is an alias on Debian; reloading an alias is not
        # reliable across systemd versions.
        assert install.on_change.to_dict().get("unit") == "ssh"

    def test_164_is_ordered_last_among_the_security_trio(self):
        # It is the only one of the three that can fail — sshd -t can reject a
        # config on an image we have not seen — and a failed migration stops the
        # ones behind it.
        assert max(("1.6.2", "1.6.3", "1.6.4")) == "1.6.4"
        assert self._module("1.6.4")

    def test_the_hardening_migrations_are_not_left_behind_164(self):
        """1.6.4 can fail, so it must not be able to block the CVE fix.

        Version order puts the trust transition and the retirement of the
        legacy helper after 1.6.4, where an unrelated sshd problem would stop
        them from ever running. The runner hoists them to the front instead.
        """
        from boneio.migrations.runner import HARDENING_FIRST

        assert HARDENING_FIRST == ("1.6.5", "1.6.6")
        for version in HARDENING_FIRST:
            assert self._module(version), f"{version} is hoisted but does not exist"
            assert version > "1.6.4", (
                f"{version} sorts before 1.6.4, so hoisting it is pointless"
            )


class TestConsoleIssue:
    """The serial console banner added by 1.6.12.

    Rendered by agetty, not by us, so what these check is the two things that
    silently produce a useless line: an interface that is not the one a person
    at the cabinet cares about, and an escape that never gets expanded.
    """

    @staticmethod
    def _fragment() -> str:
        from boneio.migrations.runner import ASSETS_DIR

        return (ASSETS_DIR / "issue.d" / "10-boneio.issue").read_text()

    def test_the_interface_is_named(self):
        """A bare \\4 is "the first fully configured interface", and on this
        device that can be a docker bridge holding a 172.17 address."""
        assert "\\4{eth0}" in self._fragment()
        assert not re.search(r"\\4(?!\{)", self._fragment())

    def test_it_says_where_the_panel_is(self):
        assert "8090" in self._fragment()

    def test_it_ends_with_a_newline(self):
        """agetty concatenates the fragments; without it the next one runs on."""
        assert self._fragment().endswith("\n")

    def test_the_migration_installs_it_where_agetty_looks(self):
        from boneio.migrations.versions import v1_6_12_console_shows_ip as migration

        actions = [a.to_dict() for a in migration.plan()]
        assert len(actions) == 1
        assert actions[0]["dst"].startswith("/etc/issue.d/")
        # /etc/issue belongs to base-files and already carries the vendor's text.
        assert actions[0]["dst"] != "/etc/issue"
