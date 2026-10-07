"""Tests for the switch from the Caddy container to the packaged Caddy.

The switch runs as root in its own unit on a controller somebody is using. The
properties worth guarding: nothing changes until the package is in and its
configuration validates; past that point any failure puts the container back;
and the device's authority, which people have installed, survives the move.
"""

from __future__ import annotations

import fcntl
import json
import os
import socket
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER = REPO_ROOT / "boneio" / "migrations" / "assets" / "helpers" / "boneio-containers"

PLAIN = (
    "services:\n"
    "  node-red:\n"
    "    image: nodered/node-red:4.1.2-22-minimal\n"
    "  caddy:\n"
    "    image: caddy:2.11.4-alpine\n"
    "    command: [\"/init-certs.sh\"]\n"
)
CLOUD = PLAIN.replace("init-certs.sh", "init-certs-cloud.sh")
NATIVE = (
    "services:\n"
    "  node-red:\n"
    "    image: nodered/node-red:4.1.2-22-minimal\n"
    "    ports:\n"
    "      - \"127.0.0.1:1880:1880\"\n"
)
CERT = b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
KEY = b"-----BEGIN EC PRIVATE KEY-----\nMHcC\n-----END EC PRIVATE KEY-----\n"
CA_FILES = {
    "root.crt": CERT, "root.key": KEY,
    "intermediate.crt": CERT.replace(b"MIIB", b"MIIC"),
    "intermediate.key": KEY.replace(b"MHcC", b"MHcD"),
}


@pytest.fixture(scope="module")
def helper():
    return SourceFileLoader("boneio_containers_switch", str(HELPER)).load_module()


@pytest.fixture
def device(tmp_path, helper, monkeypatch):
    """A controller on the Caddy container, with everything the switch needs.

    Commands are recorded rather than run; ``device.fail`` names the commands
    that should fail, by a prefix of their argv.
    """
    project = tmp_path / "docker" / "nodered"
    trusted = tmp_path / "trusted"
    etc = tmp_path / "etc-boneio"
    state = tmp_path / "var-lib-boneio-proxy"
    for directory in (project, trusted, etc):
        directory.mkdir(parents=True)
    compose = project / "docker-compose.yaml"
    # The panel updated Node-RED: the tag is not the template's.
    compose.write_text(PLAIN.replace("4.1.2-22-minimal", "4.1.3-22-minimal"))
    (trusted / "docker-compose.yaml").write_text(PLAIN)
    (trusted / "docker-compose-cloud.yaml").write_text(CLOUD)
    (trusted / "docker-compose-native-proxy.yaml").write_text(NATIVE)
    old_ca = project / "caddy" / "data" / "caddy" / "pki" / "authorities" / "local"
    old_ca.mkdir(parents=True)
    for name, data in CA_FILES.items():
        (old_ca / name).write_bytes(data)
    # What the container recorded: its own hostname, not the device's.
    (project / "caddy" / "data" / "last_hostname").write_text("boneio\n")
    prerequisites = []
    for name in ("boneio.conf", "proxy-config", "caddy-stable.list", "keyring.gpg", "caddy.pref"):
        (etc / name).write_text("x\n")
        prerequisites.append(etc / name)

    patches = {
        "PROJECT_DIR": project,
        "COMPOSE_FILE": compose,
        "TRUSTED_DIR": trusted,
        "COMPOSE_TEMPLATE": trusted / "docker-compose.yaml",
        "COMPOSE_CLOUD_TEMPLATE": trusted / "docker-compose-cloud.yaml",
        "COMPOSE_NATIVE_TEMPLATE": trusted / "docker-compose-native-proxy.yaml",
        "NATIVE_MARKER": etc / "proxy-native",
        "CLOUD_MARKER": etc / "proxy-cloud",
        "PROXY_LOCK": tmp_path / "boneio-proxy.lock",
        "CADDY_DATA": tmp_path / "caddy-home" / ".local" / "share" / "caddy",
        "OLD_CA": old_ca,
        "ENV_FILE": project / ".env",
        "SWITCH_DIR": state,
        "SWITCH_STATE": state / "switch.json",
        "SWITCH_LOG": state / "switch.log",
        "COMPOSE_BEFORE": state / "compose.before",
        "HOSTNAME_FILE": state / "last_hostname",
        "SWITCH_PREREQUISITES": tuple(prerequisites),
        "PROBE_TIMEOUT": 0.0,
        "PROBE_INTERVAL": 0.0,
    }
    for name, value in patches.items():
        monkeypatch.setattr(helper, name, value)
    (tmp_path / "caddy-home").mkdir()
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    monkeypatch.setattr(helper, "_in_switch_unit", lambda: True)
    monkeypatch.setattr(helper, "_switch_unit_active", lambda: False)
    monkeypatch.setattr(socket, "gethostname", lambda: "boneio-kitchen")
    monkeypatch.setattr(
        helper, "_root_owned",
        lambda path: os.path.isfile(path) and not os.path.islink(path),
    )

    class Device:
        calls: list[list[str]] = []
        fail: set[str] = set()
        probes: list[bool] = []
        lock_held: list[bool] = []

    dev = Device()
    dev.calls, dev.fail, dev.probes, dev.lock_held = [], set(), [], []
    dev.compose, dev.etc, dev.state, dev.project = compose, etc, state, project

    def fake_cmd(argv, log, timeout=900):
        dev.calls.append(list(argv))
        with open(helper.PROXY_LOCK, "rb") as other:
            try:
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                dev.lock_held.append(False)
            except BlockingIOError:
                dev.lock_held.append(True)
        joined = " ".join(argv)
        return 1 if any(joined.startswith(prefix) for prefix in dev.fail) else 0

    def fake_probe(port):
        answer = dev.probe(port)
        dev.probes.append(answer)
        return answer

    dev.probe = lambda port: True
    monkeypatch.setattr(helper, "_switch_cmd", fake_cmd)
    monkeypatch.setattr(helper, "_proxy_answers", fake_probe)
    return dev


def _state(helper) -> dict:
    return json.loads(helper.SWITCH_STATE.read_text())


def _index(calls, prefix):
    for i, argv in enumerate(calls):
        if " ".join(argv).startswith(prefix):
            return i
    raise AssertionError(f"{prefix!r} never ran: {calls}")


# ------------------------------------------------------------------ success


def test_switch_happy_path_ends_native(helper, device):
    before = device.compose.read_text()

    assert helper.main(["proxy-switch-run"]) == 0

    assert helper.NATIVE_MARKER.exists()
    # The native template, with the Node-RED version the panel had chosen.
    assert device.compose.read_text() == NATIVE.replace("4.1.2-22-minimal", "4.1.3-22-minimal")
    assert helper.COMPOSE_BEFORE.read_text() == before
    state = _state(helper)
    assert state["state"] == "done"
    assert state["attempts"] == 1
    assert state["error"] is None
    calls = device.calls
    order = [
        "apt-get update --error-on=any -o Dir::Etc::sourcelist=sources.list.d/caddy-stable.list "
        "-o Dir::Etc::sourceparts=- -o APT::Get::List-Cleanup=0 -o DPkg::Lock::Timeout=300",
        "apt-get install -y --no-install-recommends -o DPkg::Lock::Timeout=300 caddy",
        f"{helper.PROXY_CONFIG} --check",
        f"docker compose -f {device.compose} up -d --remove-orphans",
        "systemctl daemon-reload",
        "systemctl enable --now caddy",
    ]
    positions = [_index(calls, prefix) for prefix in order]
    assert positions == sorted(positions)
    # The generator exports the root only once Caddy has created it.
    assert calls[-1] == ["systemctl", "reload", "caddy"]
    assert all(device.lock_held), "every step must run under the proxy lock"
    assert helper.SWITCH_LOG.exists()


def test_the_current_hostname_is_recorded_not_the_containers(helper, device):
    """A recorded name that differs makes the generator discard the authority."""
    assert helper.main(["proxy-switch-run"]) == 0
    assert helper.HOSTNAME_FILE.read_text() == "boneio-kitchen\n"


def test_a_failed_reload_after_a_good_probe_still_ends_native(helper, device):
    device.fail = {"systemctl reload caddy"}
    assert helper.main(["proxy-switch-run"]) == 0
    assert _state(helper)["state"] == "done"
    assert helper.NATIVE_MARKER.exists()


# ------------------------------------------------------- nothing changed yet


def test_no_network_leaves_the_container_untouched(helper, device):
    before = device.compose.read_text()
    device.fail = {"apt-get update"}

    assert helper.main(["proxy-switch-run"]) == 1

    assert device.compose.read_text() == before
    assert not helper.NATIVE_MARKER.exists()
    assert not helper.COMPOSE_BEFORE.exists()
    assert not any(argv[0] == "docker" for argv in device.calls)
    state = _state(helper)
    assert state["state"] == "failed"
    assert "apt-get update" in state["error"] or "apt-update" in state["error"]

    assert helper.main(["proxy-switch-run"]) == 1
    assert _state(helper)["attempts"] == 2


def test_a_compose_file_that_is_no_template_is_refused(helper, device):
    device.compose.write_text(PLAIN + "  extra:\n    image: alpine\n")
    assert helper.main(["proxy-switch-run"]) == 1
    assert device.calls == []
    assert _state(helper)["state"] == "failed"


def test_a_missing_prerequisite_is_refused(helper, device):
    helper.SWITCH_PREREQUISITES[0].unlink()
    assert helper.main(["proxy-switch-run"]) == 1
    assert device.calls == []
    assert _state(helper)["state"] == "failed"


def test_an_invalid_configuration_stops_before_the_container(helper, device):
    device.fail = {f"{helper.PROXY_CONFIG} --check"}
    before = device.compose.read_text()
    assert helper.main(["proxy-switch-run"]) == 1
    assert device.compose.read_text() == before
    assert not any(argv[0] == "docker" for argv in device.calls)
    assert _state(helper)["state"] == "failed"


# ----------------------------------------------------------------- rollback


def test_probe_failure_rolls_back_to_the_container(helper, device):
    before = device.compose.read_text()
    # The packaged Caddy never answers; the container does once it is back.
    device.probe = lambda port: not helper.NATIVE_MARKER.exists()

    assert helper.main(["proxy-switch-run"]) == 1

    assert device.compose.read_text() == before
    assert not helper.NATIVE_MARKER.exists()
    assert not helper.CLOUD_MARKER.exists()
    disable = _index(device.calls, "systemctl disable --now caddy")
    up = _index(device.calls[disable:], f"docker compose -f {device.compose} up -d") + disable
    assert device.calls[up] == ["docker", "compose", "-f", str(device.compose), "up", "-d"]
    # The package stays, so the next attempt does not download it again.
    assert not any("remove" in argv or "purge" in argv for argv in device.calls)
    state = _state(helper)
    assert state["state"] == "rolled_back"
    assert state["error"]
    assert device.probes[-1] is True


def test_an_unexpected_error_after_the_compose_file_still_rolls_back(
    helper, device, monkeypatch
):
    """No kind of error may leave the controller with neither proxy."""
    before = device.compose.read_text()
    recording = helper._switch_cmd

    def explode(argv, log, timeout=900):
        if argv[:2] == ["systemctl", "enable"]:
            raise RuntimeError("unexpected")
        return recording(argv, log, timeout)

    monkeypatch.setattr(helper, "_switch_cmd", explode)
    assert helper.main(["proxy-switch-run"]) == 1
    assert device.compose.read_text() == before
    assert not helper.NATIVE_MARKER.exists()
    assert _state(helper)["state"] == "rolled_back"


def test_a_rollback_whose_container_does_not_answer_says_so(helper, device):
    device.probe = lambda port: False
    assert helper.main(["proxy-switch-run"]) == 1
    state = _state(helper)
    assert state["state"] == "rolled_back"
    assert "container" in state["error"]


# ------------------------------------------------------------- the authority


def test_existing_ca_is_carried_over_and_never_overwritten(helper, device):
    assert helper.main(["proxy-switch-run"]) == 0
    local = helper.CADDY_DATA / "pki" / "authorities" / "local"
    for name, data in CA_FILES.items():
        assert (local / name).read_bytes() == data
        expected = 0o600 if name.endswith(".key") else 0o644
        assert (local / name).stat().st_mode & 0o777 == expected
    assert sorted(p.name for p in local.iterdir()) == sorted(CA_FILES)


def test_a_native_authority_is_never_overwritten(helper, device):
    local = helper.CADDY_DATA / "pki" / "authorities" / "local"
    local.mkdir(parents=True)
    (local / "root.crt").write_bytes(b"already native\n")

    assert helper.main(["proxy-switch-run"]) == 0

    assert (local / "root.crt").read_bytes() == b"already native\n"
    assert not (local / "root.key").exists()


@pytest.mark.parametrize("trap", ["symlink", "hardlink", "oversize", "not-pem", "missing"])
def test_an_untrustworthy_old_authority_is_skipped(helper, device, tmp_path, trap):
    """The old data belongs to boneio; root copies nothing it cannot vouch for."""
    key = helper.OLD_CA / "root.key"
    if trap == "symlink":
        secret = tmp_path / "shadow"
        secret.write_bytes(KEY)
        key.unlink()
        key.symlink_to(secret)
    elif trap == "hardlink":
        os.link(key, tmp_path / "second-name")
    elif trap == "oversize":
        key.write_bytes(KEY + b"A" * (64 * 1024))
    elif trap == "not-pem":
        key.write_bytes(b"not a key\n")
    else:
        key.unlink()

    assert helper.main(["proxy-switch-run"]) == 0

    assert not (helper.CADDY_DATA / "pki").exists()
    assert _state(helper)["state"] == "done"


# -------------------------------------------------------------------- cloud


def test_cloud_compose_becomes_the_cloud_marker(helper, device):
    device.compose.write_text(CLOUD)
    assert helper.main(["proxy-switch-run"]) == 0
    assert helper.CLOUD_MARKER.exists()


def test_a_stale_cloud_marker_goes_with_a_plain_compose(helper, device):
    helper.CLOUD_MARKER.write_text("")
    assert helper.main(["proxy-switch-run"]) == 0
    assert not helper.CLOUD_MARKER.exists()


def test_rollback_removes_the_cloud_marker_it_created(helper, device):
    device.compose.write_text(CLOUD)
    device.probe = lambda port: not helper.NATIVE_MARKER.exists()
    assert helper.main(["proxy-switch-run"]) == 1
    assert not helper.CLOUD_MARKER.exists()
    assert device.compose.read_text() == CLOUD


# --------------------------------------------------------- start and state


def test_switch_refuses_outside_its_unit(helper, device, monkeypatch):
    monkeypatch.setattr(helper, "_in_switch_unit", lambda: False)
    assert helper.main(["proxy-switch-run"]) == 1
    assert device.calls == []
    assert not helper.SWITCH_STATE.exists()


def test_start_runs_the_switch_in_its_own_unit(helper, device, monkeypatch):
    ran = []
    monkeypatch.setattr(helper, "_run", lambda argv, timeout=120: ran.append(argv) or 0)
    assert helper.main(["proxy-switch-start"]) == 0
    assert ran == [[
        "systemd-run", "--unit", "boneio-proxy-switch.service", "--collect",
        "--no-block", "--quiet", "--description", "boneIO switch to the packaged Caddy",
        "--property", "CPUWeight=50", "--property", "IOWeight=50",
        "/usr/sbin/boneio-containers", "proxy-switch-run",
    ]]


def test_second_start_while_running_is_refused(helper, device, monkeypatch):
    ran = []
    monkeypatch.setattr(helper, "_run", lambda argv, timeout=120: ran.append(argv) or 0)
    monkeypatch.setattr(helper, "_switch_unit_active", lambda: True)
    assert helper.main(["proxy-switch-start"]) == 1
    assert ran == []


def test_start_is_refused_once_native(helper, device, monkeypatch):
    ran = []
    monkeypatch.setattr(helper, "_run", lambda argv, timeout=120: ran.append(argv) or 0)
    helper.NATIVE_MARKER.write_text("")
    assert helper.main(["proxy-switch-start"]) == 1
    assert ran == []


def test_state_prints_the_record_and_the_log(helper, device, capsys):
    assert helper.main(["proxy-switch-state"]) == 0
    empty = json.loads(capsys.readouterr().out)
    assert empty["state"] is None and empty["attempts"] == 0 and empty["running"] is False

    device.fail = {"apt-get update"}
    helper.main(["proxy-switch-run"])
    capsys.readouterr()
    assert helper.main(["proxy-switch-state"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["state"] == "failed"
    assert shown["native"] is False
    assert "apt-get update" in shown["log"]


def test_the_switch_verbs_are_listed(helper, capsys):
    assert helper.main(["--list-verbs"]) == 0
    verbs = json.loads(capsys.readouterr().out)
    for verb in ("proxy-switch-start", "proxy-switch-run", "proxy-switch-state"):
        assert verb in verbs
    assert "proxy-switch-state" in helper.READ_ONLY_VERBS
    # It takes the lock itself; a second flock from main would wait on it.
    assert "proxy-switch-run" not in helper.LOCKED_VERBS


# ----------------------------------------------------------------- recovery


class PowerLoss(BaseException):
    """What a power loss or SIGTERM looks like to the run: nothing is caught."""


def _interrupt_at(helper, device, monkeypatch, prefix):
    """Run the switch until *prefix* would run, and cut it off there."""
    recording = helper._switch_cmd

    def cut(argv, log, timeout=900):
        if " ".join(argv).startswith(prefix):
            raise PowerLoss
        return recording(argv, log, timeout)

    monkeypatch.setattr(helper, "_switch_cmd", cut)
    with pytest.raises(PowerLoss):
        helper.main(["proxy-switch-run"])
    monkeypatch.setattr(helper, "_switch_cmd", recording)
    assert _state(helper)["state"] == "running"
    device.calls.clear()


def test_recovery_after_the_compose_swap_brings_the_container_back(helper, device, monkeypatch):
    before = device.compose.read_text()
    _interrupt_at(helper, device, monkeypatch, "docker compose")
    assert device.compose.read_text().startswith(NATIVE[:40])
    assert not helper.NATIVE_MARKER.exists()

    assert helper.main(["proxy-switch-recover"]) == 0

    assert device.compose.read_text() == before
    assert ["docker", "compose", "-f", str(device.compose), "up", "-d"] in device.calls
    state = _state(helper)
    assert state["state"] == "rolled_back"
    assert state["error"] == "interrupted"


def test_recovery_after_the_marker_removes_it_and_stops_caddy(helper, device, monkeypatch):
    _interrupt_at(helper, device, monkeypatch, "systemctl enable")
    assert helper.NATIVE_MARKER.exists()

    assert helper.main(["proxy-switch-recover"]) == 0

    assert not helper.NATIVE_MARKER.exists()
    assert ["systemctl", "disable", "--now", "caddy"] in device.calls
    assert _state(helper)["state"] == "rolled_back"


def test_recovery_removes_only_a_cloud_marker_the_run_created(helper, device, monkeypatch):
    device.compose.write_text(CLOUD)
    _interrupt_at(helper, device, monkeypatch, "docker compose")
    assert helper.CLOUD_MARKER.exists()
    assert helper.main(["proxy-switch-recover"]) == 0
    assert not helper.CLOUD_MARKER.exists()
    assert device.compose.read_text() == CLOUD


def test_recovery_before_the_compose_swap_touches_no_container(helper, device, monkeypatch):
    before = device.compose.read_text()
    # An older attempt's copy must not be "restored" by a later interruption.
    helper.COMPOSE_BEFORE.parent.mkdir(parents=True, exist_ok=True)
    helper.COMPOSE_BEFORE.write_text("stale\n")
    _interrupt_at(helper, device, monkeypatch, "apt-get install")

    assert helper.main(["proxy-switch-recover"]) == 0

    assert device.compose.read_text() == before
    assert device.calls == []
    state = _state(helper)
    assert state["state"] == "failed"
    assert state["error"] == "interrupted"


def test_recovery_after_a_finished_switch_does_nothing(helper, device):
    assert helper.main(["proxy-switch-run"]) == 0
    device.calls.clear()
    assert helper.main(["proxy-switch-recover"]) == 0
    assert device.calls == []
    assert _state(helper)["state"] == "done"
    assert helper.NATIVE_MARKER.exists()


def test_recovery_leaves_a_running_switch_alone(helper, device, monkeypatch):
    _interrupt_at(helper, device, monkeypatch, "docker compose")
    native = device.compose.read_text()
    monkeypatch.setattr(helper, "_switch_unit_active", lambda: True)
    assert helper.main(["proxy-switch-recover"]) == 0
    assert device.calls == []
    assert device.compose.read_text() == native
    assert _state(helper)["state"] == "running"


def test_start_leaves_recovery_to_the_unit(helper, device, monkeypatch):
    """Recovery can take minutes; boneIO's call to start must not wait for it."""
    _interrupt_at(helper, device, monkeypatch, "systemctl enable")
    assert helper.NATIVE_MARKER.exists()
    ran = []
    monkeypatch.setattr(helper, "_run", lambda argv, timeout=120: ran.append(argv) or 0)

    assert helper.main(["proxy-switch-start"]) == 0

    assert device.calls == []
    assert ran and ran[0][0] == "systemd-run"


def test_the_run_recovers_an_interrupted_switch_first(helper, device, monkeypatch):
    _interrupt_at(helper, device, monkeypatch, "systemctl enable")

    assert helper.main(["proxy-switch-run"]) == 0

    disable = _index(device.calls, "systemctl disable --now caddy")
    assert disable < _index(device.calls, "apt-get update")
    assert _state(helper)["state"] == "done"
    assert "interrupted" in helper.SWITCH_LOG.read_text()


@pytest.mark.parametrize("damage", ["empty", "symlink", "group-writable", "not-a-template"])
def test_recovery_rebuilds_a_compose_file_it_cannot_trust(
    helper, device, monkeypatch, tmp_path, damage
):
    """A power loss can bring compose.before back empty; that must not be restored."""
    before = device.compose.read_text()
    _interrupt_at(helper, device, monkeypatch, "docker compose")
    saved = helper.COMPOSE_BEFORE
    if damage == "empty":
        saved.write_text("")
    elif damage == "symlink":
        elsewhere = tmp_path / "planted"
        elsewhere.write_text(before)
        saved.unlink()
        saved.symlink_to(elsewhere)
    elif damage == "group-writable":
        os.chmod(saved, 0o664)
    else:
        saved.write_text("services:\n  evil:\n    image: alpine\n")

    assert helper.main(["proxy-switch-recover"]) == 0

    # The plain template, with the Node-RED version the run recorded.
    assert device.compose.read_text() == before
    assert ["docker", "compose", "-f", str(device.compose), "up", "-d"] in device.calls
    assert _state(helper)["state"] == "rolled_back"


def test_a_rebuilt_cloud_compose_is_the_cloud_template(helper, device, monkeypatch):
    device.compose.write_text(CLOUD)
    _interrupt_at(helper, device, monkeypatch, "docker compose")
    helper.COMPOSE_BEFORE.write_text("")
    assert helper.main(["proxy-switch-recover"]) == 0
    assert device.compose.read_text() == CLOUD


def test_the_boot_unit_runs_recovery_only_after_an_interruption(helper):
    unit = (
        REPO_ROOT / "boneio" / "migrations" / "assets" / "systemd" / "boneio-proxy-recover.service"
    ).read_text()
    lines = dict(
        line.split("=", 1) for line in unit.splitlines() if "=" in line and not line.startswith("#")
    )
    program, verb = lines["ExecStart"].split()
    assert program == helper.HELPER_SELF
    assert verb in helper.ALL_VERBS
    assert "docker.service" in lines["After"]
    # The condition matches the record the run writes while it runs.
    condition = lines["ExecCondition"]
    assert str(helper.SWITCH_STATE) in condition
    assert '"state": "running"' in json.dumps({"state": "running"}, indent=1)
    assert '\\"state\\": \\"running\\"' in condition
