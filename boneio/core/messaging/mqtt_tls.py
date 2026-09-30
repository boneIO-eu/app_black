"""TLS for boneIO's own connection to an MQTT broker.

Two jobs: turn the ``mqtt.tls`` section into an :class:`ssl.SSLContext`, and
keep the certificate files the panel uploads for it.

What this module guarantees, and why it must not be relaxed:

- TLS that is switched on and cannot be set up is an error, never a quiet
  step down to plain text. The broker password travels in the CONNECT packet;
  falling back would send it in the clear to whoever answers on that port,
  which is exactly what the owner turned TLS on to prevent.
- Hostname and chain checks stay on unless ``insecure`` says otherwise in so
  many words. A context that encrypts without checking is one an attacker can
  terminate.
- A client key is written with its mode already set, so it is never readable
  by another local account, not even between the write and a chmod.
"""

from __future__ import annotations

import logging
import os
import ssl
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes

_LOGGER = logging.getLogger(__name__)

#: Where uploaded files go, relative to the directory holding config.yaml.
#: Outside the YAML globs on purpose: the file editor, the configuration backup
#: and the diagnostics bundle all walk ``*.yaml`` and ``*.json``, so a client
#: key kept here is never listed, downloaded or shipped to support.
CERT_DIR_NAME = "certs"
CA_FILE = "mqtt-ca.pem"
CLIENT_CERT_FILE = "mqtt-client.pem"
CLIENT_KEY_FILE = "mqtt-client.key"

#: A certificate chain is a few kilobytes; a megabyte of PEM is the wrong file.
MAX_PEM_BYTES = 256 * 1024

KEY_MODE = 0o600
CERT_MODE = 0o644
DIR_MODE = 0o700


class MqttTlsError(Exception):
    """TLS was asked for and cannot be set up, or an upload is unusable."""


def tls_enabled(tls: Mapping[str, Any] | None) -> bool:
    """Whether the section asks for TLS at all.

    Args:
        tls: The ``mqtt.tls`` section, or None when there is none.

    Returns:
        True when TLS is switched on.
    """
    return isinstance(tls, Mapping) and bool(tls.get("enabled"))


def resolve(path: str, config_dir: Path) -> Path:
    """A configured path, made absolute against the config directory.

    Args:
        path: As written in the configuration.
        config_dir: The directory holding config.yaml.

    Returns:
        The absolute path.
    """
    candidate = Path(os.path.expanduser(path))
    return candidate if candidate.is_absolute() else config_dir / candidate


def _no_passphrase() -> bytes:
    """Refuse to prompt for a key passphrase.

    Without a callback, OpenSSL asks on the controlling terminal, and a
    service started by systemd has nobody there to answer.
    """
    return b""


def build_context(
    tls: Mapping[str, Any] | None, config_dir: Path
) -> ssl.SSLContext | None:
    """The context to connect with, or None when TLS is off.

    Args:
        tls: The ``mqtt.tls`` section.
        config_dir: The directory relative paths are resolved from.

    Returns:
        A client context, or None for a plain connection.

    Raises:
        MqttTlsError: If TLS is on and a file is missing or unusable.
    """
    if not tls_enabled(tls):
        return None
    assert tls is not None

    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

    ca_certs = tls.get("ca_certs")
    if ca_certs:
        path = resolve(str(ca_certs), config_dir)
        if not path.is_file():
            raise MqttTlsError(f"The CA certificate {path} does not exist.")
        try:
            context.load_verify_locations(cafile=str(path))
        except (ssl.SSLError, OSError, ValueError) as err:
            raise MqttTlsError(
                f"The CA certificate {path} cannot be used: {err}"
            ) from err
        # Strict mode rejects certificates that are merely unfashionable —
        # a leaf without an Authority Key Identifier, which is what the
        # openssl recipes most private CAs were made with produce. The
        # chain is still verified and the hostname still checked; only the
        # extra shape rules are dropped, and only for a CA the owner chose.
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT

    certfile = tls.get("certfile")
    keyfile = tls.get("keyfile")
    if bool(certfile) != bool(keyfile):
        raise MqttTlsError(
            "A client certificate needs both certfile and keyfile."
        )
    if certfile and keyfile:
        cert_path = resolve(str(certfile), config_dir)
        key_path = resolve(str(keyfile), config_dir)
        for path in (cert_path, key_path):
            if not path.is_file():
                raise MqttTlsError(f"The client certificate file {path} does not exist.")
        try:
            context.load_cert_chain(
                certfile=str(cert_path), keyfile=str(key_path), password=_no_passphrase
            )
        except (ssl.SSLError, OSError, ValueError) as err:
            raise MqttTlsError(
                f"The client certificate cannot be used: {err}. The key must "
                "match the certificate and must not be passphrase-protected."
            ) from err

    if tls.get("insecure"):
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    return context


def fingerprint(tls: Mapping[str, Any] | None, config_dir: Path) -> tuple:
    """Everything a reconnect depends on, for telling whether it changed.

    The files are part of it, not only the section: uploading a new CA to the
    same path changes nothing in the configuration, and the running context
    would keep trusting the old one until the next outage.

    Args:
        tls: The ``mqtt.tls`` section.
        config_dir: The directory relative paths are resolved from.

    Returns:
        A comparable value.
    """
    if not isinstance(tls, Mapping):
        return ()
    items = tuple(sorted((str(k), repr(v)) for k, v in tls.items()))
    files = []
    for key in ("ca_certs", "certfile", "keyfile"):
        value = tls.get(key)
        if not value:
            continue
        try:
            st = resolve(str(value), config_dir).stat()
            files.append((key, st.st_mtime_ns, st.st_size, st.st_ino))
        except OSError:
            files.append((key, None))
    return items + tuple(files)


# ------------------------------------------------------------------- uploads


@dataclass
class StoredFile:
    """A certificate file the panel keeps, as the API describes it."""

    path: str
    subject: str
    issuer: str
    not_after: str
    names: list[str]
    fingerprint: str
    count: int = 1

    def to_dict(self) -> dict:
        """Serialise for the API."""
        return {
            "path": self.path,
            "subject": self.subject,
            "issuer": self.issuer,
            "not_after": self.not_after,
            "names": self.names,
            "fingerprint": self.fingerprint,
            "count": self.count,
        }


def _parse_certificates(pem: bytes) -> list[x509.Certificate]:
    if len(pem) > MAX_PEM_BYTES:
        raise MqttTlsError("That file is far too large to be a certificate.")
    try:
        certificates = x509.load_pem_x509_certificates(pem)
    except ValueError as err:
        raise MqttTlsError(f"That is not a PEM certificate: {err}") from err
    if not certificates:
        raise MqttTlsError("That file holds no certificate.")
    return certificates


def _names(cert: x509.Certificate) -> list[str]:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return []
    return [str(n) for n in san.get_values_for_type(x509.DNSName)] + [
        str(n) for n in san.get_values_for_type(x509.IPAddress)
    ]


def _describe(pem: bytes, relative: str) -> StoredFile:
    certificates = _parse_certificates(pem)
    first = certificates[0]
    return StoredFile(
        path=relative,
        subject=first.subject.rfc4514_string(),
        issuer=first.issuer.rfc4514_string(),
        not_after=first.not_valid_after_utc.isoformat(),
        names=_names(first),
        fingerprint=first.fingerprint(hashes.SHA256()).hex(),
        count=len(certificates),
    )


def _cert_dir(config_dir: Path) -> Path:
    directory = config_dir / CERT_DIR_NAME
    directory.mkdir(mode=DIR_MODE, exist_ok=True)
    directory.chmod(DIR_MODE)
    return directory


def _write(path: Path, data: bytes, mode: int) -> None:
    """Replace *path* atomically, created with *mode* from the start."""
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        os.fchmod(handle, mode)
        with os.fdopen(handle, "wb") as out:
            out.write(data)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def store_ca(pem: bytes, config_dir: Path) -> StoredFile:
    """Keep the CA that boneIO will check the broker's certificate against.

    Args:
        pem: One or more certificates in PEM.
        config_dir: The directory holding config.yaml.

    Returns:
        What was stored, with the path to put in ``mqtt.tls.ca_certs``.

    Raises:
        MqttTlsError: If it is not usable as a trust anchor.
    """
    relative = f"{CERT_DIR_NAME}/{CA_FILE}"
    info = _describe(pem, relative)
    # The same parser the connection will use, so an upload it accepts is
    # one the client can load.
    try:
        ssl.create_default_context().load_verify_locations(cadata=pem.decode("ascii"))
    except (ssl.SSLError, UnicodeDecodeError, ValueError) as err:
        raise MqttTlsError(f"That certificate cannot be used as a CA: {err}") from err
    try:
        _write(_cert_dir(config_dir) / CA_FILE, pem, CERT_MODE)
    except OSError as err:
        raise MqttTlsError(f"Could not store the CA certificate: {err}") from err
    _LOGGER.info("MQTT CA certificate stored: %s", info.subject)
    return info


def store_client(cert_pem: bytes, key_pem: bytes, config_dir: Path) -> StoredFile:
    """Keep a client certificate and its key.

    Args:
        cert_pem: The certificate, optionally followed by its chain.
        key_pem: Its unencrypted private key.
        config_dir: The directory holding config.yaml.

    Returns:
        What was stored; the key sits beside it as ``mqtt-client.key``.

    Raises:
        MqttTlsError: If the pair cannot be loaded together.
    """
    if len(key_pem) > MAX_PEM_BYTES:
        raise MqttTlsError("That file is far too large to be a key.")
    info = _describe(cert_pem, f"{CERT_DIR_NAME}/{CLIENT_CERT_FILE}")
    directory = _cert_dir(config_dir)

    # Checked with OpenSSL itself, from files, exactly as the connection will
    # load them — a key that does not match, or wants a passphrase, fails here
    # instead of at the next reconnect.
    with tempfile.TemporaryDirectory(dir=directory) as scratch:
        cert_tmp = Path(scratch) / "cert.pem"
        key_tmp = Path(scratch) / "key.pem"
        _write(cert_tmp, cert_pem, CERT_MODE)
        _write(key_tmp, key_pem, KEY_MODE)
        try:
            ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_cert_chain(
                str(cert_tmp), str(key_tmp), password=_no_passphrase
            )
        except (ssl.SSLError, ValueError) as err:
            raise MqttTlsError(
                "That key does not belong to that certificate, or it is "
                f"protected by a passphrase ({err}). boneIO connects unattended "
                "and has nobody to ask for one."
            ) from err

    try:
        _write(directory / CLIENT_KEY_FILE, key_pem, KEY_MODE)
        _write(directory / CLIENT_CERT_FILE, cert_pem, CERT_MODE)
    except OSError as err:
        raise MqttTlsError(f"Could not store the client certificate: {err}") from err
    _LOGGER.info("MQTT client certificate stored: %s", info.subject)
    return info


def stored(config_dir: Path) -> dict[str, dict | None]:
    """Describe the files the panel has stored.

    Args:
        config_dir: The directory holding config.yaml.

    Returns:
        ``ca`` and ``client``, each described or None.
    """
    directory = config_dir / CERT_DIR_NAME
    result: dict[str, dict | None] = {"ca": None, "client": None}
    for kind, name in (("ca", CA_FILE), ("client", CLIENT_CERT_FILE)):
        path = directory / name
        if not path.is_file():
            continue
        if kind == "client" and not (directory / CLIENT_KEY_FILE).is_file():
            continue
        try:
            result[kind] = _describe(path.read_bytes(), f"{CERT_DIR_NAME}/{name}").to_dict()
        except (OSError, MqttTlsError) as err:
            _LOGGER.warning("Stored MQTT certificate %s is unreadable: %s", path, err)
    if result["client"] is not None:
        result["client"]["key_path"] = f"{CERT_DIR_NAME}/{CLIENT_KEY_FILE}"
    return result


def remove(kind: str, config_dir: Path) -> bool:
    """Delete a stored file, or the client pair.

    Args:
        kind: ``ca`` or ``client``.
        config_dir: The directory holding config.yaml.

    Returns:
        True when something was removed.

    Raises:
        MqttTlsError: For an unknown kind, or when a file cannot be removed.
    """
    names = {"ca": (CA_FILE,), "client": (CLIENT_CERT_FILE, CLIENT_KEY_FILE)}.get(kind)
    if names is None:
        raise MqttTlsError(f"Unknown certificate kind {kind!r}.")
    removed = False
    for name in names:
        try:
            (config_dir / CERT_DIR_NAME / name).unlink()
            removed = True
        except FileNotFoundError:
            continue
        except OSError as err:
            raise MqttTlsError(f"Could not remove {name}: {err}") from err
    return removed
