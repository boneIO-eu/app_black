"""MigrationRunner — discovers, tracks and applies OS-level migrations.

Flow:
1.  At boneio startup ``MigrationRunner.startup_check()`` is called.
2.  It discovers all migration modules in ``boneio.migrations.versions``.
3.  It reads ``/var/lib/boneio/migrations.d/`` to find already-applied
    migration flags.
4.  If ``/usr/sbin/boneio-migrate`` exists it sends pending migration plans
    via stdin (JSON) and records the result flags.
5.  If the helper is **missing** it sets ``bootstrap_required = True``.
    The WebUI and MQTT discovery layer then prompts the user to authenticate
    once and install the helper.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import logging
import os
import pkgutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from boneio.migrations.actions import InstallFile, MigrationAction, render_template, sha256_of_content

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HELPER_PATH = "/usr/sbin/boneio-migrate"
APPLIED_DIR = Path("/var/lib/boneio/migrations.d")
ASSETS_DIR = Path(__file__).parent / "assets"
MANIFEST_PATH = ASSETS_DIR / "MANIFEST.sha256"
VERSIONS_PKG = "boneio.migrations.versions"
SUDOERS_MIGRATE_PATH = "/etc/sudoers.d/boneio-migrate"
BOOTSTRAP_HELPER_SRC = Path(__file__).parent / "bootstrap" / "boneio-migrate"
BOOTSTRAP_SUDOERS_SRC = Path(__file__).parent / "bootstrap" / "sudoers-migrate"
BOOTSTRAP_INSTALL_SCRIPT = Path(__file__).parent / "bootstrap" / "install-helper.sh"


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------


class MigrationStatus(StrEnum):
    """High-level migration subsystem status."""

    OK = "ok"
    BOOTSTRAP_REQUIRED = "bootstrap_required"
    PENDING = "pending"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Migration descriptor
# ---------------------------------------------------------------------------


@dataclass
class MigrationInfo:
    """Metadata about a single versioned migration module.

    Attributes:
        version: Semver-like string, e.g. ``"1.3.0"``.
        module_name: Full dotted module path.
        description: Human-readable description.
        requires_root: Whether ``boneio-migrate`` helper is needed.
    """

    version: str
    module_name: str
    description: str
    requires_root: bool = True

    def version_tuple(self) -> tuple[int, ...]:
        """Return version as comparable integer tuple."""
        try:
            return tuple(int(x) for x in self.version.split("."))
        except ValueError:
            return (0,)


# ---------------------------------------------------------------------------
# MigrationRunner
# ---------------------------------------------------------------------------


class MigrationRunner:
    """Discovers, tracks and applies boneio system migrations.

    Attributes:
        status: Current :class:`MigrationStatus`.
        bootstrap_required: True when the helper is not installed yet.
        pending_count: Number of migrations not yet applied.
        last_error: Last error message if status is ERROR.
    """

    def __init__(self) -> None:
        """Initialise the runner (does not apply anything yet)."""
        self.status: MigrationStatus = MigrationStatus.OK
        self.bootstrap_required: bool = False
        self.pending_count: int = 0
        self.last_error: str | None = None
        self._manifest: dict[str, str] = {}
        self._all_migrations: list[MigrationInfo] = []
        self._applied: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def startup_check(self) -> MigrationStatus:
        """Discover migrations, check helper, apply if possible.

        Returns:
            Current :class:`MigrationStatus` after the check.
        """
        try:
            self._load_manifest()
            self._discover_migrations()
            self._load_applied_flags()

            pending = self._get_pending()
            self.pending_count = len(pending)

            if not pending:
                _LOGGER.debug("No pending system migrations.")
                self.status = MigrationStatus.OK
                return self.status

            _LOGGER.info(
                "%d pending system migration(s): %s",
                len(pending),
                [m.version for m in pending],
            )

            if not self._helper_installed():
                _LOGGER.warning(
                    "boneio-migrate helper not found at %s. Bootstrap required — open WebUI to install.",
                    HELPER_PATH,
                )
                self.bootstrap_required = True
                self.status = MigrationStatus.BOOTSTRAP_REQUIRED
                return self.status

            self._ensure_helper_up_to_date()
            self._apply_pending(pending)

        except Exception as exc:
            _LOGGER.error("Migration startup_check failed: %s", exc, exc_info=True)
            self.last_error = str(exc)
            self.status = MigrationStatus.ERROR

        return self.status

    def apply_all(self, progress_callback: Any | None = None) -> bool:
        """Apply all pending migrations (called after bootstrap or by WebUI).

        Args:
            progress_callback: Optional callable(pct, msg) for progress updates.

        Returns:
            True if all pending migrations succeeded.
        """
        self._load_manifest()
        self._discover_migrations()
        self._load_applied_flags()
        pending = self._get_pending()

        if not pending:
            _LOGGER.info("No pending migrations to apply.")
            self.pending_count = 0
            self.status = MigrationStatus.OK
            return True

        self._ensure_helper_up_to_date()
        return self._apply_pending(pending, progress_callback=progress_callback)

    def get_status_dict(self) -> dict[str, Any]:
        """Return serialisable status dict for WebUI / MQTT.

        Returns:
            Dict with status, pending_count, applied list and last_error.
        """
        self._load_manifest()
        self._discover_migrations()
        self._load_applied_flags()
        pending = self._get_pending()

        # Build applied list with descriptions from discovered migrations
        migration_by_version = {m.version: m for m in self._all_migrations}
        applied_list = []
        for version in sorted(self._applied):
            migration = migration_by_version.get(version)
            applied_list.append(
                {
                    "version": version,
                    "description": migration.description if migration else "",
                    "module_name": migration.module_name if migration else "",
                }
            )

        return {
            "status": self.status.value,
            "bootstrap_required": self.bootstrap_required,
            "helper_installed": self._helper_installed(),
            "pending_count": len(pending),
            "pending": [{"version": m.version, "description": m.description} for m in pending],
            "applied": applied_list,
            "last_error": self.last_error,
        }

    def bootstrap_install(self, sudo_password: str) -> tuple[bool, str]:
        """Install the boneio-migrate helper using the user's sudo password.

        The password is passed via stdin to ``sudo -S`` and is never
        written to disk.

        Args:
            sudo_password: The system user's sudo password (boneio user).

        Returns:
            Tuple of (success: bool, message: str).
        """
        if not BOOTSTRAP_HELPER_SRC.exists():
            return False, f"Bootstrap helper source not found: {BOOTSTRAP_HELPER_SRC}"
        if not BOOTSTRAP_SUDOERS_SRC.exists():
            return False, f"Bootstrap sudoers source not found: {BOOTSTRAP_SUDOERS_SRC}"
        if not BOOTSTRAP_INSTALL_SCRIPT.exists():
            return False, f"Bootstrap install script not found: {BOOTSTRAP_INSTALL_SCRIPT}"

        cmd = [
            "sudo",
            "-S",
            "-k",
            "bash",
            str(BOOTSTRAP_INSTALL_SCRIPT),
            str(BOOTSTRAP_HELPER_SRC),
            str(BOOTSTRAP_SUDOERS_SRC),
        ]

        _LOGGER.info("Running bootstrap install of boneio-migrate helper...")
        try:
            result = subprocess.run(
                cmd,
                input=sudo_password + "\n",
                capture_output=True,
                text=True,
                timeout=30,
            )
        finally:
            # Clear password from local variable
            sudo_password = ""  # noqa: F841

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "unknown error").strip()
            _LOGGER.error("Bootstrap install failed: %s", err)
            return False, f"Bootstrap failed: {err}"

        if not self._helper_installed():
            return False, "Helper not found after install — check permissions."

        _LOGGER.info("boneio-migrate helper installed successfully.")
        self.bootstrap_required = False
        return True, "Helper installed successfully."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _helper_installed(self) -> bool:
        """Return True when the helper binary exists and is executable."""
        return os.path.isfile(HELPER_PATH) and os.access(HELPER_PATH, os.X_OK)

    def _ensure_helper_up_to_date(self) -> None:
        """Auto-update /usr/sbin/boneio-migrate if the bundled version differs.

        Compares SHA256 of the installed helper vs the one shipped in the
        package. If they differ, sends an ``install_file`` action to the
        currently installed helper to overwrite itself with the new version.
        This works because ``sudo -n /usr/sbin/boneio-migrate`` is already
        allowed in sudoers on all systems.
        """
        if not BOOTSTRAP_HELPER_SRC.exists():
            return
        if not self._helper_installed():
            return

        try:
            installed_hash = hashlib.sha256(
                Path(HELPER_PATH).read_bytes()
            ).hexdigest()
            bundled_hash = hashlib.sha256(
                BOOTSTRAP_HELPER_SRC.read_bytes()
            ).hexdigest()

            if installed_hash == bundled_hash:
                _LOGGER.debug("boneio-migrate helper is up to date.")
                return

            _LOGGER.info(
                "boneio-migrate helper outdated (installed=%s, bundled=%s). Updating...",
                installed_hash[:12],
                bundled_hash[:12],
            )

            # Copy the new helper to assets dir so install_file can find it
            update_asset = ASSETS_DIR / "_helper_update"
            update_asset.mkdir(parents=True, exist_ok=True)
            update_src = update_asset / "boneio-migrate"
            update_src.write_bytes(BOOTSTRAP_HELPER_SRC.read_bytes())

            # Send install_file action to the old helper to overwrite itself
            plan_payload = {
                "version": "_helper_update",
                "actions": [
                    {
                        "action": "install_file",
                        "src": "_helper_update/boneio-migrate",
                        "dst": HELPER_PATH,
                        "mode": 0o755,
                        "owner": "root",
                        "group": "root",
                        "template_vars": {},
                        "expected_sha256": bundled_hash,
                    }
                ],
                "assets_base": str(ASSETS_DIR),
            }

            result = subprocess.run(
                ["sudo", "-n", HELPER_PATH],
                input=json.dumps(plan_payload),
                capture_output=True,
                text=True,
                timeout=15,
            )

            # Clean up temp asset
            update_src.unlink(missing_ok=True)
            update_asset.rmdir()

            if result.returncode == 0:
                _LOGGER.info("boneio-migrate helper updated successfully.")
            else:
                _LOGGER.warning(
                    "Helper self-update failed (rc=%d): %s",
                    result.returncode,
                    result.stderr.strip(),
                )
        except Exception as exc:
            _LOGGER.warning("Could not check/update boneio-migrate helper: %s", exc)

    def _load_manifest(self) -> None:
        """Load MANIFEST.sha256 from the assets directory."""
        if not MANIFEST_PATH.exists():
            _LOGGER.warning("MANIFEST.sha256 not found at %s", MANIFEST_PATH)
            self._manifest = {}
            return

        manifest: dict[str, str] = {}
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                sha, rel_path = parts
                manifest[rel_path] = sha
        self._manifest = manifest
        _LOGGER.debug("Loaded %d entries from MANIFEST.sha256", len(manifest))

    def _discover_migrations(self) -> None:
        """Import all migration modules from ``boneio.migrations.versions``."""
        if self._all_migrations:
            return  # already discovered

        versions_path = Path(__file__).parent / "versions"
        if not versions_path.is_dir():
            _LOGGER.warning("Migration versions directory not found: %s", versions_path)
            return

        migrations: list[MigrationInfo] = []

        for _, module_name, _ in pkgutil.iter_modules([str(versions_path)]):
            full_name = f"{VERSIONS_PKG}.{module_name}"
            try:
                mod = importlib.import_module(full_name)
                version = getattr(mod, "VERSION", None)
                description = getattr(mod, "DESCRIPTION", module_name)
                requires_root = getattr(mod, "REQUIRES_ROOT", True)

                if version is None:
                    _LOGGER.warning("Migration module %s has no VERSION, skipping.", full_name)
                    continue

                migrations.append(
                    MigrationInfo(
                        version=version,
                        module_name=full_name,
                        description=description,
                        requires_root=requires_root,
                    )
                )
            except Exception as exc:
                _LOGGER.error("Failed to import migration module %s: %s", full_name, exc)

        # Sort by version ascending
        migrations.sort(key=lambda m: m.version_tuple())
        self._all_migrations = migrations
        _LOGGER.debug("Discovered %d migration(s).", len(migrations))

    def _load_applied_flags(self) -> None:
        """Read applied migration flags from APPLIED_DIR."""
        applied: set[str] = set()
        if APPLIED_DIR.is_dir():
            for p in APPLIED_DIR.glob("*.applied"):
                applied.add(p.stem)
        self._applied = applied
        _LOGGER.debug("Applied migrations: %s", applied)

    def _get_pending(self) -> list[MigrationInfo]:
        """Return migrations not yet applied."""
        return [m for m in self._all_migrations if m.version not in self._applied]

    def _apply_pending(
        self,
        pending: list[MigrationInfo],
        progress_callback: Any | None = None,
    ) -> bool:
        """Apply a list of pending migrations via boneio-migrate helper.

        Args:
            pending: List of migrations to apply, in order.
            progress_callback: Optional callable(pct, msg).

        Returns:
            True if all succeeded.
        """
        total = len(pending)
        all_ok = True

        for idx, migration in enumerate(pending):
            pct = int((idx / total) * 100)
            msg = f"Applying migration {migration.version}: {migration.description}"
            _LOGGER.info(msg)
            if progress_callback:
                progress_callback(pct, msg)

            ok = self._apply_one(migration)
            if not ok:
                _LOGGER.error("Migration %s failed, stopping.", migration.version)
                self.last_error = f"Migration {migration.version} failed"
                self.status = MigrationStatus.ERROR
                all_ok = False
                break

        if all_ok:
            self.pending_count = 0
            self.status = MigrationStatus.OK
            _LOGGER.info("All pending migrations applied successfully.")

        return all_ok

    def _apply_one(self, migration: MigrationInfo) -> bool:
        """Apply a single migration via the helper.

        Args:
            migration: Migration descriptor.

        Returns:
            True on success.
        """
        mod = importlib.import_module(migration.module_name)
        plan_fn = getattr(mod, "plan", None)
        if plan_fn is None:
            _LOGGER.error("Migration %s has no plan() function.", migration.module_name)
            return False

        actions: list[MigrationAction] = plan_fn()

        # Inject SHA256 from manifest into InstallFile actions
        enriched = self._inject_sha256(actions)

        plan_payload = {
            "version": migration.version,
            "actions": [a.to_dict() for a in enriched],
            "assets_base": str(ASSETS_DIR),
        }

        payload_json = json.dumps(plan_payload)

        try:
            result = subprocess.run(
                ["sudo", "-n", HELPER_PATH],
                input=payload_json,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            _LOGGER.error("Migration %s timed out.", migration.version)
            return False
        except Exception as exc:
            _LOGGER.error("Migration %s subprocess error: %s", migration.version, exc)
            return False

        if result.returncode != 0:
            _LOGGER.error(
                "Migration %s failed (rc=%d): %s",
                migration.version,
                result.returncode,
                result.stderr.strip(),
            )
            return False

        # Record success flag
        self._write_applied_flag(migration)
        self._applied.add(migration.version)
        _LOGGER.info("Migration %s applied successfully.", migration.version)
        return True

    def _inject_sha256(self, actions: list[MigrationAction]) -> list[MigrationAction]:
        """Inject ``expected_sha256`` from MANIFEST into InstallFile actions.

        Args:
            actions: List of actions from a migration plan.

        Returns:
            Same list with sha256 injected into InstallFile entries.
        """
        for action in actions:
            if isinstance(action, InstallFile):
                # Compute manifest key: src is relative to assets/
                manifest_key = action.src
                if manifest_key in self._manifest:
                    action.expected_sha256 = self._manifest[manifest_key]
                else:
                    _LOGGER.warning(
                        "Asset '%s' not found in MANIFEST.sha256 — skipping sha256 check.",
                        action.src,
                    )
        return actions

    def _write_applied_flag(self, migration: MigrationInfo) -> None:
        """Write a .applied flag file for a successfully applied migration.

        Note: The flag is written by the helper (root-owned). This method
        is called if the helper writes stdout confirming success. If the
        directory is not writable by the boneio user we skip silently —
        the helper is responsible for writing the flag.

        Args:
            migration: The migration that was applied.
        """
        # Applied flags are written by boneio-migrate helper (as root).
        # We reload from disk to pick them up.
        self._load_applied_flags()
