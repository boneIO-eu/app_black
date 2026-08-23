"""Migration action types for boneio-migrate.

All actions are declarative and serialisable to JSON so that the
unprivileged ``boneio`` user can send them to the privileged
``/usr/sbin/boneio-migrate`` helper via stdin.

Each action is idempotent: it checks whether the target already matches
before writing/enabling, so running a migration twice is safe.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from string import Template
from typing import Any

# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


@dataclass
class MigrationAction:
    """Base class for all migration actions."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize action to a dict for JSON transfer to boneio-migrate."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MigrationAction:
        """Deserialize action from dict (used inside boneio-migrate)."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# File installation
# ---------------------------------------------------------------------------


@dataclass
class InstallFile(MigrationAction):
    """Install a file from the package assets to a system path.

    Args:
        src: Relative path inside ``boneio/migrations/assets/``.
        dst: Absolute destination path on the system.
        mode: File permission bits (e.g. 0o755).
        owner: File owner username (default: root).
        group: File group name (default: root).
        template_vars: Optional dict of ``${KEY}`` substitutions applied to
            the file content via :class:`string.Template` before writing.
        validate_cmd: Optional shell command that receives the destination path
            as its last argument (e.g. ``"visudo -cf"``). Run after write.
        on_change: Action to perform when the file actually changed (was
            written, not skipped because hash matched). Serialised as a nested
            dict so the helper can execute it.
        expected_sha256: SHA-256 of the *rendered* content (after template
            substitution). Injected by MigrationRunner from MANIFEST.sha256.
            The helper validates this before writing.
    """

    src: str
    dst: str
    mode: int = 0o644
    owner: str = "root"
    group: str = "root"
    template_vars: dict[str, str] = field(default_factory=dict)
    validate_cmd: str | None = None
    on_change: MigrationAction | None = None
    expected_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        d: dict[str, Any] = {
            "action": "install_file",
            "src": self.src,
            "dst": self.dst,
            "mode": self.mode,
            "owner": self.owner,
            "group": self.group,
            "template_vars": self.template_vars,
        }
        if self.validate_cmd:
            d["validate_cmd"] = self.validate_cmd
        if self.on_change:
            d["on_change"] = self.on_change.to_dict()
        if self.expected_sha256:
            d["expected_sha256"] = self.expected_sha256
        return d


# ---------------------------------------------------------------------------
# Systemctl actions
# ---------------------------------------------------------------------------


@dataclass
class SystemctlDaemonReload(MigrationAction):
    """Run ``systemctl daemon-reload``."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {"action": "systemctl_daemon_reload"}


@dataclass
class SystemctlEnable(MigrationAction):
    """Enable a systemd unit (idempotent).

    Args:
        unit: Unit name, e.g. ``"boneio-oled-boot.service"``.
    """

    unit: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {"action": "systemctl_enable", "unit": self.unit}


@dataclass
class SystemctlDisable(MigrationAction):
    """Disable a systemd unit (idempotent).

    Args:
        unit: Unit name.
    """

    unit: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {"action": "systemctl_disable", "unit": self.unit}


@dataclass
class SystemctlRestart(MigrationAction):
    """Restart a systemd service.

    Args:
        unit: Unit name.
    """

    unit: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {"action": "systemctl_restart", "unit": self.unit}


@dataclass
class SystemctlReload(MigrationAction):
    """Reload a systemd service.

    Args:
        unit: Unit name.
    """

    unit: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {"action": "systemctl_reload", "unit": self.unit}


# ---------------------------------------------------------------------------
# File removal
# ---------------------------------------------------------------------------


@dataclass
class RemoveFile(MigrationAction):
    """Remove a file from the system (no-op if it does not exist).

    Args:
        path: Absolute path to remove.
    """

    path: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {"action": "remove_file", "path": self.path}


# ---------------------------------------------------------------------------
# Append a line if missing
# ---------------------------------------------------------------------------


@dataclass
class AppendLineIfMissing(MigrationAction):
    """Append ``line`` to ``path`` if the exact line is not already present.

    Useful for ``/boot/uEnv.txt`` overlays.

    Args:
        path: Absolute path to the text file.
        line: Exact line to append (without trailing newline).
    """

    path: str
    line: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {"action": "append_line_if_missing", "path": self.path, "line": self.line}


# ---------------------------------------------------------------------------
# UFW firewall rules
# ---------------------------------------------------------------------------


@dataclass
class UfwAllow(MigrationAction):
    """Allow a port/protocol through UFW firewall (idempotent).

    Runs ``ufw allow <port>/<proto> comment <comment>`` only if the rule
    is not already present in ``ufw status``.

    Args:
        port: Port number to allow.
        proto: Protocol (``"tcp"``, ``"udp"``, or ``"any"``).
        comment: Human-readable comment stored in UFW rules.
    """

    port: int
    proto: str = "udp"
    comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        d: dict[str, Any] = {
            "action": "ufw_allow",
            "port": self.port,
            "proto": self.proto,
        }
        if self.comment:
            d["comment"] = self.comment
        return d


# ---------------------------------------------------------------------------
# Package installation
# ---------------------------------------------------------------------------


@dataclass
class AptInstall(MigrationAction):
    """Install Debian packages with apt (idempotent).

    Packages that are already installed are skipped, so nothing happens on
    a second run. Package names are validated by the helper against a strict
    pattern to keep the privileged helper safe.

    Args:
        packages: List of package names to install.
        optional: When True a failure (e.g. no network) is logged as a
            warning and the migration continues instead of aborting.
    """

    packages: list[str]
    optional: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "action": "apt_install",
            "packages": list(self.packages),
            "optional": self.optional,
        }


@dataclass
class PipInstallWheel(MigrationAction):
    """Install a wheel bundled in the migration assets into a virtualenv.

    pip runs as *run_as* (never as root) so the virtualenv keeps its original
    ownership. The wheel content is verified against ``expected_sha256``
    before installation.

    Args:
        wheel: Path of the wheel relative to ``boneio/migrations/assets/``.
        python: Absolute path of the target interpreter (the venv python).
        run_as: Unprivileged user that owns the virtualenv.
        expected_sha256: SHA-256 of the wheel, injected from MANIFEST.sha256.
        skip_if: Python expression evaluated with the target interpreter;
            when it evaluates truthy the installation is skipped.
        verify: Python expression evaluated with the target interpreter after
            the installation; must be truthy or the action fails.
        optional: When True a failure is logged as a warning and the
            migration continues.
    """

    wheel: str
    python: str
    run_as: str
    expected_sha256: str | None = None
    skip_if: str | None = None
    verify: str | None = None
    optional: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        d: dict[str, Any] = {
            "action": "pip_install_wheel",
            "wheel": self.wheel,
            "python": self.python,
            "run_as": self.run_as,
            "optional": self.optional,
        }
        if self.expected_sha256:
            d["expected_sha256"] = self.expected_sha256
        if self.skip_if:
            d["skip_if"] = self.skip_if
        if self.verify:
            d["verify"] = self.verify
        return d


# ---------------------------------------------------------------------------
# AppArmor
# ---------------------------------------------------------------------------


@dataclass
class DisableApparmorProfiles(MigrationAction):
    """Disable AppArmor profiles not needed on a headless controller.

    Debian's ``apparmor`` package ships ~106 profiles in ``/etc/apparmor.d``,
    almost entirely for desktop software — browsers, Discord, Slack, Steam,
    1Password, MongoDB Compass, Xorg, plasmashell, and the sbuild/lxc tool
    families. ``apparmor.service`` loads all of them at boot, which measured
    11.4 s on a BeagleBone Black and sat ahead of ``networking.service`` on the
    critical path.

    Expressed as a keep-list so that a future apparmor package adding more
    desktop profiles cannot silently reintroduce the cost.

    Profiles are disabled via symlinks in ``/etc/apparmor.d/disable/`` — the
    mechanism ``apparmor_parser`` honours natively. Files are never deleted,
    since they belong to the apparmor package and would return on every upgrade.
    Reversible by removing the symlinks.

    Args:
        keep: Profile basenames to leave enabled. Everything else in
            ``/etc/apparmor.d`` is disabled.
    """

    keep: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {"action": "disable_apparmor_profiles", "keep": self.keep}


# ---------------------------------------------------------------------------
# Journal housekeeping
# ---------------------------------------------------------------------------


@dataclass
class PruneOrphanedJournalDirs(MigrationAction):
    """Delete journal directories whose machine-id is not the current one.

    ``/var/log/journal/`` and log2ram's disk copy contain one subdirectory per
    machine-id. journald only ever manages the directory matching
    ``/etc/machine-id``, so any other one is invisible to
    ``journalctl --vacuum-*`` and to ``SystemMaxUse`` — it is never cleaned.

    They accumulate because the image pipeline truncates ``/etc/machine-id``
    (setup_boneio.sh, and the eMMC flasher), so a new one is generated on the
    next boot while the previous journal directory stays behind. A controller
    examined in the field had **nine** of them.

    That matters because log2ram rsyncs the whole tree on every boot, so every
    reflash permanently adds to boot time.

    Only directories whose name looks like a machine-id (32 hex characters) and
    differs from the current one are removed, so nothing else under
    ``journal/`` is touched.
    """

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {"action": "prune_orphaned_journal_dirs"}


# ---------------------------------------------------------------------------
# Helper utilities (used by runner, not sent to boneio-migrate)
# ---------------------------------------------------------------------------


def sha256_of_content(content: bytes) -> str:
    """Return lower-case hex SHA-256 of *content*."""
    return hashlib.sha256(content).hexdigest()


def render_template(content: str, template_vars: dict[str, str]) -> str:
    """Apply ``${KEY}`` substitutions to *content*.

    Args:
        content: Raw file content string.
        template_vars: Mapping of variable names to values.

    Returns:
        Rendered content with substitutions applied.
    """
    if not template_vars:
        return content
    return Template(content).safe_substitute(template_vars)
