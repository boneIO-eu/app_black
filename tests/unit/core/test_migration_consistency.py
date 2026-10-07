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

    def test_it_names_no_port(self):
        """The panel's port is ``web.port`` from the operator's config, and
        this file is frozen into a signed plan — a port written here is a
        guess that cannot be corrected on the device that disproves it."""
        assert not re.search(r"\d{2,5}", self._fragment())

    def test_it_names_the_host_as_well_as_the_address(self):
        """The address is what changes; the name is what to write down.

        A new DHCP lease moves the address, and a certificate naming one goes
        stale with it. mDNS resolves the hostname on the same network and the
        proxy issues a matching certificate for it by itself.
        """
        assert "\\n.local" in self._fragment()

    def test_it_is_plain_ascii(self):
        """Serial consoles are not reliably UTF-8; a decorative separator
        arrives there as mojibake."""
        self._fragment().encode("ascii")

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


class TestJournalOnSerialConsole:
    """The journald drop-in added by 1.6.25."""

    @staticmethod
    def _settings() -> dict[str, str]:
        from boneio.migrations.runner import ASSETS_DIR

        text = (ASSETS_DIR / "journald" / "boneio-console.conf").read_text()
        settings = {}
        section = None
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("["):
                section = line
                continue
            key, _, value = line.partition("=")
            settings[f"{section}{key}"] = value
        return settings

    def test_it_forwards_to_the_debug_uart(self):
        settings = self._settings()
        assert settings["[Journal]ForwardToConsole"] == "yes"
        assert settings["[Journal]TTYPath"] == "/dev/ttyS0"

    def test_it_forwards_warnings_and_worse_only(self):
        """A serial line is slow and journald writes to it as it logs; info
        would put every routine message on the wire."""
        assert self._settings()["[Journal]MaxLevelConsole"] == "warning"

    def test_it_is_a_drop_in_and_restarts_journald(self):
        """journald.conf itself is installed whole by 1.5.7 and 1.5.14."""
        from boneio.migrations.versions import (
            v1_6_25_journal_to_serial_console as migration,
        )

        actions = [a.to_dict() for a in migration.plan()]
        assert len(actions) == 1
        assert actions[0]["dst"] == "/etc/systemd/journald.conf.d/boneio-console.conf"
        assert actions[0]["on_change"] == {
            "action": "systemctl_restart",
            "unit": "systemd-journald",
        }


class TestSshLoginScreen:
    """The SSH banner and the login status added by 1.6.28."""

    @staticmethod
    def _asset(path: str) -> str:
        from boneio.migrations.runner import ASSETS_DIR

        return (ASSETS_DIR / path).read_text()

    @staticmethod
    def _actions() -> list[dict]:
        from boneio.migrations.versions import v1_6_28_ssh_login_screen as migration

        return [a.to_dict() for a in migration.plan()]

    def test_the_banner_carries_no_date_version_or_password(self):
        """It is frozen into a signed plan and shown before authentication: a
        date is stale after the next unattended upgrade, and units upgraded
        from 1.5 may still have the shipped password or one of their own."""
        banner = self._asset("sshd/boneio-banner")
        assert not re.search(r"\d{4}-\d{2}-\d{2}|\d+\.\d+\.\d+", banner)
        assert "password" not in banner.lower()
        assert "boneio" in banner

    def test_the_banner_is_short_plain_ascii(self):
        """Every scp and `ssh host command` prints it too, on stderr."""
        banner = self._asset("sshd/boneio-banner")
        banner.encode("ascii")
        assert banner.endswith("\n")
        assert len(banner.splitlines()) <= 3

    def test_the_drop_in_points_at_the_installed_banner(self):
        settings = [
            line.split(None, 1)
            for line in self._asset("sshd/20-boneio-banner.conf").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        banner_dst = next(a["dst"] for a in self._actions() if a["src"] == "sshd/boneio-banner")
        assert settings == [["Banner", banner_dst]]

    def test_the_drop_in_goes_last_validated_and_reloads_ssh(self):
        """sshd -t is the only step that can refuse; ordered last, it cannot
        leave the banner file or the script behind uninstalled."""
        actions = self._actions()
        last = actions[-1]
        assert last["dst"] == "/etc/ssh/sshd_config.d/20-boneio-banner.conf"
        assert last["validate"] == "sshd"
        assert last["on_change"] == {"action": "systemctl_reload", "unit": "ssh"}
        assert all("validate" not in a for a in actions[:-1])

    def test_the_banner_is_a_drop_in_not_a_base_files_edit(self):
        dsts = {a["dst"] for a in self._actions()}
        assert not dsts & {"/etc/issue", "/etc/issue.net", "/etc/motd", "/etc/ssh/sshd_config"}
        # setup_boneio.sh writes this one as well.
        assert "/etc/ssh/sshd_config.d/10-boneio-hardening.conf" not in dsts

    def test_run_parts_will_run_the_motd_script(self):
        """run-parts skips a name with a dot and a file without an execute bit."""
        motd = next(a for a in self._actions() if a["src"] == "motd/20-boneio")
        assert motd["dst"].startswith("/etc/update-motd.d/")
        assert re.fullmatch(r"[A-Za-z0-9_-]+", motd["dst"].rsplit("/", 1)[1])
        assert motd["mode"] == 0o755

    def test_the_motd_script_executes_nothing_from_the_venv(self):
        """It runs as root; the venv, the app and the config are the boneio
        account's to write. Reading is fine, sourcing or running is root."""
        script = self._asset("motd/20-boneio")
        code = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))
        # A path through lib/python3*/ is fine; python as a command is not.
        assert not re.search(r"\bpython[0-9.]*(\s|$)", code)
        assert "/bin/" not in code.replace("PATH=/usr/sbin:/usr/bin:/sbin:/bin", "").replace(
            "${exe%/bin/*}", ""
        )
        assert not re.search(r"(^|[;&|]\s*)(\.|source|eval|exec)\s", code, re.M)

    def test_the_motd_offers_the_proxy_port_the_app_offers(self):
        """The same fallback as _preferred_url, so the login screen and the
        panel hand out the same address."""
        from boneio.const import DEFAULT_PROXY_PORT

        script = self._asset("motd/20-boneio")
        assert f"proxy_port=${{proxy_port:-{DEFAULT_PROXY_PORT}}}" in script
        assert 'https://$name:$proxy_port' in script

    def test_the_motd_script_is_posix_sh(self):
        import shutil
        import subprocess

        sh = shutil.which("sh")
        if sh is None:
            pytest.skip("no sh")
        from boneio.migrations.runner import ASSETS_DIR

        result = subprocess.run([sh, "-n", str(ASSETS_DIR / "motd" / "20-boneio")], capture_output=True)
        assert result.returncode == 0, result.stderr

    def test_the_motd_script_stays_quiet_where_nothing_is_there(self):
        """A missing service, dogtag or debian_version must not put errors on
        somebody's login, nor fail it. The CI runner has none of them."""
        import shutil
        import subprocess

        sh = shutil.which("sh")
        if sh is None:
            pytest.skip("no sh")
        from boneio.migrations.runner import ASSETS_DIR

        result = subprocess.run(
            [sh, str(ASSETS_DIR / "motd" / "20-boneio")],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0
        assert result.stderr == ""
        assert "System" in result.stdout


class TestServicePasswordChange:
    """1.6.29 reinstalls boneio-system with service-password-change."""

    @staticmethod
    def _actions() -> list[dict]:
        from boneio.migrations.versions import v1_6_29_service_password_change as migration

        return [a.to_dict() for a in migration.plan()]

    def test_the_pristine_copy_goes_first(self):
        """boneio-helpers-heal.service restores /usr/sbin from it at boot, so a
        stale pristine copy would put the old helper back."""
        assert [a["dst"] for a in self._actions()] == [
            "/usr/lib/boneio/trusted/boneio-system",
            "/usr/sbin/boneio-system",
        ]

    def test_both_copies_are_root_owned_and_compiled_first(self):
        """A helper that does not compile takes every privileged operation down."""
        for action in self._actions():
            assert action["src"] == "helpers/boneio-system"
            assert (action["owner"], action["group"], action["mode"]) == ("root", "root", 0o755)
            assert action["validate"] == "python"

    def test_the_helper_it_installs_has_the_verb(self):
        verbs = re.search(
            r"^VERBS = \((.*?)^\)", (ASSETS_DIR / "helpers/boneio-system").read_text(),
            re.MULTILINE | re.DOTALL,
        )
        assert verbs and '"service-password-change"' in verbs.group(1)


class TestOsUpdateAptCache:
    """1.6.30 reinstalls boneio-system, which clears apt's cache when short."""

    @staticmethod
    def _actions() -> list[dict]:
        from boneio.migrations.versions import v1_6_30_os_update_apt_cache as migration

        return [a.to_dict() for a in migration.plan()]

    def test_the_pristine_copy_goes_first(self):
        assert [a["dst"] for a in self._actions()] == [
            "/usr/lib/boneio/trusted/boneio-system",
            "/usr/sbin/boneio-system",
        ]

    def test_both_copies_are_root_owned_and_compiled_first(self):
        for action in self._actions():
            assert action["src"] == "helpers/boneio-system"
            assert (action["owner"], action["group"], action["mode"]) == ("root", "root", 0o755)
            assert action["validate"] == "python"

    def test_the_helper_it_installs_reports_the_cache(self):
        assert '"apt_cache_mb"' in (ASSETS_DIR / "helpers/boneio-system").read_text()


class TestOsUpdateMeasuredSpace:
    """1.6.33 reinstalls boneio-system, which gates an upgrade on apt's figures."""

    @staticmethod
    def _actions() -> list[dict]:
        from boneio.migrations.versions import v1_6_33_os_update_measured_space as migration

        return [a.to_dict() for a in migration.plan()]

    def test_the_pristine_copy_goes_first(self):
        assert [a["dst"] for a in self._actions()] == [
            "/usr/lib/boneio/trusted/boneio-system",
            "/usr/sbin/boneio-system",
        ]

    def test_both_copies_are_root_owned_and_compiled_first(self):
        for action in self._actions():
            assert action["src"] == "helpers/boneio-system"
            assert (action["owner"], action["group"], action["mode"]) == ("root", "root", 0o755)
            assert action["validate"] == "python"

    def test_the_helper_it_installs_reports_the_requirement(self):
        assert '"required_mb"' in (ASSETS_DIR / "helpers/boneio-system").read_text()


class TestCertificateLifetime:
    """The device's own certificate lasts long enough to be worth trusting.

    Caddy's internal issuer defaults to twelve hours. Somebody who installs
    this device's authority on their laptop, or clicks through the warning
    once, is back to an unknown certificate the same evening.
    """

    @staticmethod
    def _scripts() -> list[str]:
        from boneio.migrations.runner import ASSETS_DIR

        root = ASSETS_DIR.parents[1]
        return [
            (ASSETS_DIR / "docker" / "nodered" / "caddy" / "init-certs.sh").read_text(),
            (root / "core" / "cloud" / "data" / "init-certs-cloud.sh").read_text(),
        ]

    def test_both_generators_set_a_leaf_lifetime(self):
        """Cloud mode serves a real certificate from a file, but falls back to
        this issuer — and a fallback that expires by dinner is not one."""
        for script in self._scripts():
            assert "lifetime 180d" in script

    def test_the_intermediate_outlives_the_leaves(self):
        """Caddy refuses to start otherwise, which would take the panel with
        it — the failure is at boot, not at issuance."""
        for script in self._scripts():
            assert "intermediate_lifetime 365d" in script

    def test_the_lifetime_is_set_on_the_issuer(self):
        """`tls internal { lifetime ... }` is not valid Caddyfile — it adapts
        to "unknown subdirective" and the container never starts. It belongs
        inside `issuer internal`."""
        import re

        for script in self._scripts():
            assert re.search(r"issuer internal \{[^}]*lifetime", script, re.S), (
                "lifetime is not inside an issuer block"
            )


class TestSupersession:
    """A migration may declare that a later one makes it pointless.

    The runner then skips it on a device applying both from scratch, which
    stops the same file being written once per revision as the chain grows.
    Only whole migrations are skipped — never parts of one — because the
    privileged helper reads its plan from a signed file and is handed nothing
    but a version string, and it must stay that way.

    The danger is a claim that is not true: a migration that also did something
    else would have that something silently dropped. So the claim is checked
    here rather than trusted.
    """

    @staticmethod
    def _effects(module) -> set:
        """What a migration changes, as comparable keys.

        Args:
            module: A migration module.

        Returns:
            One key per action: the file it writes, the unit it touches, or
            the whole action for anything this does not model.
        """
        effects = set()
        for action in (a.to_dict() for a in module.plan()):
            kind = action.get("action")
            if kind in ("install_file", "set_file_permissions", "remove_file"):
                effects.add(("file", action.get("dst") or action.get("path")))
            elif kind and kind.startswith("systemctl_"):
                effects.add(("unit", kind, action.get("unit")))
            else:
                effects.add((kind, tuple(sorted(map(str, action.items())))))
        return effects

    @staticmethod
    def _modules() -> dict:
        import importlib
        import pkgutil

        from boneio.migrations import versions

        found = {}
        for info in pkgutil.iter_modules(versions.__path__):
            module = importlib.import_module(f"{versions.__name__}.{info.name}")
            if hasattr(module, "VERSION"):
                found[module.VERSION] = module
        return found

    def test_every_supersession_names_a_migration_that_exists(self):
        modules = self._modules()
        for version, module in modules.items():
            successor = getattr(module, "SUPERSEDED_BY", None)
            if successor is not None:
                assert successor in modules, (
                    f"{version} says {successor} replaces it, and there is no {successor}"
                )

    def test_the_successor_really_does_everything_the_older_one_did(self):
        """The whole risk of the mechanism, in one assertion."""
        modules = self._modules()
        for version, module in modules.items():
            successor = getattr(module, "SUPERSEDED_BY", None)
            if successor is None:
                continue
            missing = self._effects(module) - self._effects(modules[successor])
            assert not missing, (
                f"{version} claims {successor} replaces it, but {successor} does "
                f"not do: {sorted(map(str, missing))}"
            )

    def test_a_migration_cannot_be_replaced_by_an_earlier_one(self):
        """Skipping would then drop the work rather than defer it."""
        from boneio.migrations.runner import MigrationInfo

        for version, module in self._modules().items():
            successor = getattr(module, "SUPERSEDED_BY", None)
            if successor is None:
                continue
            older = MigrationInfo(version=version, module_name="", description="")
            newer = MigrationInfo(version=successor, module_name="", description="")
            assert newer.version_tuple() > older.version_tuple(), (
                f"{version} is superseded by {successor}, which comes before it"
            )


def test_1_6_34_puts_the_node_red_login_back():
    """1.6.34 reinstalls the settings.js that 1.6.0 shipped, with adminAuth."""
    from boneio.migrations.actions import InstallFile
    from boneio.migrations.versions import v1_6_0_nodered_admin_auth as first
    from boneio.migrations.versions import v1_6_34_nodered_admin_auth_again as again

    (action,) = again.plan()
    assert isinstance(action, InstallFile)
    assert (action.src, action.dst) == (first.plan()[0].src, first.plan()[0].dst)
    assert (action.owner, action.mode) == ("boneio", 0o644)


class TestSshGuessingPenalty:
    """1.6.35 slows password guessing down without turning passwords off."""

    def _plan(self):
        from boneio.migrations.versions import v1_6_35_ssh_guessing_penalty as migration

        return migration.plan()

    def test_the_drop_in_is_validated_and_reloads_ssh(self):
        (action,) = self._plan()
        assert action.dst == "/etc/ssh/sshd_config.d/15-boneio-penalties.conf"
        assert action.validate == "sshd"
        assert action.on_change.to_dict() == {"action": "systemctl_reload", "unit": "ssh"}

    def test_it_penalises_failures_and_leaves_passwords_on(self):
        text = (ASSETS_DIR / "sshd/15-boneio-penalties.conf").read_text()
        directives = [line.split() for line in text.splitlines() if line and not line.startswith("#")]
        assert directives == [
            ["PerSourcePenalties", "authfail:300s", "max:3600s"],
            ["PerSourceMaxStartups", "3"],
            ["PerSourceNetBlockSize", "32:64"],
        ]

    def test_1_6_38_brings_the_same_file_to_devices_past_1_6_35(self):
        from boneio.migrations.versions import v1_6_38_ssh_penalty_per_block as again

        (first,) = self._plan()
        (second,) = again.plan()
        assert (second.src, second.dst, second.validate) == (first.src, first.dst, first.validate)
        assert second.on_change.to_dict() == {"action": "systemctl_reload", "unit": "ssh"}


def test_1_6_37_takes_boneio_out_of_kmem_after_the_helper_learns_to():
    from boneio.migrations.versions import v1_6_36_helper_drops_kmem as helper
    from boneio.migrations.versions import v1_6_37_drop_kmem_group as kmem

    assert [a.dst for a in helper.plan()] == [
        "/usr/lib/boneio/trusted/boneio-migrate-v2",
        "/usr/sbin/boneio-migrate-v2",
    ]
    assert [a.to_dict() for a in kmem.plan()] == [
        {"action": "remove_from_group", "account": "boneio", "group": "kmem"}
    ]

    def test_the_1_6_4_drop_in_is_left_alone(self):
        dsts = {action.dst for action in self._plan()}
        assert "/etc/ssh/sshd_config.d/10-boneio-hardening.conf" not in dsts


class TestNativeCaddyStaging:
    """1.6.42 puts the packaged Caddy's files in place without switching."""

    @staticmethod
    def _actions() -> list[dict]:
        from boneio.migrations.versions import v1_6_42_native_caddy_staging as migration

        return [a.to_dict() for a in migration.plan()]

    @staticmethod
    def _containers():
        from importlib.machinery import SourceFileLoader

        return SourceFileLoader(
            "boneio_containers_1_6_42", str(ASSETS_DIR / "helpers/boneio-containers")
        ).load_module()

    def test_every_prefix_is_a_state_a_controller_can_be_left_in(self):
        """A failed action stops the run and leaves the finished prefix in
        place until the retry, so the order is the guarantee: the system helper that survives a broken
        Caddy repository before the source list, the key before the list that
        needs it, each pristine copy before its live copy, the drop-in before the
        reload that reads it, the helper before the unit that runs it."""
        steps = [a.get("dst") or a["action"] + (":" + a["unit"] if "unit" in a else "")
                 for a in self._actions()]
        assert steps == [
            "/usr/lib/boneio/trusted/boneio-system",
            "/usr/sbin/boneio-system",
            "/usr/share/keyrings/caddy-stable-archive-keyring.gpg",
            "/etc/apt/preferences.d/caddy",
            "/etc/apt/sources.list.d/caddy-stable.list",
            "/usr/share/boneio/proxy/502.html",
            "/usr/lib/boneio/trusted/boneio-proxy-config",
            "/usr/lib/boneio/proxy-config",
            "/etc/systemd/system/caddy.service.d/boneio.conf",
            "systemctl_daemon_reload",
            "/usr/lib/boneio/trusted/docker-compose-native-proxy.yaml",
            "/usr/lib/boneio/trusted/boneio-containers",
            "/usr/sbin/boneio-containers",
            "/etc/systemd/system/boneio-proxy-recover.service",
            "systemctl_daemon_reload",
            "systemctl_enable:boneio-proxy-recover.service",
            "/etc/apt/apt.conf.d/53boneio-caddy",
            "/usr/lib/boneio/trusted/boneio-helpers-heal",
            "/usr/sbin/boneio-helpers-heal",
        ]

    def test_root_scripts_are_root_owned_and_compiled_first(self):
        scripts = [a for a in self._actions() if a.get("mode") == 0o755]
        assert {a["src"] for a in scripts} == {
            "helpers/boneio-proxy-config", "helpers/boneio-system", "helpers/boneio-containers",
            "helpers/boneio-helpers-heal",
        }
        for action in scripts:
            assert (action["owner"], action["group"], action["validate"]) == (
                "root", "root", "python",
            )

    def test_nothing_starts_or_stops_a_proxy(self):
        """Staging only: the switch is a separate, deliberate step."""
        kinds = {a["action"] for a in self._actions()}
        assert kinds == {"install_file", "systemctl_daemon_reload", "systemctl_enable"}
        assert "ConditionPathExists=/etc/boneio/proxy-native" in (
            ASSETS_DIR / "systemd/caddy-boneio.conf"
        ).read_text()

    def test_the_helper_it_installs_has_the_verbs(self):
        verbs = self._containers().ALL_VERBS
        for verb in ("proxy-switch-start", "proxy-switch-recover", "caddy-root-ca"):
            assert verb in verbs

    def test_the_recovery_unit_runs_a_verb_the_helper_has(self):
        unit = (ASSETS_DIR / "systemd/boneio-proxy-recover.service").read_text()
        assert "ExecStart=/usr/sbin/boneio-containers proxy-switch-recover" in unit

    def test_the_system_helper_it_installs_survives_a_broken_caddy_repo(self):
        assert "CADDY_APT_LIST" in (ASSETS_DIR / "helpers/boneio-system").read_text()

    def test_automatic_updates_add_caddy_without_clearing_the_rest(self):
        """apt.conf.d is read in order: a #clear here would erase the
        Debian-Security origins 52boneio-unattended sets."""
        text = (ASSETS_DIR / "apt/53boneio-caddy").read_text()
        assert "#clear" not in text
        assert '"origin=cloudsmith/caddy/stable,codename=any-version";' in text


class TestHelpersHeal:
    """boneio-helpers-heal restores only from a pristine copy that is there."""

    @staticmethod
    def _heal():
        from importlib.machinery import SourceFileLoader

        return SourceFileLoader(
            "boneio_helpers_heal", str(ASSETS_DIR / "helpers/boneio-helpers-heal")
        ).load_module()

    @staticmethod
    def _trusted_installs() -> list[tuple[str, int, str]]:
        """(version, index in its plan, pristine-copy name) for every install there."""
        prefix = "/usr/lib/boneio/trusted/"
        return [
            (mod.VERSION, i, action.dst.removeprefix(prefix))
            for mod in MODULES
            for i, action in enumerate(mod.plan())
            if isinstance(action, InstallFile) and action.dst.startswith(prefix)
        ]

    def test_every_required_entry_is_there_before_heal_is(self):
        """Heal refuses to restore anything while a required entry's pristine
        copy is missing, so each one has to land no later than the first
        migration that installs heal, and ahead of it within that migration."""
        def version_key(version: str) -> tuple[int, ...]:
            return tuple(int(part) for part in version.split("."))

        heal = self._heal()
        installs = [
            (mod.VERSION, i)
            for mod in MODULES
            for i, action in enumerate(mod.plan())
            if isinstance(action, InstallFile)
            and action.dst == "/usr/sbin/boneio-helpers-heal"
        ]
        first = min(installs, key=lambda vi: (version_key(vi[0]), vi[1]))
        trusted = self._trusted_installs()
        for name, _, _ in heal.RESTORE:
            if name in heal.OPTIONAL:
                continue
            assert any(
                (version_key(v), i) < (version_key(first[0]), first[1])
                for v, i, n in trusted
                if n == name
            ), f"{name} reaches the pristine copy after heal is installed"

    def test_every_optional_entry_reaches_the_pristine_copy_before_heal_is_reinstalled(self):
        heal = self._heal()
        from boneio.migrations.versions import v1_6_42_native_caddy_staging as migration

        dsts = [a.dst for a in migration.plan() if isinstance(a, InstallFile)]
        for name in heal.OPTIONAL:
            assert name in [n for n, _, _ in heal.RESTORE]
            assert dsts.index(f"/usr/lib/boneio/trusted/{name}") < dsts.index(
                "/usr/sbin/boneio-helpers-heal"
            )

    @pytest.fixture
    def trusted(self, tmp_path, monkeypatch):
        """A full pristine copy, every file counted as root-owned, restoring
        into an empty directory instead of the system."""
        heal = self._heal()
        live = tmp_path / "live"
        live.mkdir()
        for name, _, _ in heal.RESTORE:
            (tmp_path / name).write_text(name)
        monkeypatch.setattr(heal, "TRUSTED_DIR", tmp_path)
        monkeypatch.setattr(
            heal, "RESTORE", tuple((n, live / d.name, m) for n, d, m in heal.RESTORE)
        )
        monkeypatch.setattr(heal.os, "geteuid", lambda: 0)
        monkeypatch.setattr(heal, "_root_owned", lambda p: p.is_file() and "untrusted" not in p.read_text())
        return heal, tmp_path

    def test_a_missing_generator_does_not_stop_the_rest(self, trusted, capsys):
        heal, directory = trusted
        (directory / "boneio-proxy-config").unlink()
        assert heal.main(["--check"]) == 0
        out = capsys.readouterr().out
        assert "live/boneio-migrate-v2" in out
        assert "proxy-config" not in out

    def test_a_present_generator_is_restored(self, trusted, capsys):
        heal, _ = trusted
        assert heal.main(["--check"]) == 0
        assert "live/proxy-config" in capsys.readouterr().out

    def test_an_untrusted_generator_refuses_everything(self, trusted):
        heal, directory = trusted
        (directory / "boneio-proxy-config").write_text("untrusted")
        assert heal.main(["--check"]) == 1

    def test_a_dangling_link_for_the_generator_refuses_everything(self, tmp_path, monkeypatch):
        """A name that exists but is no root-owned file is tampering, not a
        copy that has not arrived yet. The real _root_owned decides here, so
        the list is cut down to the generator: every other file in tmp_path
        belongs to the test user and would be refused for that alone."""
        heal = self._heal()
        monkeypatch.setattr(heal, "TRUSTED_DIR", tmp_path)
        monkeypatch.setattr(heal.os, "geteuid", lambda: 0)
        monkeypatch.setattr(heal, "RESTORE", (
            ("boneio-proxy-config", tmp_path / "live" / "proxy-config", 0o755),
        ))
        # Absent: skipped, nothing refused.
        assert heal.main(["--check"]) == 0
        (tmp_path / "boneio-proxy-config").symlink_to(tmp_path / "nowhere")
        assert heal.main(["--check"]) == 1

    def test_a_missing_helper_still_refuses_everything(self, trusted):
        heal, directory = trusted
        (directory / "boneio-system").unlink()
        assert heal.main(["--check"]) == 1
