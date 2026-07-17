"""Update manager for checking and publishing software updates to Home Assistant.

This module manages periodic checking of software updates from GitHub
and publishes the update status to Home Assistant via MQTT.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from boneio.core.utils.async_updater import AsyncUpdater
from boneio.core.utils.timeperiod import TimePeriod
from boneio.version import __version__
from boneio.webui.services.logs import is_running_as_service

# Flag file created before restart so the new process knows it was an update
UPDATE_FLAG_PATH = Path("/tmp/boneio_update_in_progress")

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


class UpdateManager(AsyncUpdater):
    """Manages software update checking and MQTT publishing.

    This manager:
    - Checks for updates from GitHub periodically (default: 4 hours)
    - Caches results to avoid rate limiting
    - Publishes update state to MQTT for Home Assistant
    - Supports on-demand update checks from frontend
    """

    def __init__(
        self,
        manager: Manager,
        update_interval: TimePeriod | None = None,
    ):
        """Initialize UpdateManager.

        Args:
            manager: Parent Manager instance
            update_interval: Time between update checks (default: 4 hours)
        """
        self.id = "update_manager"
        self._manager = manager

        # Update check interval (default: 4 hours)
        if update_interval is None:
            update_interval = TimePeriod(hours=4)

        # Cache for update info to avoid excessive GitHub API calls
        self._last_check_result: dict | None = None
        self._last_published_state: str | None = None
        self._ha_discovery_sent: bool = False
        self._update_running: bool = False

        # Initialize AsyncUpdater (starts periodic task)
        super().__init__(manager=manager, update_interval=update_interval)

        _LOGGER.info("UpdateManager initialized (check interval: %s)", update_interval)

    async def async_update(self, timestamp: float) -> float | None:
        """Perform periodic update check.

        Args:
            timestamp: Current timestamp

        Returns:
            Optional custom update interval in seconds
        """
        # Send HA discovery on first update (MQTT is connected by then)
        if not self._ha_discovery_sent:
            await self.send_ha_autodiscovery()
            self._ha_discovery_sent = True

        _LOGGER.debug("Checking for software updates...")

        try:
            # Check for updates from GitHub
            update_info = await self._check_update_from_github()

            if update_info and update_info.get("status") == "success":
                # Publish state to MQTT
                await self._publish_state_to_mqtt(update_info)
            else:
                _LOGGER.warning(
                    "Update check failed: %s",
                    update_info.get("message", "Unknown error") if update_info else "No response",
                )
        except Exception as e:
            _LOGGER.error("Error during update check: %s", e, exc_info=True)

        # Return None to use default interval
        return None

    async def _check_update_from_github(self) -> dict | None:
        """Check for updates from GitHub releases.

        Uses the shared cached fetch to avoid exhausting the
        unauthenticated GitHub API rate limit (60 req/h per IP).

        Returns:
            Update information dict or None on error
        """
        current_version = __version__

        try:
            from packaging import version
        except ImportError:
            _LOGGER.error("Package 'packaging' is not installed")
            return {
                "status": "error",
                "message": "Package 'packaging' is not installed",
                "current_version": current_version,
            }

        try:
            from boneio.webui.routes.update import _fetch_github_releases

            releases, error = _fetch_github_releases()

            if error:
                return {"status": "error", "message": error, "current_version": current_version}

            if not releases:
                return {"status": "error", "message": "No releases found on GitHub", "current_version": current_version}

            # Find latest stable and prerelease versions
            # GitHub API does NOT guarantee ordering by version — must compare
            latest_stable = None
            latest_stable_parsed = None
            latest_prerelease = None
            latest_prerelease_parsed = None

            for release in releases:
                tag = release["tag_name"]
                ver_str = tag[1:] if tag.startswith("v") else tag

                # Skip v0.x versions (Debian 10, incompatible)
                if tag.startswith("v0."):
                    continue

                is_prerelease = release.get("prerelease", False)

                if not is_prerelease:
                    ver_lower = ver_str.lower()
                    is_prerelease = any(x in ver_lower for x in ["dev", "alpha", "beta", "rc"])

                try:
                    parsed = version.parse(ver_str)
                except Exception:
                    continue

                ver_info = {
                    "version": ver_str,
                    "is_prerelease": is_prerelease,
                    "release_url": release["html_url"],
                    "published_at": release["published_at"],
                    "release_notes": release.get("body", "")[:255],  # Max 255 chars for HA
                }

                if not is_prerelease:
                    if latest_stable_parsed is None or parsed > latest_stable_parsed:
                        latest_stable = ver_info
                        latest_stable_parsed = parsed
                else:
                    if latest_prerelease_parsed is None or parsed > latest_prerelease_parsed:
                        latest_prerelease = ver_info
                        latest_prerelease_parsed = parsed

            # Determine which version to recommend based on update_channel setting
            update_channel = self._manager._config_helper.update_channel
            current_ver_lower = current_version.lower()
            current_is_prerelease = any(x in current_ver_lower for x in ["dev", "alpha", "beta", "rc"])

            # Check if update is available
            is_update_available = False
            recommended = None
            try:
                current_parsed = version.parse(current_version)

                # Build candidate list based on update_channel
                # - Stable channel: only stable releases
                # - Dev channel: both stable and prerelease
                # - Always: if currently on prerelease, stable is a valid upgrade
                candidates = []
                if latest_stable:
                    stable_parsed = version.parse(latest_stable["version"])
                    if stable_parsed > current_parsed:
                        candidates.append((stable_parsed, latest_stable))

                if (update_channel == "dev" or current_is_prerelease) and latest_prerelease:
                    pre_parsed = version.parse(latest_prerelease["version"])
                    if pre_parsed > current_parsed:
                        candidates.append((pre_parsed, latest_prerelease))

                if candidates:
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    recommended = candidates[0][1]
                    is_update_available = True
            except Exception as e:
                _LOGGER.warning("Error parsing versions: %s", e)

            if recommended is None:
                if update_channel == "dev":
                    recommended = latest_prerelease or latest_stable
                else:
                    recommended = latest_stable

            if not recommended:
                return {"status": "error", "message": "No suitable release found", "current_version": current_version}

            result = {
                "status": "success",
                "current_version": current_version,
                "latest_version": recommended["version"],
                "update_available": is_update_available,
                "release_url": recommended["release_url"],
                "release_notes": recommended.get("release_notes", ""),
                "is_prerelease": recommended["is_prerelease"],
            }

            # Cache result
            self._last_check_result = result

            return result

        except Exception as e:
            _LOGGER.error("Error checking for updates: %s", e, exc_info=True)
            return {"status": "error", "message": f"Error: {str(e)}", "current_version": current_version}

    async def _publish_state_to_mqtt(self, update_info: dict) -> None:
        """Publish update state to MQTT for Home Assistant.

        Includes pending system migration details in the release summary
        so the user is aware of pending changes directly from HA.

        Args:
            update_info: Update information from GitHub check
        """
        if update_info.get("status") != "success":
            return

        current_version = update_info.get("current_version", __version__)
        latest_version = update_info.get("latest_version", current_version)

        # Build release summary with optional migration info
        release_summary = update_info.get("release_notes", "")

        migration_note = self._get_migration_summary()
        if migration_note:
            # Prepend migration info to release notes
            release_summary = f"{migration_note}\n{release_summary}" if release_summary else migration_note

        # Build state payload (JSON format for HA Update entity)
        # Always include in_progress/update_percentage to clear any retained
        # progress state left by a previous update (e.g., after restart).
        state_payload = {
            "installed_version": current_version,
            "latest_version": latest_version,
            "title": "boneIO Black Firmware",
            "release_url": update_info.get("release_url", ""),
            "release_summary": release_summary[:255],  # HA limit
            "entity_picture": "http://boneio.eu/logo_fb_circle.png",
            "in_progress": False,
            "update_percentage": None,
        }

        # Convert to JSON
        payload_json = json.dumps(state_payload)

        # Only publish if state changed (avoid unnecessary MQTT traffic)
        if payload_json == self._last_published_state:
            _LOGGER.debug("Update state unchanged, skipping MQTT publish")
            return

        # Publish to MQTT
        topic_prefix = self._manager._config_helper.topic_prefix
        state_topic = f"{topic_prefix}/update/state"

        self._manager.send_message(
            topic=state_topic,
            payload=payload_json,
            retain=True,
        )

        self._last_published_state = payload_json

        _LOGGER.info(
            "Published update state to MQTT: %s -> %s (update available: %s)",
            current_version,
            latest_version,
            update_info.get("update_available", False),
        )

    def _get_migration_summary(self) -> str:
        """Build a short summary of pending system migrations.

        Returns:
            Human-readable string for HA release_summary, or empty if none pending.
        """
        migration_runner = getattr(self._manager, "migration_runner", None)
        if not migration_runner:
            return ""

        try:
            pending = migration_runner._get_pending()
        except Exception:
            return ""

        if not pending:
            return ""

        descriptions = ", ".join(m.description for m in pending[:3])
        suffix = f" (+{len(pending) - 3} more)" if len(pending) > 3 else ""
        return f"⚠️ {len(pending)} pending system migration(s): {descriptions}{suffix}"

    def get_last_check_result(self) -> dict | None:
        """Get the last update check result.

        Returns:
            Last check result dict or None if no check performed yet
        """
        return self._last_check_result

    @property
    def update_running(self) -> bool:
        """Whether an update is currently in progress."""
        return self._update_running

    async def handle_install_command(self, payload: str) -> None:
        """Handle install command from Home Assistant.

        This is called when HA sends a message to the command topic.
        Performs pip install of the latest version and restarts the service.

        Args:
            payload: MQTT payload (should be "INSTALL")
        """
        if payload != "INSTALL":
            _LOGGER.warning("Invalid install command payload: %s", payload)
            return

        _LOGGER.info("Received install command from Home Assistant")

        if not is_running_as_service():
            _LOGGER.warning("Update via MQTT is only available when running as a service")
            return

        if self._update_running:
            _LOGGER.warning("Update already in progress, ignoring install command")
            return

        # Block update if migration bootstrap is required
        migration_runner = getattr(self._manager, "migration_runner", None)
        if migration_runner and migration_runner.bootstrap_required:
            _LOGGER.warning(
                "Cannot install update: system migration bootstrap required. "
                "Open the WebUI and complete the migration bootstrap first."
            )
            await self._publish_bootstrap_required_state()
            return

        # Check if update is available
        if not self._last_check_result:
            _LOGGER.warning("No update check result available, checking now...")
            await self.async_update(timestamp=0)

        if not self._last_check_result or not self._last_check_result.get("update_available"):
            _LOGGER.warning("No update available to install")
            return

        target_version = self._last_check_result.get("latest_version")

        # Run update in background task to not block MQTT
        asyncio.create_task(self.perform_update(target_version=target_version))

    async def perform_update(
        self,
        target_version: str | None = None,
        on_progress: Callable[[int, str, str | None], None] | None = None,
    ) -> None:
        """Perform the actual update: pip install + restart.

        This is the single update algorithm used by both MQTT (HA) and WebUI.

        Handles pre-release versions by adding --pre flag.
        Retries up to 3 times with 30s delay if pip install fails
        (PyPI index may not have the version available immediately).

        Args:
            target_version: Version to install, or None for latest.
            on_progress: Optional callback(progress_pct, step, log_msg).
                         Called at each stage so the caller can track progress.
                         If None, only MQTT progress is published.
        """
        if self._update_running:
            _LOGGER.warning("Update already in progress")
            return

        self._update_running = True
        current_version = __version__
        _LOGGER.info("Starting update from %s to %s", current_version, target_version or "latest")

        async def _report(progress: int, step: str, log_msg: str | None = None) -> None:
            """Report progress to both MQTT and optional callback."""
            await self._publish_update_progress(
                current_version=current_version,
                target_version=target_version,
                progress=progress,
            )
            if on_progress:
                on_progress(progress, step, log_msg)

        try:
            await _report(5, "Finding virtual environment...")

            # Find virtual environment
            possible_venv_paths = [
                os.path.expanduser("~/boneio/venv"),
                os.path.expanduser("~/venv"),
                "/opt/boneio/venv",
            ]

            pip_path = None
            venv_path = None
            for path in possible_venv_paths:
                pip_candidate = os.path.join(path, "bin", "pip")
                if os.path.exists(pip_candidate):
                    venv_path = path
                    pip_path = pip_candidate
                    _LOGGER.info("Found venv pip at %s", pip_path)
                    break

            if not pip_path:
                _LOGGER.error("Virtual environment not found, cannot update")
                await _report(0, "Failed", "Could not find virtual environment")
                return

            await _report(10, "Virtual environment found", f"Using venv at {venv_path}")
            await _report(15, "Preparing update...", f"Current version: {current_version}")
            await _report(30, "Upgrading pip...")

            # Upgrade pip first
            pip_upgrade = subprocess.run(
                [pip_path, "install", "--upgrade", "pip"], capture_output=True, text=True, timeout=120
            )

            if pip_upgrade.returncode == 0:
                await _report(40, "Pip upgraded", "pip upgraded successfully")
            else:
                await _report(40, "Pip upgrade skipped", "pip upgrade failed, continuing...")

            # Build pip install command
            pip_cmd = [pip_path, "install", "--upgrade"]

            # Add --pre flag for pre-release versions (dev, alpha, beta, rc)
            needs_pre = False
            if (
                target_version
                and self._is_prerelease_version(target_version)
                or not target_version
                and self._is_prerelease_version(current_version)
            ):
                needs_pre = True

            if needs_pre:
                pip_cmd.append("--pre")
                await _report(42, "Using --pre flag", "Pre-release version detected")

            if target_version:
                pip_package = f"boneio=={target_version}"
            else:
                pip_package = "boneio"

            pip_cmd.append(pip_package)

            await _report(45, f"Downloading and installing {pip_package}...")

            # Retry logic: PyPI may not have the version available immediately
            max_retries = 3
            retry_delay = 30  # seconds
            result = None

            for attempt in range(1, max_retries + 1):
                await _report(
                    45 + (attempt - 1) * 10,
                    f"Installing (attempt {attempt}/{max_retries})...",
                    f"Running: {' '.join(pip_cmd)}",
                )

                result = subprocess.run(pip_cmd, capture_output=True, text=True, timeout=300)

                if result.returncode == 0:
                    break

                _LOGGER.warning("pip install attempt %d/%d failed: %s", attempt, max_retries, result.stderr.strip())

                if attempt < max_retries:
                    await _report(
                        45 + attempt * 10,
                        f"Retrying in {retry_delay}s...",
                        f"Attempt {attempt} failed, PyPI index may not be ready",
                    )
                    await asyncio.sleep(retry_delay)

            if not result or result.returncode != 0:
                error_msg = result.stderr.strip() if result else "Unknown error"
                _LOGGER.error("pip install failed after %d attempts: %s", max_retries, error_msg)
                await _report(0, "Update failed", error_msg)
                return

            await _report(80, "BoneIO updated", "Package installed successfully")
            await _report(85, "Verifying installation...")

            # Verify installed version
            version_result = subprocess.run([pip_path, "show", "boneio"], capture_output=True, text=True)
            new_version = current_version
            if version_result.returncode == 0:
                for line in version_result.stdout.split("\n"):
                    if line.startswith("Version:"):
                        new_version = line.split(":")[1].strip()
                        break

            _LOGGER.info("Update successful: %s -> %s. Restarting in 2 seconds...", current_version, new_version)

            await _report(90, "Installation verified", f"Updated from {current_version} to {new_version}")
            await _report(95, "Finalizing...")

            # Keep in_progress=true as retained so HA shows "Updating"
            # even during the restart window. The new process will clear
            # this via _check_post_update_flag() on startup.
            await self._publish_update_progress(
                current_version=current_version,
                target_version=new_version,
                progress=95,
            )

            # Write a flag file so the new process knows to immediately
            # publish "up to date" on startup.
            try:
                UPDATE_FLAG_PATH.write_text(new_version, encoding="utf-8")
            except OSError:
                _LOGGER.warning("Could not write update flag file at %s", UPDATE_FLAG_PATH)

            if on_progress:
                on_progress(100, "Update complete!", "Restarting service in 2 seconds...")

            # Wait long enough for MQTT to drain the retained in_progress
            # message before killing the process.
            await asyncio.sleep(5)

            _LOGGER.info("Restarting BoneIO service after update...")
            os._exit(0)

        except subprocess.TimeoutExpired:
            _LOGGER.error("Update process timed out")
            await _report(0, "Timeout", "Update process timed out")
        except Exception as e:
            _LOGGER.error("Error during update: %s", e, exc_info=True)
            await _report(0, "Error", f"Unexpected error: {e}")
        finally:
            self._update_running = False

    @staticmethod
    def _is_prerelease_version(version_str: str) -> bool:
        """Check if version string is a pre-release (dev, alpha, beta, rc).

        Args:
            version_str: Version string to check

        Returns:
            True if version is a pre-release
        """
        ver_lower = version_str.lower()
        return any(x in ver_lower for x in ["dev", "alpha", "beta", "rc"])

    async def _publish_update_progress(
        self,
        current_version: str,
        target_version: str | None,
        progress: int,
    ) -> None:
        """Publish update progress state to MQTT for HA.

        HA update entity supports in_progress as:
        - false/0: not updating
        - true: updating (indeterminate)
        - int 1-100: updating with progress percentage

        Args:
            current_version: Currently installed version
            target_version: Version being installed (None if not updating)
            progress: Update progress percentage (0 = not updating, 1-100 = in progress)
        """
        # HA update entity progress:
        # - in_progress: boolean (true = updating, false = idle)
        # - update_percentage: float 0-100 (shows progress bar in HA UI)
        is_updating = progress > 0

        state_payload = {
            "installed_version": current_version,
            "latest_version": target_version or current_version,
            "title": "boneIO Black Firmware",
            "release_url": self._last_check_result.get("release_url", "") if self._last_check_result else "",
            "release_summary": self._last_check_result.get("release_notes", "") if self._last_check_result else "",
            "entity_picture": "http://boneio.eu/logo_fb_circle.png",
            "in_progress": is_updating,
            "update_percentage": float(progress) if is_updating else None,
        }

        topic_prefix = self._manager._config_helper.topic_prefix
        self._manager.send_message(
            topic=f"{topic_prefix}/update/state",
            payload=json.dumps(state_payload),
            retain=True,
        )

        _LOGGER.debug("Published update progress: %d%%", progress)

    async def _publish_bootstrap_required_state(self) -> None:
        """Publish a special update state indicating migration bootstrap is required.

        This informs Home Assistant that the update cannot proceed until the user
        completes the one-time migration bootstrap via the WebUI.
        """
        current_version = __version__
        state_payload = {
            "installed_version": current_version,
            "latest_version": current_version,
            "title": "boneIO Black Firmware",
            "release_url": "",
            "release_summary": (
                "System migration bootstrap required. Open the BoneIO WebUI → System → Migrations to complete setup."
            ),
            "entity_picture": "http://boneio.eu/logo_fb_circle.png",
            "in_progress": False,
            "update_percentage": None,
        }
        topic_prefix = self._manager._config_helper.topic_prefix
        self._manager.send_message(
            topic=f"{topic_prefix}/update/state",
            payload=json.dumps(state_payload),
            retain=True,
        )

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for Update and Migration Alert entities."""
        from boneio.integration.homeassistant import ha_update_availability_message

        _LOGGER.debug("Sending HA autodiscovery for Update entity")
        payload = ha_update_availability_message(
            id="firmware",
            name="Update",
            config_helper=self._manager._config_helper,
        )
        self._manager.publish_ha_discovery(
            id="firmware",
            ha_type="update",
            payload=payload,
        )

        # Subscribe to command topic for install commands
        command_topic = f"{self._manager._topic_prefix}/update/install"
        await self._manager._message_bus.subscribe_and_listen(
            topic=command_topic, callback=self._manager._handle_update_install_command
        )
        _LOGGER.info("Subscribed to update command topic: %s", command_topic)

        # If we just restarted after an update, immediately clear the
        # retained in_progress state so HA transitions from "Updating"
        # to "Up to date" as fast as possible.
        await self._check_post_update_flag()

        # Migration alert event entity — fires when system migrations are pending
        await self._send_migration_event_discovery()
        await self._fire_migration_event_if_pending()

    async def _check_post_update_flag(self) -> None:
        """Check if we just restarted after a firmware update.

        If the flag file exists, publish an immediate 'up to date' state
        to clear the retained ``in_progress: true`` message left by the
        previous process before it called ``os._exit()``.  This minimises
        the window in which HA shows "unavailable" for the update entity.
        """
        if not UPDATE_FLAG_PATH.exists():
            return

        try:
            new_version = UPDATE_FLAG_PATH.read_text(encoding="utf-8").strip()
            UPDATE_FLAG_PATH.unlink(missing_ok=True)
        except OSError as exc:
            _LOGGER.warning("Failed to read/remove update flag: %s", exc)
            return

        _LOGGER.info(
            "Post-update restart detected (updated to %s). "
            "Publishing 'up to date' state to clear retained in_progress.",
            new_version,
        )

        # Publish idle state with the new version
        await self._publish_update_progress(
            current_version=new_version,
            target_version=None,
            progress=0,
        )

    async def _send_migration_event_discovery(self) -> None:
        """Register HA binary_sensor (diagnostic) for system migration alerts.

        The sensor is ON when pending migrations are detected at startup,
        OFF when all migrations have been applied.  Attributes include
        ``count`` and ``description`` of pending migrations.

        Also removes the legacy ``event.migration_alert`` entity that was
        registered in earlier versions — HA does not auto-remove entities
        when the discovery ha_type changes, so we publish an empty payload
        on the old topic.
        """
        from boneio.integration.homeassistant import (
            ha_migration_alert_availability_message,
        )

        config = self._manager._config_helper

        # --- Remove legacy event entity discovery (if any) ---
        old_event_topic = (
            f"{config.ha_discovery_prefix}/event/"
            f"{config.serial_number}/migration_alert/config"
        )
        self._manager.send_message(topic=old_event_topic, payload="", retain=True)
        _LOGGER.debug("Removed legacy migration_alert event entity discovery")

        # --- Register new binary_sensor entity ---
        msg = ha_migration_alert_availability_message(config_helper=config)

        self._manager.publish_ha_discovery(
            id="migration_alert",
            ha_type="binary_sensor",
            payload=msg,
        )
        _LOGGER.debug("Migration alert binary_sensor entity registered")

    async def _fire_migration_event_if_pending(self) -> None:
        """Publish migration binary_sensor state based on pending migrations.

        Called once after HA discovery is sent. Sets state to ON if there are
        pending migrations, OFF otherwise.  Attributes (count, description)
        are published on a separate JSON attributes topic.
        """
        migration_runner = getattr(self._manager, "migration_runner", None)
        if not migration_runner:
            return

        try:
            pending = migration_runner._get_pending()
        except Exception:
            return

        topic = self._manager._topic_prefix
        state_topic = f"{topic}/migration/state"
        attr_topic = f"{topic}/migration/attributes"

        if pending:
            descriptions = "; ".join(f"{m.version}: {m.description}" for m in pending[:5])
            state_payload = json.dumps({"state": "ON"})
            attr_payload = json.dumps(
                {
                    "count": len(pending),
                    "description": descriptions,
                }
            )
            _LOGGER.info("Migration alert ON: %d pending migration(s)", len(pending))
        else:
            state_payload = json.dumps({"state": "OFF"})
            attr_payload = json.dumps(
                {
                    "count": 0,
                    "description": "All system migrations applied",
                }
            )

        self._manager.send_message(topic=state_topic, payload=state_payload, retain=True)
        self._manager.send_message(topic=attr_topic, payload=attr_payload, retain=True)

