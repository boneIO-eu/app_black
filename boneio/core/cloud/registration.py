"""
Cloud registration module for boneIO Black.

Handles DNS registration with boneIO Cloud API and SSL certificate management
for PWA support with custom subdomains.
"""

import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import hmac
from importlib.resources import files
import logging
import os
import re
import shutil
import socket
import ssl
import subprocess
from contextlib import suppress
from pathlib import Path

import aiohttp

from boneio.core.cloud.secrets import MASTER_SECRET as DEFAULT_MASTER_SECRET
from boneio.core.system.monitor import get_network_info

from boneio.core import containers
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
# No Caddyfile constants here on purpose. Caddy's configuration is not a file
# in this directory — init-certs.sh (or init-certs-cloud.sh) writes it to
# /tmp/Caddyfile inside the container on every start. Switching between local
# and cloud mode swaps the compose file, and with it which of those two scripts
# runs; there is no Caddyfile to copy over another.

# Registration interval (1 hour)
REGISTRATION_INTERVAL = 3600

# Caddy Docker HTTPS port (host side of the 8443:443 mapping)
CADDY_HTTPS_PORT = 8443


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

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
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
                    elif (
                        self._cert_exists()
                        and self.is_cloud_config_active()
                        and not await self._caddy_cert_matches_disk()
                    ):
                        # Disk cert is OK but Caddy is serving a stale
                        # certificate (previous restart may have failed).
                        _LOGGER.warning(
                            "Caddy is serving a different certificate than on disk, restarting Caddy..."
                        )
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
            date_str = re.sub(r"\s+", " ", date_str.strip())

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

    async def _caddy_cert_matches_disk(self, port: int = CADDY_HTTPS_PORT) -> bool:
        """Check if the certificate served by Caddy matches the one on disk.

        Connects to 127.0.0.1:<port> via TLS (using the registered domain
        as SNI) and compares the serial number of the served certificate
        with the disk certificate.  If they differ Caddy needs a restart.

        Args:
            port: HTTPS port Caddy listens on (default 8443).

        Returns:
            True if the certificates match (or if the check cannot be
            performed), False if they differ.
        """
        if not self._cert_exists():
            return True  # nothing to compare

        if not self._domain:
            return True  # domain not yet known, skip

        try:
            # Read serial from disk cert
            disk_serial = await self._get_cert_serial_from_file(CERT_FILE)
            if disk_serial is None:
                return True  # can't read disk cert, assume OK

            # Read serial from Caddy's live TLS cert using the real domain as SNI
            live_serial = await self._get_caddy_live_serial(
                port=port, server_name=self._domain
            )
            if live_serial is None:
                # Caddy unreachable — restart will be attempted anyway
                _LOGGER.debug("Cannot connect to Caddy TLS on port %d", port)
                return False

            match = disk_serial == live_serial
            if not match:
                _LOGGER.info(
                    "Certificate serial mismatch: disk=%s caddy=%s",
                    disk_serial,
                    live_serial,
                )
            return match

        except Exception as e:
            _LOGGER.debug("Error comparing Caddy cert with disk: %s", e)
            return True  # don't trigger restart on unexpected errors

    async def _get_cert_serial_from_file(self, cert_path: Path) -> str | None:
        """Extract hex serial number from a PEM certificate file via openssl.

        Args:
            cert_path: Path to the PEM certificate.

        Returns:
            Hex serial string, or None on error.
        """
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["openssl", "x509", "-serial", "-noout", "-in", str(cert_path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                ),
            )
            if result.returncode != 0:
                return None
            # Output: "serial=AABBCCDD..."
            return result.stdout.strip().split("=", 1)[1].upper()
        except Exception:
            return None

    async def _get_caddy_live_serial(
        self, port: int = CADDY_HTTPS_PORT, server_name: str = "localhost"
    ) -> str | None:
        """Connect to Caddy via TLS and return the served certificate's serial.

        Args:
            port: HTTPS port to connect to.
            server_name: SNI server hostname (must match the Caddy vhost).

        Returns:
            Hex serial string, or None if unreachable.
        """
        sni = server_name  # capture for closure

        def _probe() -> str | None:

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            sock = socket.create_connection(("127.0.0.1", port), timeout=5)
            try:
                tls_sock = ctx.wrap_socket(sock, server_hostname=sni)
                try:
                    der_cert = tls_sock.getpeercert(binary_form=True)
                    if not der_cert:
                        return None
                    # Parse serial from DER using openssl
                    proc = subprocess.run(
                        ["openssl", "x509", "-serial", "-noout", "-inform", "DER"],
                        input=der_cert,
                        capture_output=True,
                        timeout=5,
                    )
                    if proc.returncode != 0:
                        return None
                    return proc.stdout.decode().strip().split("=", 1)[1].upper()
                finally:
                    tls_sock.close()
            except Exception:
                sock.close()
                return None

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _probe)
        except Exception:
            return None

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
            src = files("boneio.core.cloud.data").joinpath("init-certs-cloud.sh")
            src_bytes = src.read_bytes()

            # Only write if content differs or file missing
            if not dest.exists() or dest.read_bytes() != src_bytes:
                dest.write_bytes(src_bytes)
                dest.chmod(0o755)
                _LOGGER.info("Deployed init-certs-cloud.sh to %s", dest)
        except Exception as e:
            _LOGGER.warning("Could not deploy init-certs-cloud.sh: %s", e)

    def _check_compose_ownership(self) -> bool:
        """Check the compose file is managed by the privileged helper.

        This used to check the opposite — that the file was *writable* — and its
        error message told the operator to ``sudo chown $USER`` it. That advice
        reopens F-04: ``docker compose up`` executes this file, so whoever can
        write it can start a container as root with the host filesystem mounted.

        Returns:
            True when the cloud switch can proceed.
        """
        if containers.helper_available():
            return True
        self._last_error = (
            "boneio-containers is not installed yet, so the compose file cannot "
            "be switched. Apply the pending system migrations and try again."
        )
        _LOGGER.error("%s", self._last_error)
        return False

    async def _switch_to_cloud_config(self) -> bool:
        """Switch Caddy to cloud mode.

        The compose file is no longer written here. The helper copies it from a
        root-owned template, so this method asks for a template by name and has
        no way to influence its contents.

        Returns:
            True if the switch was successful.
        """
        # The init script still comes from the package; it is mounted read-only
        # into the container and is not what compose executes on the host.
        self._ensure_cloud_script()

        if not self._check_compose_ownership():
            return False

        if self.is_cloud_config_active():
            _LOGGER.debug("Cloud config already active in docker-compose.yaml")
            return await self._recreate_caddy()

        result = await asyncio.get_event_loop().run_in_executor(
            None, containers.apply_cloud_template
        )
        if not result.ok:
            self._last_error = result.stderr.strip() or "could not apply the cloud template"
            _LOGGER.error("Failed to switch to cloud config: %s", self._last_error)
            return False

        _LOGGER.info("Switched docker-compose.yaml to the cloud template")
        return await self._recreate_caddy()

    async def _restore_local_config(self) -> bool:
        """Restore the plain compose template and restart Caddy.

        Returns:
            True if the restore was successful.
        """
        if not self._check_compose_ownership():
            return False

        if not self.is_cloud_config_active():
            _LOGGER.debug("docker-compose.yaml is already the local template")
            return await self._recreate_caddy()

        result = await asyncio.get_event_loop().run_in_executor(
            None, containers.remove_cloud_template
        )
        if not result.ok:
            self._last_error = result.stderr.strip() or "could not restore the template"
            _LOGGER.error("Failed to restore local config: %s", self._last_error)
            return False

        _LOGGER.info("Restored the local docker-compose.yaml template")
        return await self._recreate_caddy()

    async def _recreate_caddy(self) -> bool:
        """Recreate and restart Caddy so it picks up new certs or compose config.

        Both steps go through the container helper, so neither passes anything
        from here to Docker.

        Returns:
            True if the recreate was successful.
        """
        loop = asyncio.get_event_loop()
        up = await loop.run_in_executor(None, containers.start_caddy)
        if not up.ok:
            _LOGGER.error(
                "Failed to recreate Caddy: %s", up.stderr.strip() or "unknown error"
            )
            return False

        # Restart as well: mounted TLS certificates are only re-read on start.
        restart = await loop.run_in_executor(None, containers.restart_caddy)
        if not restart.ok:
            _LOGGER.warning(
                "Caddy was recreated but the restart failed: %s",
                restart.stderr.strip() or "unknown error",
            )

        _LOGGER.info("Caddy container recreated and restarted successfully")
        return True

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


async def set_enabled(config_helper, enabled: bool, local_ip: str | None = None) -> str:
    """Turn cloud registration on or off on a running device.

    Registration used to begin only in :mod:`boneio.runner`, so switching it on
    from the panel wrote a line to config.yaml and asked for a restart —
    on a controller whose whole point is that it is running. Everything the
    change needs is already here: :meth:`CloudRegistration.start` does no more
    than launch the loop that registers the name, fetches the certificate,
    swaps the compose template and recreates Caddy.

    Idempotent in both directions, because the panel can be open twice and a
    save can be repeated.

    Args:
        config_helper: The live :class:`ConfigHelper`.
        enabled: The state asked for.
        local_ip: This device's address on the LAN. Read from the system when
            not given.

    Returns:
        A short word for what happened: ``started``, ``stopped``, ``unchanged``
        or ``unavailable``.
    """
    existing = getattr(config_helper, "_cloud_reg", None)

    if not enabled:
        config_helper._cloud_registration = False
        if existing is None:
            return "unchanged"
        try:
            await existing.stop()
            # Put the plain template back, or Caddy keeps trying to serve a
            # certificate for a name that is no longer being renewed.
            await existing._restore_local_config()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Could not stop cloud registration cleanly: %s", err)
        config_helper._cloud_reg = None
        _LOGGER.info("Cloud registration stopped on request")
        return "stopped"

    if existing is not None:
        config_helper._cloud_registration = True
        return "unchanged"

    serial = getattr(config_helper, "serial_number", None)
    if not local_ip:
        try:
            local_ip = (get_network_info() or {}).get("ip", "")
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Could not read this device's address: %s", err)
            local_ip = ""

    if not serial or not local_ip:
        # The setting is saved either way; the next start picks it up. Saying
        # so is better than reporting success for a service that did not begin.
        _LOGGER.warning(
            "Cloud registration is enabled but %s is not known yet; it will "
            "start on the next boot.",
            "the serial number" if not serial else "this device's address",
        )
        config_helper._cloud_registration = True
        return "unavailable"

    registration = CloudRegistration(serial_number=serial, local_ip=local_ip)
    await registration.start()
    config_helper._cloud_reg = registration
    config_helper._cloud_registration = True
    _LOGGER.info("Cloud registration started for %s (IP: %s)", serial, local_ip)
    return "started"
