"""Certificates for the broker on the controller: made here, or uploaded.

The generated ones are checked the way Home Assistant will check them — a
default Python context, strict verification left on. That the helper's own
parser accepts what is built here is tested beside the helper's verbs.
"""

from __future__ import annotations

import datetime
import ssl
from pathlib import Path

import pytest
from cryptography import x509

from boneio.core.messaging import broker_tls
from tests.tls_material import TlsServer, encrypted_key, handshake, make_ca, make_leaf

ADDRESSES = ["boneio-test", "boneio-test.local", "192.168.1.50"]


@pytest.fixture(scope="module")
def generated():
    return broker_tls.generate(ADDRESSES)


def _write(tmp_path: Path, chain: bytes, key: bytes) -> tuple[Path, Path]:
    cert_path, key_path = tmp_path / "broker.crt", tmp_path / "broker.key"
    cert_path.write_bytes(chain)
    key_path.write_bytes(key)
    return cert_path, key_path


# ------------------------------------------------------------- generated


def test_the_chain_is_the_broker_then_its_ca(generated):
    chain, _, ca = generated
    certificates = x509.load_pem_x509_certificates(chain)
    assert len(certificates) == 2
    assert certificates[1] == x509.load_pem_x509_certificate(ca)
    assert certificates[0].issuer == certificates[1].subject


def test_no_ca_key_ever_leaves_the_generator(generated):
    chain, key, ca = generated
    assert b"PRIVATE KEY" not in chain + ca
    assert key.count(b"BEGIN PRIVATE KEY") == 1


def test_it_covers_the_device_and_loopback(generated):
    leaf = x509.load_pem_x509_certificates(generated[0])[0]
    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    names = {str(n) for n in san.get_values_for_type(x509.DNSName)}
    ips = {str(n) for n in san.get_values_for_type(x509.IPAddress)}
    assert {"boneio-test", "boneio-test.local", "localhost"} <= names
    assert {"192.168.1.50", "127.0.0.1"} <= ips


def test_it_lasts_ten_years_from_yesterday(generated):
    leaf = x509.load_pem_x509_certificates(generated[0])[0]
    now = datetime.datetime.now(datetime.UTC)
    assert leaf.not_valid_before_utc < now - datetime.timedelta(hours=12)
    assert leaf.not_valid_after_utc > now + datetime.timedelta(days=3640)


def test_home_assistant_would_accept_it(tmp_path, generated):
    """A default client context: strict verification on, hostname checked."""
    chain, key, ca = generated
    context = ssl.create_default_context(cadata=ca.decode())
    assert context.verify_flags & ssl.VERIFY_X509_STRICT or not hasattr(ssl, "VERIFY_X509_STRICT")
    with TlsServer(*_write(tmp_path, chain, key)) as server:
        handshake(context, server.port, "boneio-test.local")
        handshake(context, server.port, "192.168.1.50")
        with pytest.raises(ssl.SSLCertVerificationError):
            handshake(context, server.port, "other.local")
    assert server.results[:2] == [True, True]


def test_every_generation_is_a_new_ca(generated):
    again = broker_tls.generate(ADDRESSES)
    assert again[2] != generated[2]


# --------------------------------------------------------------- uploads


@pytest.fixture(scope="module")
def own_ca():
    return make_ca("Owner CA")


def test_an_upload_with_its_ca_carries_the_ca_for_clients(own_ca):
    leaf = make_leaf(own_ca, ("boneio-test.local",))
    bundle, info = broker_tls.prepare_upload(leaf.cert, leaf.key, own_ca.cert, ADDRESSES)
    assert bundle == (leaf.cert + own_ca.cert + leaf.key.strip() + b"\n").decode()
    assert info.ca_available is True
    assert "192.168.1.50" in info.uncovered


def test_a_ca_already_in_the_chain_is_not_repeated(own_ca):
    leaf = make_leaf(own_ca, ("boneio-test.local",))
    bundle, _ = broker_tls.prepare_upload(leaf.cert + own_ca.cert, leaf.key, own_ca.cert, [])
    assert bundle.count("BEGIN CERTIFICATE") == 2


def test_a_ca_that_did_not_sign_it_is_refused(own_ca):
    leaf = make_leaf(own_ca, ("boneio-test.local",))
    with pytest.raises(broker_tls.BrokerTlsError, match="did not sign"):
        broker_tls.prepare_upload(leaf.cert, leaf.key, make_ca("Other").cert, [])


def test_without_a_ca_there_is_nothing_to_hand_out(own_ca):
    leaf = make_leaf(own_ca, ("boneio-test.local",))
    _, info = broker_tls.prepare_upload(leaf.cert, leaf.key, None, [])
    assert info.ca_available is False


@pytest.mark.parametrize("problem", ["mismatch", "passphrase", "expired"])
def test_unusable_uploads_are_refused(own_ca, problem):
    leaf = make_leaf(own_ca, ("x",), expired=problem == "expired")
    key = {
        "mismatch": make_leaf(own_ca, ("y",)).key,
        "passphrase": encrypted_key(leaf),
        "expired": leaf.key,
    }[problem]
    with pytest.raises(broker_tls.BrokerTlsError):
        broker_tls.prepare_upload(leaf.cert, key, None, [])


# ------------------------------------------------------------- installed


def test_the_installed_chain_is_described_and_its_ca_offered(tmp_path, generated):
    path = tmp_path / "boneio.crt"
    path.write_bytes(generated[0])
    info = broker_tls.installed(["boneio-test.local", "10.0.0.9"], path=path)
    assert info.ca_available is True
    assert info.uncovered == ["10.0.0.9"]
    assert broker_tls.installed_ca(path=path) == generated[2]


def test_nothing_installed_is_none(tmp_path):
    assert broker_tls.installed(path=tmp_path / "missing.crt") is None
    assert broker_tls.installed_ca(path=tmp_path / "missing.crt") is None


def test_a_chain_without_a_root_offers_no_ca(tmp_path, own_ca):
    path = tmp_path / "boneio.crt"
    path.write_bytes(make_leaf(own_ca, ("x",)).cert)
    assert broker_tls.installed_ca(path=path) is None
