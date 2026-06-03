"""
Cloud registration module for boneIO Black.

Handles DNS registration with boneIO Cloud API and SSL certificate management
for PWA support with custom subdomains.
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import shutil
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiohttp

from boneio.core.cloud.secrets import MASTER_SECRET as DEFAULT_MASTER_SECRET
from boneio.core.system.monitor import get_network_info

_LOGGER = logging.getLogger(__name__)

# Cloud API configuration
CLOUD_API_URL = "https://api.boneio.app"

# SSL certificate paths (relative to home dir, writable by boneio app)
_DOCKER_DIR = Path.home() / "docker" / "nodered"
CERT_DIR = _DOCKER_DIR / "caddy" / "ssl"
CERT_FILE = CERT_DIR / "fullchain.pem"
KEY_FILE = CERT_DIR / "privkey.pem"

# Caddy configuration paths
CADDY_CONFIG_DIR = _DOCKER_DIR / "caddy"
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
        master_secret: str = DEFAULT_MASTER_SECRET,
        enabled: bool = True,
    ) -> None:
        """
        Initialize cloud registration.

        Args:
            serial_number: Device serial number (e.g., 'blkf8dc18')
            local_ip: Local IP address of the device
            master_secret: Shared secret for HMAC device authentication.
                Defaults to the build-time injected secret from secrets.py.
            enabled: Whether cloud registration is enabled
        """
        self._serial = serial_number
        self._local_ip = local_ip
        self._master_secret = master_secret
        self._enabled = enabled
        self._domain: str | None = None
        self._task: asyncio.Task | None = None
        self._session: aiohttp.ClientSession | None = None
        self._last_error: str | None = None

    @property
    def domain(self) -> str | None:
        """Get the registered domain name."""
        return self._domain

    @property
    def enabled(self) -> bool:
        """Check if cloud registration is enabled."""
        return self._enabled

    @property
    def last_error(self) -> str | None:
        """Get the last error message, if any."""
        return self._last_error

    @property
    def is_compose_writable(self) -> bool:
        """Check if docker-compose.yaml is writable without side effects."""
        compose_file = _DOCKER_DIR / "docker-compose.yaml"
        if not compose_file.exists():
            return False
        return os.access(compose_file, os.W_OK)

    async def start(self) -> None:
        """Start the cloud registration service."""
        if not self._enabled:
            _LOGGER.info("Cloud registration is disabled")
            return

        _LOGGER.info("Starting cloud registration for %s", self._serial)
        _LOGGER.debug(
            "Master secret starts with: '%s...' (len=%d)",
            self._master_secret[:4] if self._master_secret else "NONE",
            len(self._master_secret) if self._master_secret else 0,
        )

        # Create SSL directory if it doesn't exist
        CERT_DIR.mkdir(parents=True, exist_ok=True)

        # Start registration loop
        self._task = asyncio.create_task(self._registration_loop())

    async def stop(self) -> None:
        """Stop the cloud registration service."""
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        if self._session:
            await self._session.close()
            self._session = None

    def _compute_token(self) -> str:
        """Compute HMAC-SHA256 auth token from master secret and serial.

        Returns:
            Hex-encoded HMAC token string
        """
        return hmac.new(
            self._master_secret.encode(),
            self._serial.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _auth_headers(self) -> dict[str, str]:
        """Get authorization headers for cloud API requests.

        Returns:
            Dict with Authorization header
        """
        return {"Authorization": f"Bearer {self._compute_token()}"}

    async def _get_session(self) -> "aiohttp.ClientSession":
        """Get or create aiohttp session."""
        import aiohttp

        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self._session

    async def _registration_loop(self) -> None:
        """Main registration loop - registers DNS and fetches cert periodically."""
        while True:
            try:
                # Refresh local IP in case it changed (e.g. DHCP renewal)
                current_ip = get_network_info().get("ip", "")
                if current_ip and current_ip != "none" and current_ip != self._local_ip:
                    _LOGGER.info("Local IP changed: %s -> %s", self._local_ip, current_ip)
                    self._local_ip = current_ip

                # Register DNS
                success = await self._register_dns()
                if success:
                    _LOGGER.info("DNS registration successful: %s", self._domain)

                    # Fetch certificate if not present or needs refresh
                    cert_refreshed = False
                    if not self._cert_exists() or await self._cert_needs_refresh():
                        cert_refreshed = await self._fetch_certificate()

                    # Switch to cloud Caddy config if certs exist but not yet active
                    if self._cert_exists() and not self.is_cloud_config_active():
                        _LOGGER.info("Switching Caddy to cloud configuration...")
                        await self._switch_to_cloud_config()
                    elif cert_refreshed and self.is_cloud_config_active():
                        _LOGGER.info("Certificate refreshed, restarting Caddy...")
                        await self._recreate_caddy()
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
        import aiohttp

        try:
            session = await self._get_session()

            payload = {
                "serial": self._serial,
                "ip": self._local_ip,
            }

            async with session.post(
                f"{CLOUD_API_URL}/register",
                json=payload,
                headers=self._auth_headers(),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self._domain = data.get("domain")
                    return True
                elif response.status == 429:
                    # Rate limited - wait longer
                    data = await response.json()
                    retry_after = data.get("retryAfter", 3600)
                    _LOGGER.warning("Rate limited, retry after %d seconds", retry_after)
                    return False
                else:
                    body = await response.text()
                    _LOGGER.error(
                        "DNS registration failed (HTTP %d): %s",
                        response.status,
                        body,
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
        import aiohttp

        try:
            session = await self._get_session()

            async with session.get(
                f"{CLOUD_API_URL}/cert",
                params={"serial": self._serial},
                headers=self._auth_headers(),
            ) as response:
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
                        data.get("expiresAt", "unknown"),
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

        Parses the actual X.509 Not After date from the PEM file using openssl.
        Returns True if cert expires within 14 days or can't be parsed.

        Returns:
            True if certificate should be refreshed
        """
        if not self._cert_exists():
            return True

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["openssl", "x509", "-enddate", "-noout", "-in", str(CERT_FILE)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                ),
            )

            if result.returncode != 0:
                _LOGGER.warning("Failed to read cert expiry: %s", result.stderr.strip())
                return True

            # Output format: "notAfter=Jun  3 12:00:00 2026 GMT"
            line = result.stdout.strip()
            date_str = line.split("=", 1)[1]

            from datetime import datetime, timezone

            expiry = datetime.strptime(date_str, "%b %d %H:%M:%S %Y %Z").replace(
                tzinfo=timezone.utc
            )
            now = datetime.now(tz=timezone.utc)
            days_left = (expiry - now).total_seconds() / 86400

            _LOGGER.debug(
                "SSL certificate expires: %s (%.1f days left)", expiry.isoformat(), days_left
            )

            # Refresh if expiring within 14 days
            if days_left < 14:
                _LOGGER.info(
                    "SSL certificate expires in %.1f days, refreshing", days_left
                )
                return True

            return False

        except Exception as e:
            _LOGGER.warning("Error checking cert expiry, forcing refresh: %s", e)
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

    def _ensure_cloud_script(self) -> None:
        """
        Copy init-certs-cloud.sh from package data to the Caddy config directory.

        This ensures the script is always up-to-date after a pip upgrade,
        even if the user never re-clones the full repo.
        """
        dest = CADDY_CONFIG_DIR / "init-certs-cloud.sh"
        try:
            from importlib.resources import files

            src = files("boneio.core.cloud.data").joinpath("init-certs-cloud.sh")
            src_bytes = src.read_bytes()

            # Only write if content differs or file missing
            if not dest.exists() or dest.read_bytes() != src_bytes:
                dest.write_bytes(src_bytes)
                dest.chmod(0o755)
                _LOGGER.info("Deployed init-certs-cloud.sh to %s", dest)
        except Exception as e:
            _LOGGER.warning("Could not deploy init-certs-cloud.sh: %s", e)

    def _check_compose_writable(self) -> bool:
        """
        Check if docker-compose.yaml is writable.

        Returns:
            True if file is writable, False otherwise (sets _last_error).
        """
        compose_file = _DOCKER_DIR / "docker-compose.yaml"
        if compose_file.exists() and not os.access(compose_file, os.W_OK):
            compose_path = str(compose_file)
            self._last_error = f"Permission denied writing {compose_path}. Run via SSH: sudo chown $USER {compose_path}"
            _LOGGER.error(
                "Permission denied for %s. Fix with: sudo chown $USER %s",
                compose_path,
                compose_path,
            )
            return False
        return True

    async def _switch_to_cloud_config(self) -> bool:
        """
        Switch Caddy to cloud mode by replacing docker-compose.yaml with
        the bundled cloud template from boneio.core.cloud.data.

        Changes:
        - Deploys init-certs-cloud.sh from package to caddy dir
        - Replaces docker-compose.yaml with cloud version from package
        - Recreates Caddy container with new config

        Returns:
            True if switch was successful
        """
        # Ensure cloud script is deployed from package
        self._ensure_cloud_script()

        compose_file = _DOCKER_DIR / "docker-compose.yaml"
        try:
            if not compose_file.exists():
                _LOGGER.error("docker-compose.yaml not found: %s", compose_file)
                return False

            # Check permissions before attempting any changes
            if not self._check_compose_writable():
                return False

            content = compose_file.read_text()

            # Already switched?
            if "init-certs-cloud.sh" in content:
                _LOGGER.debug("Cloud config already active in docker-compose.yaml")
                return await self._recreate_caddy()

            # Backup original
            backup = compose_file.with_suffix(".yaml.bak")
            if not backup.exists():
                shutil.copy2(compose_file, backup)
                _LOGGER.info("Backed up docker-compose.yaml to %s", backup)

            # Replace with bundled cloud template
            from importlib.resources import files

            cloud_src = files("boneio.core.cloud.data").joinpath("docker-compose-cloud.yaml")
            cloud_content = cloud_src.read_text(encoding="utf-8")
            compose_file.write_text(cloud_content)
            _LOGGER.info("Replaced docker-compose.yaml with cloud template from package")

            return await self._recreate_caddy()

        except PermissionError:
            compose_path = str(compose_file)
            self._last_error = f"Permission denied writing {compose_path}. Run via SSH: sudo chown $USER {compose_path}"
            _LOGGER.error(
                "Permission denied for %s. Fix with: sudo chown $USER %s",
                compose_path,
                compose_path,
            )
            return False
        except Exception as e:
            self._last_error = str(e)
            _LOGGER.error("Failed to switch to cloud config: %s", e)
            return False

    async def _restore_local_config(self) -> bool:
        """
        Restore original docker-compose.yaml from package data and restart Caddy.

        Uses the bundled docker-compose.yaml from boneio.core.cloud.data so that
        future pip upgrades automatically bring the latest Caddy/Node-RED versions.

        Returns:
            True if restore was successful
        """
        compose_file = _DOCKER_DIR / "docker-compose.yaml"
        try:
            # Check permissions before attempting any changes
            if not self._check_compose_writable():
                return False

            from importlib.resources import files

            src = files("boneio.core.cloud.data").joinpath("docker-compose.yaml")
            original_content = src.read_text(encoding="utf-8")

            current_content = compose_file.read_text() if compose_file.exists() else ""
            if current_content == original_content:
                _LOGGER.debug("docker-compose.yaml already matches package original")
                return await self._recreate_caddy()

            compose_file.write_text(original_content)
            _LOGGER.info("Restored original docker-compose.yaml from package data")

            return await self._recreate_caddy()

        except PermissionError:
            compose_path = str(compose_file)
            self._last_error = f"Permission denied writing {compose_path}. Run via SSH: sudo chown $USER {compose_path}"
            _LOGGER.error(
                "Permission denied for %s. Fix with: sudo chown $USER %s",
                compose_path,
                compose_path,
            )
            return False
        except Exception as e:
            self._last_error = str(e)
            _LOGGER.error("Failed to restore local config: %s", e)
            return False

    async def _recreate_caddy(self) -> bool:
        """
        Recreate Caddy container to apply new docker-compose config.

        Uses 'docker compose up -d caddy' to pick up volume and entrypoint changes.

        Returns:
            True if recreate was successful
        """
        compose_dir = str(_DOCKER_DIR)
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["docker", "compose", "up", "-d", "caddy"],
                    cwd=compose_dir,
                    capture_output=True,
                    timeout=60,
                ),
            )

            if result.returncode == 0:
                _LOGGER.info("Caddy container recreated successfully")
                return True
            else:
                _LOGGER.error(
                    "Failed to recreate Caddy: %s",
                    result.stderr.decode() if result.stderr else "Unknown error",
                )
                return False

        except subprocess.TimeoutExpired:
            _LOGGER.error("Caddy recreate timed out")
            return False
        except Exception as e:
            _LOGGER.error("Failed to recreate Caddy: %s", e)
            return False

    def is_cloud_config_active(self) -> bool:
        """
        Check if cloud init-certs script is active in docker-compose.

        Returns:
            True if cloud config is active
        """
        try:
            compose_file = _DOCKER_DIR / "docker-compose.yaml"
            if not compose_file.exists():
                return False
            content = compose_file.read_text()
            return "init-certs-cloud.sh" in content
        except Exception:
            return False
