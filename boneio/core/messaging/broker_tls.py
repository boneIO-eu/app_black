"""Certificates for the MQTT broker installed on this controller.

The broker's files are root's (``/etc/mosquitto/certs``, the key readable by
the broker's group only) and are installed by ``boneio-system mqtt-tls-cert``.
This module prepares what goes there and describes what is there.

Two sources:

- The owner's own certificate, uploaded with its key and, optionally, the CA
  that signed it. Checked here the same way the panel's own certificate is,
  plus that the CA really issued it; the CA is appended to the chain so the
  panel can hand it out to Home Assistant later.
- One made here. A CA and the broker's certificate are generated together and
  the CA's key is dropped the moment it has signed, so the controller never
  holds a key that could vouch for anything else. The price is that a new
  certificate means a new CA, which clients have to be given again — and that
  is why these are made to last ten years rather than the 825 days Apple
  platforms insist on for certificates their own TLS stack checks: an expiry
  nobody remembers would take every client off the broker at once, while a
  client that refuses a long lifetime does so the day it is set up.
"""

from __future__ import annotations

import datetime
import ipaddress
from dataclasses import dataclass, field
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from boneio.core.security import certificate as certs

#: Where the helper installs the chain. World-readable; the key beside it is not.
INSTALLED_CERT = Path("/etc/mosquitto/certs/boneio.crt")

GENERATED_DAYS = 3650
#: Names every generated certificate covers besides the device's own, so a
#: client on the controller itself can connect over TLS and still check it.
LOCAL_NAMES = ("localhost", "127.0.0.1")


class BrokerTlsError(Exception):
    """The material cannot be used for the broker."""


@dataclass
class BrokerCertificate:
    """The broker's certificate, as the panel shows it."""

    subject: str
    issuer: str
    not_after: datetime.datetime
    names: list[str]
    fingerprint: str
    uncovered: list[str] = field(default_factory=list)
    #: The chain ends in a self-signed CA, which the panel can hand out.
    ca_available: bool = False

    def to_dict(self) -> dict:
        """Serialise for the API."""
        now = datetime.datetime.now(datetime.UTC)
        return {
            "subject": self.subject,
            "issuer": self.issuer,
            "not_after": self.not_after.isoformat(),
            "days_left": max(0, (self.not_after - now).days),
            "names": self.names,
            "fingerprint": self.fingerprint,
            "uncovered": self.uncovered,
            "ca_available": self.ca_available,
        }


def _pem(cert: x509.Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def _is_root_ca(cert: x509.Certificate) -> bool:
    if cert.issuer != cert.subject:
        return False
    try:
        return cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        return False


def _load_chain(pem: bytes) -> list[x509.Certificate]:
    if len(pem) > certs.MAX_PEM_BYTES:
        raise BrokerTlsError("That file is far too large to be a certificate.")
    try:
        chain = x509.load_pem_x509_certificates(pem)
    except ValueError as err:
        raise BrokerTlsError(f"That is not a PEM certificate: {err}") from err
    if not chain:
        raise BrokerTlsError("That file holds no certificate.")
    return chain


def _issued_by(cert: x509.Certificate, issuer: x509.Certificate) -> bool:
    try:
        cert.verify_directly_issued_by(issuer)
    except Exception:  # noqa: BLE001 - InvalidSignature, ValueError, TypeError
        return False
    return True


def _names_for(addresses: list[str]) -> list[x509.GeneralName]:
    names: list[x509.GeneralName] = []
    seen: set[str] = set()
    for value in [*addresses, *LOCAL_NAMES]:
        value = value.strip()
        if not value or value.lower() in seen:
            continue
        seen.add(value.lower())
        try:
            names.append(x509.IPAddress(ipaddress.ip_address(value)))
        except ValueError:
            names.append(x509.DNSName(value))
    return names


def generate(addresses: list[str]) -> tuple[bytes, bytes, bytes]:
    """Make a CA and a broker certificate for *addresses*, and drop the CA key.

    Args:
        addresses: Hostnames and IP addresses clients reach the broker by.

    Returns:
        The chain (broker certificate, then the CA), the broker's key, and the
        CA certificate on its own — all PEM.
    """
    now = datetime.datetime.now(datetime.UTC)
    # A day back, so a client whose clock lags a little does not see a
    # certificate from the future.
    start = now - datetime.timedelta(days=1)
    end = now + datetime.timedelta(days=GENERATED_DAYS)
    label = next((a for a in addresses if a and not a[0].isdigit()), None) or "boneIO"

    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "boneIO"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"{label} MQTT CA"),
    ])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, label)]))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName(_names_for(addresses)), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    # The CA has done its one job. Nothing keeps a reference to its key, and
    # nothing ever wrote it anywhere.
    del ca_key

    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return _pem(leaf) + _pem(ca), key_pem, _pem(ca)


def prepare_upload(
    cert_pem: bytes,
    key_pem: bytes,
    ca_pem: bytes | None,
    reached_by: list[str],
) -> tuple[str, BrokerCertificate]:
    """Check an uploaded certificate and build what the helper installs.

    Args:
        cert_pem: The broker's certificate, optionally with intermediates.
        key_pem: Its unencrypted key.
        ca_pem: The CA that signed it, when the owner has one to hand out.
        reached_by: Names and addresses clients reach the broker by.

    Returns:
        The PEM bundle for ``mqtt-tls-cert`` (chain, CA, key) and a
        description of the certificate.

    Raises:
        BrokerTlsError: If the pair is unusable, or the CA did not sign it.
    """
    try:
        info = certs.inspect(cert_pem, key_pem, reached_by=reached_by)
    except certs.CertificateError as err:
        raise BrokerTlsError(str(err)) from err

    chain = _load_chain(cert_pem)
    if ca_pem:
        authorities = _load_chain(ca_pem)
        last = chain[-1]
        if not any(_issued_by(last, authority) or last == authority for authority in authorities):
            raise BrokerTlsError(
                "That CA did not sign this certificate. Clients given it would "
                "refuse the broker."
            )
        for authority in authorities:
            if authority not in chain:
                chain.append(authority)

    bundle = b"".join(_pem(c) for c in chain) + key_pem.strip() + b"\n"
    description = BrokerCertificate(
        subject=info.subject,
        issuer=info.issuer,
        not_after=info.not_after,
        names=info.names,
        fingerprint=info.fingerprint,
        uncovered=info.uncovered,
        ca_available=_is_root_ca(chain[-1]) and len(chain) > 1,
    )
    return bundle.decode("ascii"), description


def generated_bundle(addresses: list[str]) -> str:
    """A fresh CA-signed certificate and key, as the helper's stdin."""
    chain, key, _ = generate(addresses)
    return (chain + key).decode("ascii")


def installed(reached_by: list[str] | None = None, path: Path = INSTALLED_CERT) -> BrokerCertificate | None:
    """Describe the certificate the broker has, if any.

    Args:
        reached_by: Names to check it against.
        path: The installed chain.

    Returns:
        Its description, or None when there is none or it is unreadable.
    """
    try:
        chain = _load_chain(path.read_bytes())
    except (OSError, BrokerTlsError):
        return None
    leaf = chain[0]
    names = certs._names_of(leaf)  # noqa: SLF001 - same rules as the panel's certificate
    return BrokerCertificate(
        subject=leaf.subject.rfc4514_string(),
        issuer=leaf.issuer.rfc4514_string(),
        not_after=leaf.not_valid_after_utc,
        names=names,
        fingerprint=leaf.fingerprint(hashes.SHA256()).hex(),
        uncovered=[a for a in (reached_by or []) if a and not certs._covers(names, a)],  # noqa: SLF001
        ca_available=len(chain) > 1 and _is_root_ca(chain[-1]),
    )


def installed_ca(path: Path = INSTALLED_CERT) -> bytes | None:
    """The CA at the end of the installed chain, for clients to trust.

    Returns:
        PEM, or None when the chain does not end in a self-signed CA (a
        public CA, which clients already trust, or an intermediate only).
    """
    try:
        chain = _load_chain(path.read_bytes())
    except (OSError, BrokerTlsError):
        return None
    if len(chain) > 1 and _is_root_ca(chain[-1]):
        return _pem(chain[-1])
    return None
