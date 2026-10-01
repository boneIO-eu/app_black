"""TLS on boneIO's own connection to a broker.

What matters is proved with real handshakes against a local TLS listener, not
by inspecting context flags: that each mode (system trust, own CA, client
certificate, insecure) actually connects, that a wrong CA or name is refused,
and that TLS which cannot be set up means no connection rather than a plain one.
"""

from __future__ import annotations

import asyncio
import os
import ssl
import stat
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from boneio.core.messaging import mqtt_tls
from boneio.core.messaging.mqtt_tls import MqttTlsError, build_context
from tests.tls_material import TlsServer, encrypted_key, handshake, make_ca, make_leaf


@pytest.fixture(scope="module")
def ca():
    return make_ca()


@pytest.fixture(scope="module")
def other_ca():
    return make_ca("Somebody else")


@pytest.fixture
def server_files(tmp_path, ca):
    """The broker's certificate, signed by *ca*, for localhost and 127.0.0.1."""
    return make_leaf(ca).write(tmp_path, "server")


@pytest.fixture
def ca_file(tmp_path, ca):
    path = tmp_path / "ca.pem"
    path.write_bytes(ca.cert)
    return path


# ------------------------------------------------------------- the context


def test_no_section_or_tls_off_means_a_plain_connection(tmp_path):
    assert build_context(None, tmp_path) is None
    assert build_context({}, tmp_path) is None
    assert build_context({"enabled": False, "ca_certs": "nope.pem"}, tmp_path) is None


def test_the_system_trust_store_is_used_without_a_ca(tmp_path):
    context = build_context({"enabled": True}, tmp_path)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_a_missing_ca_file_is_an_error_not_a_fallback(tmp_path):
    with pytest.raises(MqttTlsError, match="does not exist"):
        build_context({"enabled": True, "ca_certs": "certs/missing.pem"}, tmp_path)


def test_a_ca_file_that_is_not_a_certificate_is_an_error(tmp_path):
    (tmp_path / "ca.pem").write_text("hello")
    with pytest.raises(MqttTlsError, match="cannot be used"):
        build_context({"enabled": True, "ca_certs": "ca.pem"}, tmp_path)


def test_relative_paths_start_from_the_config_directory(tmp_path, ca):
    (tmp_path / "certs").mkdir()
    (tmp_path / "certs" / "ca.pem").write_bytes(ca.cert)
    assert build_context({"enabled": True, "ca_certs": "certs/ca.pem"}, tmp_path)


def test_half_a_client_certificate_is_an_error(tmp_path):
    with pytest.raises(MqttTlsError, match="both certfile and keyfile"):
        build_context({"enabled": True, "certfile": "c.pem"}, tmp_path)


def test_a_client_key_that_does_not_match_is_an_error(tmp_path, ca):
    cert, _ = make_leaf(ca, ("boneio",), client=True).write(tmp_path, "client")
    _, other_key = make_leaf(ca, ("other",), client=True).write(tmp_path, "other")
    with pytest.raises(MqttTlsError, match="client certificate cannot be used"):
        build_context(
            {"enabled": True, "certfile": str(cert), "keyfile": str(other_key)}, tmp_path
        )


def test_a_passphrase_protected_key_is_refused_without_prompting(tmp_path, ca):
    """OpenSSL would otherwise ask on a terminal a service does not have."""
    pair = make_leaf(ca, ("boneio",), client=True)
    cert, key = pair.write(tmp_path, "client")
    key.write_bytes(encrypted_key(pair))
    with pytest.raises(MqttTlsError, match="passphrase"):
        build_context({"enabled": True, "certfile": str(cert), "keyfile": str(key)}, tmp_path)


# -------------------------------------------------------- real handshakes


def test_the_broker_is_trusted_through_the_configured_ca(server_files, ca_file, tmp_path):
    context = build_context({"enabled": True, "ca_certs": str(ca_file)}, tmp_path)
    with TlsServer(*server_files) as server:
        handshake(context, server.port, "localhost")
        handshake(context, server.port, "127.0.0.1")
    assert server.results == [True, True]


def test_a_broker_signed_by_another_ca_is_refused(server_files, tmp_path, other_ca):
    (tmp_path / "other.pem").write_bytes(other_ca.cert)
    context = build_context({"enabled": True, "ca_certs": "other.pem"}, tmp_path)
    with TlsServer(*server_files) as server, pytest.raises(ssl.SSLCertVerificationError):
        handshake(context, server.port)


def test_a_broker_under_another_name_is_refused(server_files, ca_file, tmp_path):
    context = build_context({"enabled": True, "ca_certs": str(ca_file)}, tmp_path)
    with TlsServer(*server_files) as server, pytest.raises(ssl.SSLCertVerificationError):
        handshake(context, server.port, "broker.example")


def test_insecure_connects_to_anything_and_says_so_in_the_config(server_files, tmp_path):
    context = build_context({"enabled": True, "insecure": True}, tmp_path)
    with TlsServer(*server_files) as server:
        handshake(context, server.port, "broker.example")
    assert server.results == [True]


def test_a_leaf_without_authority_key_identifier_is_accepted_from_an_own_ca(tmp_path, ca, ca_file):
    """The shape most openssl recipes produce.

    The default context on Python 3.13 rejects it under VERIFY_X509_STRICT;
    for a CA the owner configured the chain and name checks are enough.
    """
    files = make_leaf(ca, with_aki=False).write(tmp_path, "noaki")
    context = build_context({"enabled": True, "ca_certs": str(ca_file)}, tmp_path)
    with TlsServer(*files) as server:
        handshake(context, server.port)
    assert server.results == [True]


def test_a_broker_requiring_client_certificates_accepts_ours(tmp_path, ca, ca_file, server_files):
    cert, key = make_leaf(ca, ("boneio",), client=True).write(tmp_path, "client")
    context = build_context(
        {"enabled": True, "ca_certs": str(ca_file), "certfile": str(cert), "keyfile": str(key)},
        tmp_path,
    )
    with TlsServer(*server_files, client_ca=ca_file) as server:
        handshake(context, server.port)
    assert server.results == [True]


def test_without_a_client_certificate_such_a_broker_refuses(tmp_path, ca_file, server_files):
    context = build_context({"enabled": True, "ca_certs": str(ca_file)}, tmp_path)
    with TlsServer(*server_files, client_ca=ca_file) as server:
        try:
            handshake(context, server.port)
            # TLS 1.3 reports the refusal on the first read, after the
            # client already considers the handshake done.
        except (ssl.SSLError, OSError):
            pass
    assert server.results and server.results[0] is not True


# ------------------------------------------------------- the MQTT client


@pytest.fixture
def config_helper():
    helper = MagicMock()
    helper.ha_discovery = False
    helper.ha_discovery_prefix = "homeassistant"
    helper.ha_types = []
    helper.serial_number = "0123456789"
    helper.subscribe_topic = "boneio/cmd/#"
    helper.topic_prefix = "boneio"
    helper.receive_boneio_autodiscovery = False
    return helper


def _client(config_helper, port, tls, config_dir):
    pytest.importorskip("aiomqtt")
    from boneio.core.messaging.mqtt import MQTTClient

    return MQTTClient(
        host="localhost",
        port=port,
        config_helper=config_helper,
        tls=tls,
        config_dir=config_dir,
        username="boneio",
        password="secret",
    )


async def test_the_real_client_connects_over_tls(config_helper, server_files, ca_file, tmp_path):
    """aiomqtt and paho with our context, against a TLS listener that CONNACKs."""
    with TlsServer(*server_files, mqtt=True) as server:
        client = _client(config_helper, server.port, {"enabled": True, "ca_certs": str(ca_file)}, tmp_path)
        assert client.tls_error is None
        async with client.asyncio_client:
            pass
    assert server.results[0] is True


async def test_the_real_client_connects_insecurely_when_told_to(config_helper, tmp_path, other_ca):
    files = make_leaf(other_ca, ("broker.example",)).write(tmp_path, "srv")
    with TlsServer(*files, mqtt=True) as server:
        client = _client(config_helper, server.port, {"enabled": True, "insecure": True}, tmp_path)
        async with client.asyncio_client:
            pass
    assert server.results[0] is True


async def test_the_real_client_refuses_a_broker_it_cannot_verify(config_helper, tmp_path, other_ca, ca_file):
    from aiomqtt import MqttError

    files = make_leaf(other_ca).write(tmp_path, "srv")
    with TlsServer(*files, mqtt=True) as server:
        client = _client(config_helper, server.port, {"enabled": True, "ca_certs": str(ca_file)}, tmp_path)
        with pytest.raises(MqttError):
            async with client.asyncio_client:
                pass


async def test_broken_tls_means_no_connection_at_all(config_helper, tmp_path):
    """Not a plain one: the password would go out in the clear."""
    from aiomqtt import MqttError

    accepted: list[bool] = []

    async def _count(reader, writer):
        accepted.append(True)
        writer.close()

    plain = await asyncio.start_server(_count, "127.0.0.1", 0)
    port = plain.sockets[0].getsockname()[1]
    try:
        client = _client(config_helper, port, {"enabled": True, "ca_certs": "missing.pem"}, tmp_path)
        assert "does not exist" in client.tls_error
        with pytest.raises(MqttError, match="TLS is on but cannot be used"):
            await client._subscribe_manager(MagicMock())
        await asyncio.sleep(0.1)
    finally:
        plain.close()
        await plain.wait_closed()
    assert accepted == []


async def test_a_fixed_file_is_picked_up_by_the_next_client(config_helper, tmp_path, ca):
    client = _client(config_helper, 8883, {"enabled": True, "ca_certs": "ca.pem"}, tmp_path)
    assert client.tls_error is not None
    (tmp_path / "ca.pem").write_bytes(ca.cert)
    client.asyncio_client = client.create_client()
    assert client.tls_error is None


# ------------------------------------------------------------- reloading


async def test_turning_tls_on_is_a_reconnect(config_helper, tmp_path, ca_file):
    client = _client(config_helper, 1883, None, tmp_path)
    assert await client.reload_credentials(
        "localhost", 1883, "boneio", "secret", tls={"enabled": True, "ca_certs": str(ca_file)}
    )
    assert client.tls_error is None
    assert await client.reload_credentials(
        "localhost", 1883, "boneio", "secret", tls={"enabled": True, "ca_certs": str(ca_file)}
    ) is False


async def test_the_same_path_with_a_new_file_is_a_reconnect(config_helper, tmp_path, ca, other_ca):
    (tmp_path / "ca.pem").write_bytes(ca.cert)
    tls = {"enabled": True, "ca_certs": "ca.pem"}
    client = _client(config_helper, 8883, tls, tmp_path)
    assert await client.reload_credentials("localhost", 8883, "boneio", "secret", tls=tls) is False
    (tmp_path / "ca.pem").write_bytes(other_ca.cert + b"\n")
    assert await client.reload_credentials("localhost", 8883, "boneio", "secret", tls=tls)


async def test_a_reload_without_tls_keeps_a_plain_client_plain(config_helper, tmp_path):
    client = _client(config_helper, 1883, None, tmp_path)
    assert await client.reload_credentials("localhost", 1883, "boneio", "secret") is False


async def test_a_reload_reports_a_tls_problem_at_once(config_helper, tmp_path):
    client = _client(config_helper, 1883, None, tmp_path)
    await client.reload_credentials(
        "localhost", 8883, "boneio", "secret", tls={"enabled": True, "ca_certs": "missing.pem"}
    )
    assert client.tls_error is not None


# ---------------------------------------------------------------- uploads


def test_a_ca_is_stored_where_the_config_points(tmp_path, ca):
    info = mqtt_tls.store_ca(ca.cert, tmp_path)
    assert info.path == "certs/mqtt-ca.pem"
    assert (tmp_path / info.path).read_bytes() == ca.cert
    assert stat.S_IMODE((tmp_path / "certs").stat().st_mode) == 0o700
    assert build_context({"enabled": True, "ca_certs": info.path}, tmp_path)


def test_something_else_is_not_stored_as_a_ca(tmp_path):
    with pytest.raises(MqttTlsError):
        mqtt_tls.store_ca(b"-----BEGIN CERTIFICATE-----\nnope\n-----END CERTIFICATE-----\n", tmp_path)
    assert not (tmp_path / "certs" / "mqtt-ca.pem").exists()


def test_a_client_pair_is_stored_with_a_private_key(tmp_path, ca):
    pair = make_leaf(ca, ("boneio",), client=True)
    mqtt_tls.store_client(pair.cert, pair.key, tmp_path)
    key = tmp_path / "certs" / "mqtt-client.key"
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert build_context(
        {"enabled": True, "certfile": "certs/mqtt-client.pem", "keyfile": "certs/mqtt-client.key"},
        tmp_path,
    )
    described = mqtt_tls.stored(tmp_path)
    assert described["client"]["key_path"] == "certs/mqtt-client.key"
    assert described["ca"] is None
    # Nothing left behind by the check.
    assert sorted(os.listdir(tmp_path / "certs")) == ["mqtt-client.key", "mqtt-client.pem"]


def test_a_mismatched_or_protected_pair_is_not_stored(tmp_path, ca):
    pair = make_leaf(ca, ("boneio",), client=True)
    other = make_leaf(ca, ("other",), client=True)
    with pytest.raises(MqttTlsError, match="does not belong"):
        mqtt_tls.store_client(pair.cert, other.key, tmp_path)
    with pytest.raises(MqttTlsError, match="passphrase"):
        mqtt_tls.store_client(pair.cert, encrypted_key(pair), tmp_path)
    assert not (tmp_path / "certs" / "mqtt-client.key").exists()


def test_stored_files_can_be_removed(tmp_path, ca):
    mqtt_tls.store_ca(ca.cert, tmp_path)
    assert mqtt_tls.remove("ca", tmp_path) is True
    assert mqtt_tls.remove("ca", tmp_path) is False
    with pytest.raises(MqttTlsError):
        mqtt_tls.remove("../etc", tmp_path)


def test_certificate_files_stay_out_of_the_yaml_globs(tmp_path, ca):
    """The file editor, backup and diagnostics bundle only walk YAML/JSON."""
    mqtt_tls.store_ca(ca.cert, tmp_path)
    pair = make_leaf(ca, ("boneio",), client=True)
    mqtt_tls.store_client(pair.cert, pair.key, tmp_path)
    found = [p for pattern in ("*.yaml", "*.yml", "*.json") for p in Path(tmp_path).rglob(pattern)]
    assert found == []


# -------------------------------------------------------------- the log


async def test_a_session_says_it_connected_and_how(config_helper, server_files, ca_file, tmp_path, caplog):
    """Without this the log never says the broker was reached, or whether it is encrypted."""
    import logging

    from unittest.mock import AsyncMock

    client = _client(config_helper, 0, {"enabled": True, "ca_certs": str(ca_file)}, tmp_path)
    with TlsServer(*server_files, mqtt=True) as server:
        client.port = server.port
        client.asyncio_client = client.create_client()
        manager = MagicMock()
        manager.reconnect_callback = AsyncMock()
        client.subscribe = AsyncMock(side_effect=asyncio.CancelledError)
        with caplog.at_level(logging.INFO, logger="boneio.core.messaging.mqtt"):
            with pytest.raises(asyncio.CancelledError):
                await client._subscribe_manager(manager)
    assert f"Connected to MQTT broker at localhost:{server.port} (TLS, broker checked against {ca_file})" in caplog.text
    assert client.tls_in_use is True


async def test_the_transport_is_described_for_each_mode(config_helper, tmp_path, ca_file):
    pytest.importorskip("aiomqtt")
    from boneio.core.messaging.mqtt import MQTTClient

    def describe(tls):
        return MQTTClient(host="h", config_helper=config_helper, tls=tls, config_dir=tmp_path).describe_transport()

    assert describe(None) == "plain text"
    assert describe({"enabled": True}) == "TLS, broker checked against the system CAs"
    assert describe({"enabled": True, "insecure": True}) == "TLS, broker certificate NOT checked"
    assert describe({"enabled": True, "ca_certs": str(ca_file)}).endswith(str(ca_file))
    assert describe({"enabled": True, "ca_certs": "missing.pem"}) == "plain text"  # never connects anyway
