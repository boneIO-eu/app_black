"""Update manager for checking and publishing software updates to Home Assistant.

This module manages periodic checking of software updates from GitHub
and publishes the update status to Home Assistant via MQTT.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from boneio.core.utils.async_updater import AsyncUpdater
from boneio.core.utils.timeperiod import TimePeriod
from boneio.version import __version__

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
        
        # Initialize AsyncUpdater (starts periodic task)
        super().__init__(manager=manager, update_interval=update_interval)
        
        _LOGGER.info(
            "UpdateManager initialized (check interval: %s)",
            update_interval
        )

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
                    update_info.get("message", "Unknown error") if update_info else "No response"
                )
        except Exception as e:
            _LOGGER.error("Error during update check: %s", e, exc_info=True)
        
        # Return None to use default interval
        return None

    async def _check_update_from_github(self) -> dict | None:
        """Check for updates from GitHub releases.
        
        This method reuses the logic from /api/check_update endpoint.
        
        Returns:
            Update information dict or None on error
        """
        current_version = __version__
        
        try:
            import requests
        except ImportError:
            _LOGGER.error("Package 'requests' is not installed")
            return {
                "status": "error",
                "message": "Package 'requests' is not installed",
                "current_version": current_version
            }
        
        try:
            from packaging import version
        except ImportError:
            _LOGGER.error("Package 'packaging' is not installed")
            return {
                "status": "error",
                "message": "Package 'packaging' is not installed",
                "current_version": current_version
            }
        
        try:
            repo = "boneIO-eu/app_black"
            api_url = f'https://api.github.com/repos/{repo}/releases'
            response = requests.get(api_url, timeout=10)
            
            if response.status_code != 200:
                return {
                    "status": "error",
                    "message": f"GitHub API error: {response.status_code}",
                    "current_version": current_version
                }
            
            releases = response.json()
            
            if not releases:
                return {
                    "status": "error",
                    "message": "No releases found on GitHub",
                    "current_version": current_version
                }
            
            # Find latest stable and prerelease versions
            latest_stable = None
            latest_prerelease = None
            
            for release in releases:
                tag = release['tag_name']
                ver_str = tag[1:] if tag.startswith('v') else tag
                
                # Skip v0.x versions (Debian 10, incompatible)
                if tag.startswith("v0."):
                    continue
                
                is_prerelease = release.get('prerelease', False)
                
                if not is_prerelease:
                    ver_lower = ver_str.lower()
                    is_prerelease = any(x in ver_lower for x in ['dev', 'alpha', 'beta', 'rc'])
                
                ver_info = {
                    "version": ver_str,
                    "is_prerelease": is_prerelease,
                    "release_url": release['html_url'],
                    "published_at": release['published_at'],
                    "release_notes": release.get('body', '')[:255],  # Max 255 chars for HA
                }
                
                if not is_prerelease and latest_stable is None:
                    latest_stable = ver_info
                if is_prerelease and latest_prerelease is None:
                    latest_prerelease = ver_info
                
                # Stop after finding both
                if latest_stable and latest_prerelease:
                    break
            
            # Determine which version to recommend based on update_channel setting
            update_channel = self._manager._config_helper.update_channel
            
            if update_channel == "dev":
                # Dev channel: prefer prerelease, fallback to stable
                recommended = latest_prerelease or latest_stable
            else:
                # Stable channel (default): only stable releases
                recommended = latest_stable
            
            if not recommended:
                return {
                    "status": "error",
                    "message": "No suitable release found",
                    "current_version": current_version
                }
            
            # Check if update is available
            is_update_available = False
            try:
                current_parsed = version.parse(current_version)
                recommended_parsed = version.parse(recommended["version"])
                is_update_available = recommended_parsed > current_parsed
            except Exception as e:
                _LOGGER.warning("Error parsing versions: %s", e)
            
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
            return {
                "status": "error",
                "message": f"Error: {str(e)}",
                "current_version": current_version
            }

    async def _publish_state_to_mqtt(self, update_info: dict) -> None:
        """Publish update state to MQTT for Home Assistant.
        
        Args:
            update_info: Update information from GitHub check
        """
        if update_info.get("status") != "success":
            return
        
        current_version = update_info.get("current_version", __version__)
        latest_version = update_info.get("latest_version", current_version)
        
        # Build state payload (JSON format for HA Update entity)
        state_payload = {
            "installed_version": current_version,
            "latest_version": latest_version,
            "title": "boneIO Black Firmware",
            "release_url": update_info.get("release_url", ""),
            "release_summary": update_info.get("release_notes", "")[:255],  # HA limit
        }
        
        # Add entity_picture (boneIO logo from HA brands)
        state_payload["entity_picture"] = "http://boneio.eu/logo_fb_circle.png"
        
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
            update_info.get("update_available", False)
        )

    def get_last_check_result(self) -> dict | None:
        """Get the last update check result.
        
        Returns:
            Last check result dict or None if no check performed yet
        """
        return self._last_check_result

    async def handle_install_command(self, payload: str) -> None:
        """Handle install command from Home Assistant.
        
        This is called when HA sends a message to the command topic.
        
        Args:
            payload: MQTT payload (should be "INSTALL")
        """
        if payload != "INSTALL":
            _LOGGER.warning("Invalid install command payload: %s", payload)
            return
        
        _LOGGER.info("Received install command from Home Assistant")
        
        # Check if update is available
        if not self._last_check_result:
            _LOGGER.warning("No update check result available, checking now...")
            await self.async_update(timestamp=0)
        
        if not self._last_check_result or not self._last_check_result.get("update_available"):
            _LOGGER.warning("No update available to install")
            return
        
        # Trigger update via existing update endpoint
        # Note: This requires the update API to be accessible
        # The actual installation is handled by /api/update endpoint
        _LOGGER.info(
            "Update installation should be triggered via WebUI or API endpoint /api/update"
        )
        
        # TODO: Consider adding direct integration with update logic
        # For now, users should use the WebUI to trigger updates

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for Update entity."""
        _LOGGER.debug("Sending HA autodiscovery for Update entity")
        
        self._manager.send_ha_autodiscovery(
            id="firmware",
            name="Update",
            ha_type="update",
        )
        
        # Subscribe to command topic for install commands
        command_topic = f"{self._manager._topic_prefix}/update/install"
        await self._manager._message_bus.subscribe_and_listen(
            topic=command_topic,
            callback=self._manager._handle_update_install_command
        )
        _LOGGER.info("Subscribed to update command topic: %s", command_topic)
