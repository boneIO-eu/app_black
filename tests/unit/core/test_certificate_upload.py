"""Checking a certificate before the device starts serving it.

An operator who does not want cloud registration gets a browser-accepted panel
by uploading their own certificate. Everything here is about catching the ways
that goes wrong, because two of them are worse than not trying: a key that does
not match stops the proxy from starting, and names that do not cover the
address people type leave the same warning in place while the operator believes
it is gone.
"""

from __future__ import annotations

import datetime
import ipaddress

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from boneio.core.security.certificate import (
    CertificateError,
    device_addresses,
    inspect,
)


def _make(names=("blk239bb2",), ips=(), days=365, common_name="boneIO Black"):
    """A certificate and its key, as PEM."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.UTC)
    san = [x509.DNSName(n) for n in names]
    san += [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .sign(key, hashes.SHA256())
    )
    return (
        cert.public_bytes(serialization.Encoding.PEM),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


# --------------------------------------------------------------- the good case


def test_a_matching_pair_is_accepted():
    cert, key = _make()
    info = inspect(cert, key)
    assert "boneIO Black" in info.subject
    assert info.names == ["blk239bb2"]
    assert info.days_left > 360


def test_ip_addresses_are_read_from_the_certificate():
    """Most people reach a controller by address, not by name."""
    cert, key = _make(names=(), ips=("192.168.50.117",))
    assert inspect(cert, key).names == ["192.168.50.117"]


# ----------------------------------------------------------- the refusals


def test_a_key_from_another_certificate_is_refused():
    """Caddy would fail to start, and the panel would be gone entirely."""
    cert, _ = _make()
    _, other_key = _make()
    with pytest.raises(CertificateError, match="does not belong"):
        inspect(cert, other_key)


def test_an_expired_certificate_is_refused():
    """Louder in a browser than the self-signed one it would replace."""
    cert, key = _make(days=-1)
    with pytest.raises(CertificateError, match="expired"):
        inspect(cert, key)


def test_an_encrypted_key_is_refused_with_the_reason():
    """The proxy starts unattended; there is nobody to type a passphrase."""
    key = ec.generate_private_key(ec.SECP256R1())
    encrypted = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(b"hunter2"),
    )
    cert, _ = _make()
    with pytest.raises(CertificateError, match="passphrase"):
        inspect(cert, encrypted)


def test_something_that_is_not_a_certificate_is_refused():
    with pytest.raises(CertificateError, match="not readable PEM"):
        inspect(b"-----BEGIN CERTIFICATE-----\nnope\n", b"also nope")


def test_an_enormous_file_is_refused_before_parsing():
    with pytest.raises(CertificateError, match="too large"):
        inspect(b"x" * (300 * 1024), b"y")


# ------------------------------------------------------- names actually used


def test_an_address_the_certificate_does_not_cover_is_reported():
    """Not an error — the operator may be about to set up DNS — but silence
    here means they think the warning is gone when it is not."""
    cert, key = _make(names=("boneio.example.com",))
    info = inspect(cert, key, reached_by=["192.168.50.117", "boneio.example.com"])
    assert info.uncovered == ["192.168.50.117"]


def test_a_wildcard_covers_one_label():
    cert, key = _make(names=("*.black.boneio.app",))
    info = inspect(cert, key, reached_by=["blk239bb2.black.boneio.app"])
    assert info.uncovered == []


def test_a_wildcard_does_not_cover_the_bare_domain():
    cert, key = _make(names=("*.example.com",))
    info = inspect(cert, key, reached_by=["example.com"])
    assert info.uncovered == ["example.com"]


def test_a_wildcard_does_not_cover_two_labels():
    cert, key = _make(names=("*.example.com",))
    info = inspect(cert, key, reached_by=["a.b.example.com"])
    assert info.uncovered == ["a.b.example.com"]


def test_nothing_to_check_against_reports_nothing():
    cert, key = _make()
    assert inspect(cert, key, reached_by=[]).uncovered == []


def test_the_addresses_a_device_is_reached_by():
    assert device_addresses("blk1", "192.168.1.5") == [
        "blk1",
        "blk1.local",
        "192.168.1.5",
    ]
    assert device_addresses(None, "192.168.1.5") == ["192.168.1.5"]
