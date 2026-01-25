"""
Cloud registration module for boneIO Black.

Handles DNS registration with boneIO Cloud API and SSL certificate management
for PWA support with custom subdomains.
"""

import asyncio
import base64
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Cloud API configuration
CLOUD_API_URL = "https://api.boneio.app"
CERT_DIR = Path("/data/ssl")
CERT_FILE = CERT_DIR / "fullchain.pem"
KEY_FILE = CERT_DIR / "privkey.pem"

# Caddy configuration paths
CADDY_CONFIG_DIR = Path("/opt/boneio/docker/nodered/caddy")
CADDY_DEFAULT_CONFIG = CADDY_CONFIG_DIR / "Caddyfile"
CADDY_CLOUD_CONFIG = CADDY_CONFIG_DIR / "Caddyfile.cloud"
CADDY_ACTIVE_CONFIG = CADDY_CONFIG_DIR / "Caddyfile"

# Registration interval (1 hour)
REGISTRATION_INTERVAL = 3600


class CloudRegistration:
    """
    Manages cloud registration for boneIO Black devices.
    
    Registers device DNS with cloud API and downloads SSL certificates
    for PWA support.
    """

    def __init__(
        self,
        serial_number: str,
        local_ip: str,
        enabled: bool = True,
    ) -> None:
        """
        Initialize cloud registration.
        
        Args:
            serial_number: Device serial number (e.g., 'blkf8dc18')
            local_ip: Local IP address of the device
            enabled: Whether cloud registration is enabled
        """
        self._serial = serial_number
        self._local_ip = local_ip
        self._enabled = enabled
        self._domain: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def domain(self) -> Optional[str]:
        """Get the registered domain name."""
        return self._domain

    @property
    def enabled(self) -> bool:
        """Check if cloud registration is enabled."""
        return self._enabled

    async def start(self) -> None:
        """Start the cloud registration service."""
        if not self._enabled:
            _LOGGER.info("Cloud registration is disabled")
            return

        _LOGGER.info("Starting cloud registration for %s", self._serial)
        
        # Create SSL directory if it doesn't exist
        CERT_DIR.mkdir(parents=True, exist_ok=True)
        
        # Start registration loop
        self._task = asyncio.create_task(self._registration_loop())

    async def stop(self) -> None:
        """Stop the cloud registration service."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._session:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def _registration_loop(self) -> None:
        """Main registration loop - registers DNS and fetches cert periodically."""
        while True:
            try:
                # Register DNS
                success = await self._register_dns()
                if success:
                    _LOGGER.info("DNS registration successful: %s", self._domain)
                    
                    # Fetch certificate if not present or needs refresh
                    if not self._cert_exists() or await self._cert_needs_refresh():
                        cert_fetched = await self._fetch_certificate()
                        
                        # Switch to cloud Caddy config if cert was fetched and not already active
                        if cert_fetched and not self.is_cloud_config_active():
                            _LOGGER.info("Switching Caddy to cloud configuration...")
                            await self._switch_to_cloud_config()
                else:
                    _LOGGER.warning("DNS registration failed, will retry")

            except asyncio.CancelledError:
                raise
            except Exception as e:
                _LOGGER.error("Cloud registration error: %s", e)

            # Wait before next registration
            await asyncio.sleep(REGISTRATION_INTERVAL)

    async def _register_dns(self) -> bool:
        """
        Register device DNS with cloud API.
        
        Returns:
            True if registration was successful
        """
        try:
            session = await self._get_session()
            
            payload = {
                "serial": self._serial,
                "ip": self._local_ip,
            }
            
            async with session.post(
                f"{CLOUD_API_URL}/register",
                json=payload,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self._domain = data.get("domain")
                    return True
                elif response.status == 429:
                    # Rate limited - wait longer
                    data = await response.json()
                    retry_after = data.get("retryAfter", 3600)
                    _LOGGER.warning(
                        "Rate limited, retry after %d seconds", retry_after
                    )
                    return False
                else:
                    data = await response.json()
                    _LOGGER.error(
                        "DNS registration failed: %s", data.get("error", "Unknown")
                    )
                    return False

        except aiohttp.ClientError as e:
            _LOGGER.error("Failed to connect to cloud API: %s", e)
            return False

    async def _fetch_certificate(self) -> bool:
        """
        Fetch SSL certificate from cloud API.
        
        Returns:
            True if certificate was fetched successfully
        """
        try:
            session = await self._get_session()
            
            async with session.get(f"{CLOUD_API_URL}/cert") as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Decode and save certificate
                    cert_data = base64.b64decode(data["cert"])
                    key_data = base64.b64decode(data["key"])
                    
                    CERT_FILE.write_bytes(cert_data)
                    KEY_FILE.write_bytes(key_data)
                    
                    # Set proper permissions for key file
                    os.chmod(KEY_FILE, 0o600)
                    
                    _LOGGER.info(
                        "SSL certificate saved, expires: %s",
                        data.get("expiresAt", "unknown")
                    )
                    return True
                elif response.status == 503:
                    _LOGGER.warning("Certificate not yet available from cloud")
                    return False
                else:
                    _LOGGER.error("Failed to fetch certificate: %d", response.status)
                    return False

        except aiohttp.ClientError as e:
            _LOGGER.error("Failed to fetch certificate: %s", e)
            return False
        except Exception as e:
            _LOGGER.error("Error saving certificate: %s", e)
            return False

    def _cert_exists(self) -> bool:
        """Check if certificate files exist."""
        return CERT_FILE.exists() and KEY_FILE.exists()

    async def _cert_needs_refresh(self) -> bool:
        """
        Check if certificate needs to be refreshed.
        
        Returns:
            True if cert is older than 30 days or doesn't exist
        """
        if not self._cert_exists():
            return True
        
        try:
            # Check cert file age
            import time
            cert_age = time.time() - CERT_FILE.stat().st_mtime
            # Refresh if older than 30 days
            return cert_age > (30 * 24 * 3600)
        except Exception:
            return True

    def update_ip(self, new_ip: str) -> None:
        """
        Update local IP address.
        
        Args:
            new_ip: New local IP address
        """
        if new_ip != self._local_ip:
            _LOGGER.info("Local IP changed: %s -> %s", self._local_ip, new_ip)
            self._local_ip = new_ip

    async def _switch_to_cloud_config(self) -> bool:
        """
        Switch Caddy to cloud configuration with wildcard cert.
        
        Returns:
            True if switch was successful
        """
        try:
            if not CADDY_CLOUD_CONFIG.exists():
                _LOGGER.error("Cloud Caddyfile not found: %s", CADDY_CLOUD_CONFIG)
                return False

            # Backup current config
            backup_path = CADDY_CONFIG_DIR / "Caddyfile.backup"
            if CADDY_ACTIVE_CONFIG.exists():
                shutil.copy2(CADDY_ACTIVE_CONFIG, backup_path)

            # Copy cloud config to active
            shutil.copy2(CADDY_CLOUD_CONFIG, CADDY_ACTIVE_CONFIG)
            _LOGGER.info("Switched to cloud Caddyfile")

            # Restart Caddy container
            return await self._restart_caddy()

        except Exception as e:
            _LOGGER.error("Failed to switch Caddy config: %s", e)
            return False

    async def _restart_caddy(self) -> bool:
        """
        Restart Caddy container to apply new configuration.
        
        Returns:
            True if restart was successful
        """
        try:
            # Use docker compose to restart caddy
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["docker", "compose", "restart", "caddy"],
                    cwd="/opt/boneio/docker/nodered",
                    capture_output=True,
                    timeout=30,
                )
            )

            if result.returncode == 0:
                _LOGGER.info("Caddy container restarted successfully")
                return True
            else:
                _LOGGER.error(
                    "Failed to restart Caddy: %s",
                    result.stderr.decode() if result.stderr else "Unknown error"
                )
                return False

        except subprocess.TimeoutExpired:
            _LOGGER.error("Caddy restart timed out")
            return False
        except Exception as e:
            _LOGGER.error("Failed to restart Caddy: %s", e)
            return False

    def is_cloud_config_active(self) -> bool:
        """
        Check if cloud Caddyfile is currently active.
        
        Returns:
            True if cloud config is active
        """
        try:
            if not CADDY_ACTIVE_CONFIG.exists():
                return False
            
            # Check if active config contains the cloud domain block
            content = CADDY_ACTIVE_CONFIG.read_text()
            return "*.black.boneio.app" in content
        except Exception:
            return False
