"""Checking a certificate and key before the device starts serving them.

An operator who does not want cloud registration still deserves a panel that
browsers accept, and the way there is their own certificate: from a company CA,
or from Let's Encrypt obtained on a machine that can actually run the
challenge. This is the part that decides whether what they uploaded is usable.

The checking is the point. A certificate that does not match its key makes the
proxy fail to start, and a certificate whose names do not cover the address
people type produces the same browser warning as before — except now the
operator believes they fixed it, which is worse than knowing they had not.
"""

from __future__ import annotations

import datetime
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

_LOGGER = logging.getLogger(__name__)

#: Refuse anything larger. A certificate chain is a few kilobytes; a megabyte
#: of PEM is somebody uploading the wrong file.
MAX_PEM_BYTES = 256 * 1024


class CertificateError(Exception):
    """The uploaded material cannot be served."""


@dataclass
class CertificateInfo:
    """What a usable certificate turned out to be."""

    subject: str
    issuer: str
    not_before: datetime.datetime
    not_after: datetime.datetime
    names: list[str] = field(default_factory=list)
    fingerprint: str = ""
    #: Names the device is reached by that this certificate does not cover.
    #: Not an error — the operator may know something we do not — but the one
    #: thing worth saying out loud.
    uncovered: list[str] = field(default_factory=list)

    @property
    def days_left(self) -> int:
        """Whole days until it expires."""
        now = datetime.datetime.now(datetime.UTC)
        return max(0, (self.not_after - now).days)

    def to_dict(self) -> dict:
        """Serialise for the API."""
        return {
            "subject": self.subject,
            "issuer": self.issuer,
            "not_before": self.not_before.isoformat(),
            "not_after": self.not_after.isoformat(),
            "days_left": self.days_left,
            "names": self.names,
            "fingerprint": self.fingerprint,
            "uncovered": self.uncovered,
        }


def _names_of(cert: x509.Certificate) -> list[str]:
    """Every name the certificate is valid for.

    Args:
        cert: The parsed certificate.

    Returns:
        DNS names and IP addresses from the SAN extension.
    """
    try:
        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound:
        return []
    names = [str(n) for n in san.get_values_for_type(x509.DNSName)]
    names += [str(n) for n in san.get_values_for_type(x509.IPAddress)]
    return names


def _covers(names: list[str], wanted: str) -> bool:
    """Whether a certificate's names cover one address.

    Args:
        names: Names from the certificate.
        wanted: A hostname or IP address the device is reached by.

    Returns:
        True when a browser would accept the certificate for *wanted*.
    """
    wanted = wanted.strip().lower()
    if not wanted:
        return True
    for name in names:
        name = name.lower()
        if name == wanted:
            return True
        # A wildcard matches one label, and never the bare domain.
        if name.startswith("*.") and "." in wanted:
            if wanted.split(".", 1)[1] == name[2:]:
                return True
    return False


def inspect(cert_pem: bytes, key_pem: bytes, reached_by: list[str] | None = None) -> CertificateInfo:
    """Check a certificate and key, and describe what they are.

    Args:
        cert_pem: The certificate, or a full chain, in PEM.
        key_pem: The private key in PEM. Must not be encrypted — the proxy
            starts unattended and has nobody to ask for a passphrase.
        reached_by: Hostnames and addresses this device is reached by, checked
            against the certificate's names.

    Returns:
        What the certificate is.

    Raises:
        CertificateError: If it cannot be parsed, the key does not match, the
            key is encrypted, or the certificate has expired.
    """
    if len(cert_pem) > MAX_PEM_BYTES or len(key_pem) > MAX_PEM_BYTES:
        raise CertificateError("That file is far too large to be a certificate.")

    try:
        cert = x509.load_pem_x509_certificate(cert_pem)
    except Exception as err:  # noqa: BLE001
        raise CertificateError(f"The certificate is not readable PEM: {err}") from err

    try:
        key = serialization.load_pem_private_key(key_pem, password=None)
    except TypeError as err:
        raise CertificateError(
            "The private key is protected by a passphrase. The proxy starts "
            "unattended and has nobody to ask, so upload an unencrypted key."
        ) from err
    except Exception as err:  # noqa: BLE001
        raise CertificateError(f"The private key is not readable PEM: {err}") from err

    cert_public = cert.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_public = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if cert_public != key_public:
        raise CertificateError(
            "That key does not belong to that certificate. Serving them "
            "together would stop the proxy from starting at all."
        )

    not_after = cert.not_valid_after_utc
    not_before = cert.not_valid_before_utc
    now = datetime.datetime.now(datetime.UTC)
    if not_after <= now:
        raise CertificateError(
            f"That certificate expired on {not_after.date()}. Browsers would "
            "reject it more loudly than the self-signed one it replaces."
        )

    names = _names_of(cert)
    uncovered = [
        address
        for address in (reached_by or [])
        if address and not _covers(names, address)
    ]

    return CertificateInfo(
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        not_before=not_before,
        not_after=not_after,
        names=names,
        fingerprint=cert.fingerprint(hashes.SHA256()).hex(),
        uncovered=uncovered,
    )


def device_addresses(hostname: str | None, ip: str | None) -> list[str]:
    """The names a browser is likely to be pointed at this device by.

    Args:
        hostname: The device's hostname.
        ip: Its address on the local network.

    Returns:
        Addresses to check a certificate against.
    """
    addresses = []
    for value in (hostname, f"{hostname}.local" if hostname else None, ip):
        if value and value not in addresses:
            addresses.append(value)
    return addresses


# --------------------------------------------------------------- on the device

#: Where the proxy reads an uploaded certificate from.
#:
#: Inside Caddy's data directory on purpose. That directory is already mounted
#: into the container and already belongs to the account the panel runs as, so
#: nothing here needs a change to docker-compose.yaml — which is root-owned and
#: would have to go out as a migration — and no new mount point can be created
#: by Docker as root before the panel ever gets to write in it. The cloud
#: path's own certificate lives elsewhere and is untouched by any of this.
CERT_DIR = Path.home() / "docker" / "nodered" / "caddy" / "data" / "custom"
CUSTOM_CERT = CERT_DIR / "fullchain.pem"
CUSTOM_KEY = CERT_DIR / "privkey.pem"

#: Caddy's own certificate authority, created on first start. Offering it for
#: download is the cheapest way to a panel that browsers accept: no domain, no
#: DNS credentials, nothing reachable from outside. What it costs is that a
#: machine trusting it will believe that authority about any name, so it is
#: offered with that said rather than as the obvious thing to do.
ROOT_CA = (
    Path.home()
    / "docker" / "nodered" / "caddy" / "data" / "caddy" / "pki"
    / "authorities" / "local" / "root.crt"
)

#: The key is a secret, and it is written by the account the panel runs as.
KEY_MODE = 0o600
CERT_MODE = 0o644


def install(cert_pem: bytes, key_pem: bytes) -> None:
    """Write a checked certificate and key where the proxy will find them.

    Args:
        cert_pem: The certificate or chain.
        key_pem: Its private key.

    Raises:
        CertificateError: If the files cannot be written.
    """
    try:
        CERT_DIR.mkdir(parents=True, exist_ok=True)
        # The key is created with its mode already set, so it is never even
        # briefly readable by anything else on the device.
        def _private(path: str, flags: int) -> int:
            return os.open(path, flags, KEY_MODE)

        with open(CUSTOM_KEY, "wb", opener=_private) as handle:
            handle.write(key_pem)
        CUSTOM_KEY.chmod(KEY_MODE)
        CUSTOM_CERT.write_bytes(cert_pem)
        CUSTOM_CERT.chmod(CERT_MODE)
    except OSError as err:
        raise CertificateError(f"Could not store the certificate: {err}") from err
    _LOGGER.warning("A custom TLS certificate was installed at %s", CUSTOM_CERT)


def remove() -> bool:
    """Delete the custom certificate, returning the proxy to its own.

    Returns:
        True if something was removed.
    """
    removed = False
    for path in (CUSTOM_CERT, CUSTOM_KEY):
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            continue
        except OSError as err:
            raise CertificateError(f"Could not remove {path.name}: {err}") from err
    if removed:
        _LOGGER.warning("The custom TLS certificate was removed")
    return removed


def installed() -> CertificateInfo | None:
    """Describe the custom certificate in place, if there is one.

    Returns:
        Its details, or None when the proxy is using its own.
    """
    if not (CUSTOM_CERT.exists() and CUSTOM_KEY.exists()):
        return None
    try:
        return inspect(CUSTOM_CERT.read_bytes(), CUSTOM_KEY.read_bytes())
    except (OSError, CertificateError) as err:
        _LOGGER.warning("The installed certificate cannot be read: %s", err)
        return None
