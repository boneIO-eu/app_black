"""The support bundle.

The bundle leaves the building — it goes to an inbox — so the tests that
matter most are the ones about what must not be in it.
"""

from __future__ import annotations

import io
import tarfile

import pytest

from boneio.core.config.secret_masking import MASK
from boneio.core.diagnostics.collect import EXCLUDED_FILES, build


@pytest.fixture
def device(tmp_path):
    """A configured device, with credentials in the places they really live."""
    (tmp_path / "config.yaml").write_text(
        "boneio:\n  name: Kotlownia\n"
        "mqtt:\n  host: localhost\n  username: boneio\n  password: sekret-brokera\n"
        "web:\n  port: 8090\n",
        encoding="utf-8",
    )
    (tmp_path / "secrets.yaml").write_text("mqtt_pass: sekret-brokera\n", encoding="utf-8")
    (tmp_path / "users.json").write_text('{"users": [{"password_hash": "scrypt$x"}]}', encoding="utf-8")
    (tmp_path / "remote_devices.yaml").write_text(
        "- id: wled1\n  password: haslo-wled\n", encoding="utf-8"
    )
    return tmp_path


def members(payload: bytes) -> dict[str, str]:
    """Read the archive back as {path inside the bundle: text}."""
    out = {}
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for info in archive.getmembers():
            handle = archive.extractfile(info)
            body = handle.read().decode("utf-8") if handle else ""
            out[info.name.split("/", 1)[1]] = body
    return out


def config_of(device):
    from boneio.core.config.yaml_util import load_yaml_file

    return load_yaml_file(str(device / "config.yaml"))


# --------------------------------------------------------- what must not leak


def test_no_configured_secret_survives_anywhere(device):
    """Every file is scrubbed, not just the ones someone remembered."""
    payload, _ = build(config_of(device), device / "config.yaml")
    for path, body in members(payload).items():
        assert "sekret-brokera" not in body, f"broker password leaked into {path}"


def test_the_credential_files_are_never_read(device):
    payload, _ = build(config_of(device), device / "config.yaml")
    files = members(payload)

    for name in EXCLUDED_FILES:
        assert f"config/{name}" not in files
    assert "scrypt$x" not in "".join(files.values())
    # The omission is recorded, so nobody wonders whether it was forgotten.
    assert "config/secrets.yaml.omitted" in files


def test_secrets_from_included_files_are_scrubbed_too(device):
    """remote_devices.yaml holds device passwords; it is still collected."""
    payload, _ = build(config_of(device), device / "config.yaml")
    files = members(payload)
    assert "config/remote_devices.yaml" in files
    assert "haslo-wled" not in files["config/remote_devices.yaml"]


def test_the_readme_says_what_was_removed(device):
    payload, _ = build(config_of(device), device / "config.yaml")
    readme = members(payload)["README.txt"]
    assert "secret value(s)" in readme
    assert "secrets.yaml" in readme
    # And warns about what it still contains.
    assert "public forum" in readme


# ------------------------------------------------------------ what is in it


def test_the_bundle_holds_the_sections_support_asks_for(device):
    payload, name = build(config_of(device), device / "config.yaml")
    files = members(payload)

    assert name.endswith(".tar.gz")
    assert "Kotlownia" in name  # findable in an inbox
    for expected in (
        "README.txt",
        "summary.txt",
        "config/config.yaml",
        "logs/boneio.log",
        "status/mqtt.txt",
        "status/mosquitto.txt",
        "status/docker.txt",
        "status/system.txt",
        "status/network.txt",
    ):
        assert expected in files, f"{expected} missing"


def test_the_summary_says_how_much_is_configured(device):
    payload, _ = build(config_of(device), device / "config.yaml")
    summary = members(payload)["summary.txt"]
    assert "Kotlownia" in summary
    assert "localhost" in summary
    # The username is not a secret and support needs it to match broker logs.
    assert "boneio" in summary


def test_the_summary_names_the_unit(device):
    """A bundle detached from whoever sent it still says which device it is."""
    payload, _ = build(config_of(device), device / "config.yaml", serial="blk265f49")
    summary = members(payload)["summary.txt"]
    assert "blk265f49" in summary


def test_an_overridden_serial_reports_the_real_one_too(device):
    """Support needs to know the unit answers to a serial it was not born with."""
    payload, _ = build(
        config_of(device),
        device / "config.yaml",
        serial="blk000000",
        real_serial="blk265f49",
    )
    summary = members(payload)["summary.txt"]
    assert "blk000000" in summary
    assert "blk265f49" in summary


def test_an_unknown_serial_is_said_rather_than_left_blank(device):
    payload, _ = build(config_of(device), device / "config.yaml")
    assert "(unknown)" in members(payload)["summary.txt"]


def test_a_local_broker_is_reported_on(device):
    payload, _ = build(config_of(device), device / "config.yaml")
    assert "systemctl status mosquitto" in members(payload)["status/mosquitto.txt"]


def test_a_remote_broker_is_not_looked_for_locally(tmp_path):
    """systemctl here would say nothing about someone else's broker."""
    (tmp_path / "config.yaml").write_text(
        "mqtt:\n  host: 192.168.1.50\n  password: x\n", encoding="utf-8"
    )
    from boneio.core.config.yaml_util import load_yaml_file

    payload, _ = build(load_yaml_file(str(tmp_path / "config.yaml")), tmp_path / "config.yaml")
    body = members(payload)["status/mosquitto.txt"]
    assert "192.168.1.50" in body
    assert "not on this device" in body


# ------------------------------------------------------- when things are bad


def test_a_missing_command_does_not_break_the_bundle(device, monkeypatch):
    """A bundle that fails because one tool is absent is a bundle nobody gets."""
    monkeypatch.setattr("boneio.core.diagnostics.collect.shutil.which", lambda _: None)
    # Docker is reached through boneio-containers first, so a device that has
    # the helper installed (the dev controller does) would still report it.
    monkeypatch.setattr(
        "boneio.core.diagnostics.collect.containers.helper_available",
        lambda recheck=False: False,
    )
    payload, _ = build(config_of(device), device / "config.yaml")
    assert "is not installed" in members(payload)["status/docker.txt"]


def test_an_empty_config_still_produces_a_bundle(tmp_path):
    """A config that will not parse is often the fault being reported."""
    (tmp_path / "config.yaml").write_text("", encoding="utf-8")
    payload, _ = build({}, tmp_path / "config.yaml")
    assert "summary.txt" in members(payload)


def test_an_unreadable_config_file_becomes_a_note_not_a_crash(device, monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr("pathlib.Path.read_text", boom)
    payload, _ = build(config_of(device), device / "config.yaml")
    assert "could not read" in members(payload)["config/config.yaml"]


def test_the_capture_window_is_stated_either_way(device):
    with_capture, _ = build(config_of(device), device / "config.yaml", capture_started=1_700_000_000)
    assert "DEBUG CAPTURE" in members(with_capture)["summary.txt"]

    without, _ = build(config_of(device), device / "config.yaml")
    summary = members(without)["summary.txt"]
    assert "no debug capture" in summary
    # And says what to do about it, since that is the common case.
    assert "reproduce" in summary


def test_archive_entries_are_not_world_readable(device):
    payload, _ = build(config_of(device), device / "config.yaml")
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        assert all(info.mode == 0o600 for info in archive.getmembers())


def test_a_yaml_file_nothing_includes_is_still_scrubbed(tmp_path):
    """The leak this module had before the test above caught it.

    collect_secrets only sees what config.yaml pulls in. A file left in the
    directory — from an edit, or included conditionally — would have gone out
    with its passwords intact.
    """
    (tmp_path / "config.yaml").write_text("mqtt:\n  password: main-secret\n", encoding="utf-8")
    (tmp_path / "orphan.yaml").write_text(
        "- id: wled1\n  password: orphan-secret\n", encoding="utf-8"
    )
    from boneio.core.config.yaml_util import load_yaml_file

    payload, _ = build(load_yaml_file(str(tmp_path / "config.yaml")), tmp_path / "config.yaml")
    body = members(payload)["config/orphan.yaml"]
    assert "orphan-secret" not in body
    assert MASK in body


def test_a_file_that_will_not_parse_is_shipped_but_not_trusted(tmp_path, caplog):
    """It still goes in — broken YAML is often the fault — with a warning."""
    (tmp_path / "config.yaml").write_text("mqtt:\n  password: main-secret\n", encoding="utf-8")
    (tmp_path / "broken.yaml").write_text("this: [is: not: valid\n", encoding="utf-8")
    from boneio.core.config.yaml_util import load_yaml_file

    payload, _ = build(load_yaml_file(str(tmp_path / "config.yaml")), tmp_path / "config.yaml")
    assert "config/broken.yaml" in members(payload)
