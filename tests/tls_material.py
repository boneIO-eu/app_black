"""Certificates made on the fly for the TLS tests, and a server to try them on.

Generated rather than checked in: fixtures in the repository expire, and a
test suite that starts failing on a date nobody remembers is worse than none.
"""

from __future__ import annotations

import datetime
import ipaddress
import socket
import ssl
import threading
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


@dataclass
class Pair:
    """A certificate and its key, as PEM."""

    cert: bytes
    key: bytes
    certificate: x509.Certificate
    private_key: ec.EllipticCurvePrivateKey

    def write(self, directory: Path, stem: str) -> tuple[Path, Path]:
        """Write both files and return their paths."""
        cert_path = directory / f"{stem}.pem"
        key_path = directory / f"{stem}.key"
        cert_path.write_bytes(self.cert)
        key_path.write_bytes(self.key)
        return cert_path, key_path


def _key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _pem_key(key, passphrase: bytes | None = None) -> bytes:
    encryption = (
        serialization.BestAvailableEncryption(passphrase)
        if passphrase
        else serialization.NoEncryption()
    )
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption
    )


def _pair(cert: x509.Certificate, key) -> Pair:
    return Pair(cert.public_bytes(serialization.Encoding.PEM), _pem_key(key), cert, key)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def make_ca(name: str = "Test CA") -> Pair:
    """A CA shaped the way strict verification wants it."""
    key = _key()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - datetime.timedelta(days=1))
        .not_valid_after(_now() + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return _pair(cert, key)


def make_leaf(
    ca: Pair,
    names: tuple[str, ...] = ("localhost", "127.0.0.1"),
    *,
    client: bool = False,
    with_aki: bool = True,
    days: int = 30,
    expired: bool = False,
) -> Pair:
    """A server (or client) certificate signed by *ca*.

    Args:
        ca: The issuer.
        names: DNS names and IP addresses for the SAN.
        client: Mark it for client authentication instead of server.
        with_aki: Leave the Authority Key Identifier out to imitate the
            certificates most openssl recipes produce.
        days: Lifetime.
        expired: Make one whose validity ended yesterday.
    """
    key = _key()
    san: list[x509.GeneralName] = []
    for name in names:
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            san.append(x509.DNSName(name))
    start = _now() - datetime.timedelta(days=2 if expired else 1)
    end = _now() - datetime.timedelta(days=1) if expired else _now() + datetime.timedelta(days=days)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
        .issuer_name(ca.certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage(
                [ExtendedKeyUsageOID.CLIENT_AUTH if client else ExtendedKeyUsageOID.SERVER_AUTH]
            ),
            critical=False,
        )
    )
    if san:
        builder = builder.add_extension(x509.SubjectAlternativeName(san), critical=False)
    if with_aki:
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca.private_key.public_key()),
            critical=False,
        )
    return _pair(builder.sign(ca.private_key, hashes.SHA256()), key)


def encrypted_key(pair: Pair, passphrase: bytes = b"secret") -> bytes:
    """The same key, protected by a passphrase."""
    return _pem_key(pair.private_key, passphrase)


class TlsServer:
    """A TLS listener on localhost that completes handshakes in a thread.

    Each connection is recorded as True (handshake done) or the error that
    ended it, so a test can assert which side refused.

    With ``mqtt=True`` it answers the first packet with a CONNACK, which is
    enough for a real MQTT client to consider itself connected.
    """

    def __init__(self, cert: Path, key: Path, *, client_ca: Path | None = None, mqtt: bool = False):
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(str(cert), str(key))
        if client_ca is not None:
            self.context.verify_mode = ssl.CERT_REQUIRED
            self.context.load_verify_locations(cafile=str(client_ca))
        self.mqtt = mqtt
        self.results: list[object] = []
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self._sock.settimeout(0.2)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self) -> TlsServer:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        self._sock.close()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                raw, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            raw.settimeout(5)
            try:
                with self.context.wrap_socket(raw, server_side=True) as tls:
                    self.results.append(True)
                    if self.mqtt:
                        self._answer_connect(tls)
            except (ssl.SSLError, OSError) as err:
                self.results.append(err)

    @staticmethod
    def _answer_connect(tls: ssl.SSLSocket) -> None:
        header = tls.recv(1)
        if not header:
            return
        # Remaining length, variable-byte encoded.
        length, shift = 0, 0
        while True:
            byte = tls.recv(1)[0]
            length |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                break
        while length:
            length -= len(tls.recv(length))
        tls.sendall(b"\x20\x02\x00\x00")  # CONNACK, accepted
        try:
            while tls.recv(1024):
                pass
        except OSError:
            pass


def handshake(context: ssl.SSLContext, port: int, server_hostname: str = "localhost") -> None:
    """Connect to a :class:`TlsServer` and complete the handshake, or raise."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname=server_hostname):
            pass
