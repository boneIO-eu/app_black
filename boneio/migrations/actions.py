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
