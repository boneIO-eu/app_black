"""boneio-system's broker TLS verbs.

The broker is what Home Assistant and boneIO itself talk to, on a device that
may be in a cabinet, so the tests are mostly about what happens when things go
wrong: a bad certificate never reaches the broker, a broker that does not come
back gets its previous files back, and a configuration someone edited by hand
is never overwritten.
"""

from __future__ import annotations

import io
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from boneio.core.messaging import broker_tls
from tests.tls_material import encrypted_key, make_ca, make_leaf

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER = REPO_ROOT / "boneio" / "migrations" / "assets" / "helpers" / "boneio-system"
ASSET_CONF = REPO_ROOT / "boneio" / "migrations" / "assets" / "mosquitto" / "boneio.conf"


@pytest.fixture(scope="module")
def helper():
    return SourceFileLoader("boneio_system_tls", str(HELPER)).load_module()


@pytest.fixture(scope="module")
def pair():
    ca = make_ca()
    return make_leaf(ca, ("boneio.local", "192.168.1.50")), ca


class Broker:
    """A fake broker: files in a temp dir, and a switch for whether it starts."""

    def __init__(self, helper, tmp_path, monkeypatch):
        self.dir = tmp_path
        self.conf = tmp_path / "conf.d" / "boneio.conf"
        self.conf.parent.mkdir()
        self.conf.write_text(helper.MOSQUITTO_CONFS["off"])
        self.certs = tmp_path / "certs"
        self.certs.mkdir()
        self.restarts = 0
        self.calls: list[list[str]] = []
        self.starts = True
        self.owners: dict[str, tuple] = {}
        monkeypatch.setattr(helper, "MOSQUITTO_CONF", self.conf)
        monkeypatch.setattr(helper, "MOSQUITTO_CERT_DIR", self.certs)
        monkeypatch.setattr(helper, "MOSQUITTO_CERT", self.certs / "boneio.crt")
        monkeypatch.setattr(helper, "MOSQUITTO_KEY", self.certs / "boneio.key")
        monkeypatch.setattr(helper, "MQTT_TLS_START_TIMEOUT", 0.0)
        monkeypatch.setattr(helper, "_assert_root", lambda: None)
        monkeypatch.setattr(helper, "_set_owner", self._set_owner)
        monkeypatch.setattr(helper, "_run", self._run)
        monkeypatch.setattr(helper, "_broker_active", lambda: self.starts)
        monkeypatch.setattr(helper, "_port_open", lambda port, host="127.0.0.1": self.starts)

    def _set_owner(self, path, owner, mode):
        path.chmod(mode)
        # Called on the temporary file (".boneio.key.XXXX") before the rename.
        name = Path(path).name
        final = name[1:].rsplit(".", 1)[0] if name.startswith(".") else name
        self.owners[final] = (owner, mode)

    def _run(self, argv, timeout=30, tolerate=False):
        self.calls.append(list(argv))
        if argv == ["systemctl", "reset-failed", "mosquitto"]:
            assert tolerate, "a failed reset must not stop the restart"
            return 0
        assert argv == ["systemctl", "restart", "mosquitto"], argv
        self.restarts += 1
        # A broker that cannot start makes systemctl restart fail too.
        return 0 if self.starts else 1

    @property
    def cert(self) -> Path:
        return self.certs / "boneio.crt"

    @property
    def key(self) -> Path:
        return self.certs / "boneio.key"


@pytest.fixture
def broker(helper, tmp_path, monkeypatch):
    return Broker(helper, tmp_path, monkeypatch)


def _feed(monkeypatch, text: str | bytes):
    if isinstance(text, bytes):
        text = text.decode("ascii")
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


# ----------------------------------------------------------------- shapes


def test_off_is_byte_for_byte_what_migration_130_installs(helper):
    """Turning TLS off must return a device to the fleet's common state."""
    assert helper.MOSQUITTO_CONFS["off"].encode() == ASSET_CONF.read_bytes()


def test_required_keeps_plain_mqtt_on_loopback_only(helper):
    conf = helper.MOSQUITTO_CONFS["required"]
    assert "listener 1883 127.0.0.1\n" in conf
    assert "\nlistener 1883\n" not in f"\n{conf}"
    assert "listener 8883\n" in conf


def test_optional_keeps_1883_for_everyone(helper):
    assert helper.MOSQUITTO_CONFS["optional"].startswith(helper.MOSQUITTO_CONFS["off"])


def test_the_verbs_are_listed(helper):
    for verb in ("mqtt-tls-state", "mqtt-tls-cert", "mqtt-tls-cert-remove", "mqtt-tls-mode"):
        assert verb in helper.VERBS


# ------------------------------------------------------------------ state


def test_state_reports_mode_and_certificate(helper, broker, capsys):
    assert helper.main(["mqtt-tls-state"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "mode": "off", "certificate": False, "active": True, "tls_port": 8883,
    }


def test_a_hand_edited_configuration_is_reported_as_custom(helper, broker, capsys):
    broker.conf.write_text("listener 1883\npassword_file /etc/mosquitto/passwd\nlistener 9001\nprotocol websockets\n")
    helper.main(["mqtt-tls-state"])
    assert json.loads(capsys.readouterr().out)["mode"] == "custom"


# ------------------------------------------------------------ certificate


def test_a_certificate_is_installed_with_the_key_private(helper, broker, monkeypatch, pair):
    leaf, ca = pair
    _feed(monkeypatch, leaf.cert + ca.cert + leaf.key)
    assert helper.main(["mqtt-tls-cert"]) == 0
    assert broker.cert.read_bytes() == leaf.cert + ca.cert
    assert broker.key.read_bytes() == leaf.key
    assert broker.owners["boneio.key"] == (("root", "mosquitto"), 0o640)
    assert broker.owners["boneio.crt"] == (("root", "mosquitto"), 0o644)
    assert broker.key.stat().st_mode & 0o777 == 0o640
    assert not [p for p in broker.certs.iterdir() if p.name.startswith(".")]
    # TLS is off: nothing to restart yet.
    assert broker.restarts == 0


def test_with_tls_on_a_new_certificate_restarts_the_broker(helper, broker, monkeypatch, pair):
    leaf, _ = pair
    broker.conf.write_text(helper.MOSQUITTO_CONFS["optional"])
    _feed(monkeypatch, leaf.cert + leaf.key)
    assert helper.main(["mqtt-tls-cert"]) == 0
    assert broker.restarts == 1


def test_a_certificate_the_broker_rejects_is_rolled_back(helper, broker, monkeypatch, pair):
    leaf, _ = pair
    other = make_leaf(make_ca(), ("x",))
    broker.conf.write_text(helper.MOSQUITTO_CONFS["optional"])
    broker.cert.write_bytes(other.cert)
    broker.key.write_bytes(other.key)
    broker.starts = False

    _feed(monkeypatch, leaf.cert + leaf.key)
    assert helper.main(["mqtt-tls-cert"]) == 1
    assert broker.cert.read_bytes() == other.cert
    assert broker.key.read_bytes() == other.key
    assert broker.restarts == 2  # onto the new files, then back onto the old


@pytest.mark.parametrize("bundle,reason", [
    (lambda leaf, other: leaf.cert, "no key"),
    (lambda leaf, other: leaf.key, "no certificate"),
    (lambda leaf, other: leaf.cert + leaf.key + other.key, "two keys"),
    (lambda leaf, other: leaf.cert + other.key, "mismatched"),
    (lambda leaf, other: leaf.cert + encrypted_key(leaf), "passphrase"),
    (lambda leaf, other: leaf.cert + b"listener 1884\n" + leaf.key, "text between blocks"),
    (lambda leaf, other: b"-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n" + leaf.key, "garbage cert"),
])
def test_an_unusable_bundle_never_reaches_the_broker(helper, broker, monkeypatch, pair, bundle, reason):
    leaf, _ = pair
    other = make_leaf(make_ca(), ("x",))
    _feed(monkeypatch, bundle(leaf, other))
    assert helper.main(["mqtt-tls-cert"]) == 1, reason
    assert not broker.cert.exists()
    assert not broker.key.exists()
    assert broker.restarts == 0


def test_an_oversized_bundle_is_refused(helper, broker, monkeypatch):
    _feed(monkeypatch, "A" * (helper.MQTT_TLS_MAX_BYTES + 10))
    assert helper.main(["mqtt-tls-cert"]) == 1


def test_ec_parameters_blocks_are_tolerated(helper, broker, monkeypatch, pair):
    """`openssl ecparam -genkey` puts one in front of the key."""
    leaf, _ = pair
    params = b"-----BEGIN EC PARAMETERS-----\nBggqhkjOPQMBBw==\n-----END EC PARAMETERS-----\n"
    _feed(monkeypatch, leaf.cert + params + leaf.key)
    assert helper.main(["mqtt-tls-cert"]) == 0


def test_the_verbs_take_no_arguments(helper, broker, monkeypatch, pair):
    leaf, _ = pair
    _feed(monkeypatch, leaf.cert + leaf.key)
    assert helper.main(["mqtt-tls-cert", "/etc/shadow"]) == 1
    assert helper.main(["mqtt-tls-state", "x"]) == 1


def test_the_certificate_stays_while_tls_is_on(helper, broker, monkeypatch, pair):
    leaf, _ = pair
    _feed(monkeypatch, leaf.cert + leaf.key)
    helper.main(["mqtt-tls-cert"])
    broker.conf.write_text(helper.MOSQUITTO_CONFS["optional"])
    assert helper.main(["mqtt-tls-cert-remove"]) == 1
    assert broker.cert.exists()

    broker.conf.write_text(helper.MOSQUITTO_CONFS["off"])
    assert helper.main(["mqtt-tls-cert-remove"]) == 0
    assert not broker.cert.exists() and not broker.key.exists()


# ------------------------------------------------------------------- mode


def test_tls_needs_a_certificate_first(helper, broker):
    assert helper.main(["mqtt-tls-mode", "optional"]) == 1
    assert broker.conf.read_text() == helper.MOSQUITTO_CONFS["off"]
    assert broker.restarts == 0


@pytest.mark.parametrize("mode", ["optional", "required"])
def test_switching_mode_writes_the_managed_shape(helper, broker, monkeypatch, pair, mode):
    leaf, _ = pair
    _feed(monkeypatch, leaf.cert + leaf.key)
    helper.main(["mqtt-tls-cert"])

    assert helper.main(["mqtt-tls-mode", mode]) == 0
    assert broker.conf.read_text() == helper.MOSQUITTO_CONFS[mode]
    assert broker.owners["boneio.conf"] == (("mosquitto", "mosquitto"), 0o600)
    assert broker.restarts == 1

    assert helper.main(["mqtt-tls-mode", "off"]) == 0
    assert broker.conf.read_bytes() == ASSET_CONF.read_bytes()


def test_the_same_mode_is_not_a_restart(helper, broker):
    assert helper.main(["mqtt-tls-mode", "off"]) == 0
    assert broker.restarts == 0


def test_a_broker_that_does_not_come_back_gets_its_old_configuration(helper, broker, monkeypatch, pair):
    leaf, _ = pair
    _feed(monkeypatch, leaf.cert + leaf.key)
    helper.main(["mqtt-tls-cert"])
    broker.starts = False

    assert helper.main(["mqtt-tls-mode", "required"]) == 1
    assert broker.conf.read_text() == helper.MOSQUITTO_CONFS["off"]
    assert broker.restarts == 2


def test_a_hand_edited_configuration_is_never_overwritten(helper, broker, monkeypatch, pair):
    leaf, _ = pair
    _feed(monkeypatch, leaf.cert + leaf.key)
    helper.main(["mqtt-tls-cert"])
    edited = "listener 1883\npassword_file /etc/mosquitto/passwd\nlog_type all\n"
    broker.conf.write_text(edited)

    assert helper.main(["mqtt-tls-mode", "optional"]) == 1
    assert helper.main(["mqtt-tls-mode", "off"]) == 1
    assert broker.conf.read_text() == edited
    assert broker.restarts == 0


@pytest.mark.parametrize("mode", ["on", "OFF", "", "required;id", "../x"])
def test_an_unknown_mode_is_refused(helper, broker, mode):
    assert helper.main(["mqtt-tls-mode", mode]) == 1
    assert broker.restarts == 0


def test_a_missing_configuration_is_not_created(helper, broker):
    broker.conf.unlink()
    assert helper.main(["mqtt-tls-mode", "off"]) == 1
    assert not broker.conf.exists()


def test_the_helper_accepts_what_the_app_generates(helper, broker, monkeypatch):
    """The app builds the bundle; root parses it. They have to agree."""
    _feed(monkeypatch, broker_tls.generated_bundle(["boneio.local", "192.168.1.50"]))
    assert helper.main(["mqtt-tls-cert"]) == 0
    assert broker.cert.read_bytes().count(b"BEGIN CERTIFICATE") == 2


def test_the_helper_accepts_an_upload_the_app_prepared(helper, broker, monkeypatch, pair):
    leaf, ca = pair
    bundle, _ = broker_tls.prepare_upload(leaf.cert, leaf.key, ca.cert, [])
    _feed(monkeypatch, bundle)
    assert helper.main(["mqtt-tls-cert"]) == 0


def test_every_restart_clears_the_start_limit_first(helper, broker, monkeypatch, pair):
    """mosquitto.service restarts every 100 ms, at most five times in 10 s.

    A bad certificate uses that up within a second, and the rollback's own
    restart would then be refused — the broker left down in exactly the case
    the rollback is for. So reset-failed goes before each restart, forward and
    back.
    """
    leaf, _ = pair
    _feed(monkeypatch, leaf.cert + leaf.key)
    helper.main(["mqtt-tls-cert"])
    broker.starts = False

    assert helper.main(["mqtt-tls-mode", "optional"]) == 1
    reset = ["systemctl", "reset-failed", "mosquitto"]
    restart = ["systemctl", "restart", "mosquitto"]
    assert broker.calls == [reset, restart, reset, restart]
