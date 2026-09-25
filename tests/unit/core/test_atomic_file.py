"""Config files are replaced whole or not at all.

The controller has no UPS. Every config save used to truncate the file and
write it again, so power lost mid-write left config.yaml or secrets.yaml cut
short and the controller unable to boot.
"""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

import pytest

from boneio.core import atomic_file
from boneio.core.atomic_file import write_atomically


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_the_new_content_replaces_the_old(tmp_path):
    target = tmp_path / "config.yaml"
    target.write_text("old: 1\n", encoding="utf-8")

    write_atomically(target, "new: 2\n")

    assert target.read_text(encoding="utf-8") == "new: 2\n"


def test_a_write_that_fails_leaves_the_old_file_whole(tmp_path, monkeypatch):
    """What a power cut mid-write looks like from the file's side."""
    target = tmp_path / "config.yaml"
    target.write_text("mqtt: !include mqtt.yaml\n", encoding="utf-8")

    def power_cut(fd):
        raise OSError("I/O error")

    monkeypatch.setattr(atomic_file.os, "fsync", power_cut)

    with pytest.raises(OSError):
        write_atomically(target, "half of the new")

    assert target.read_text(encoding="utf-8") == "mqtt: !include mqtt.yaml\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.yaml"]


def test_temp_files_left_by_a_killed_writer_are_cleaned_up(tmp_path):
    """Measured on the controller: 30 of 40 SIGKILLs mid-save left one.
    Nothing runs after a power cut either, so the next save sweeps them."""
    target = tmp_path / "config.yaml"
    target.write_text("a: 1\n", encoding="utf-8")
    stale = tmp_path / ".config.yaml.k1ll3d_x"
    stale.write_text("half", encoding="utf-8")
    old = time.time() - 3600
    os.utime(stale, (old, old))
    in_flight = tmp_path / ".config.yaml.wr1t1ng_"
    in_flight.write_text("another save, still running", encoding="utf-8")
    unrelated = tmp_path / ".config.yaml.backup"
    unrelated.write_text("someone's own copy", encoding="utf-8")
    os.utime(unrelated, (old, old))

    write_atomically(target, "a: 2\n")

    assert not stale.exists()
    assert in_flight.exists()
    assert unrelated.exists()


def test_a_file_holding_a_password_stays_private(tmp_path):
    target = tmp_path / "secrets.yaml"
    target.write_text("mqtt_password: x\n", encoding="utf-8")
    target.chmod(0o600)

    write_atomically(target, "mqtt_password: y\n")

    assert _mode(target) == 0o600


def test_a_readable_file_stays_readable(tmp_path):
    """mkstemp makes 0600; the service's own group reads config.yaml."""
    target = tmp_path / "config.yaml"
    target.write_text("a: 1\n", encoding="utf-8")
    target.chmod(0o644)

    write_atomically(target, "a: 2\n")

    assert _mode(target) == 0o644


def test_a_new_file_gets_what_open_would_have_given_it(tmp_path):
    """The controller runs with umask 002: its config files are 0664."""
    target = tmp_path / "can_node_id"
    reference = tmp_path / "reference"
    reference.write_text("", encoding="utf-8")

    write_atomically(target, "5")

    assert target.read_text(encoding="utf-8") == "5"
    assert _mode(target) == _mode(reference)


def test_a_symlink_keeps_pointing_at_the_written_file(tmp_path):
    """Replacing the link itself would leave the real file behind unchanged."""
    real = tmp_path / "shared" / "mqtt.yaml"
    real.parent.mkdir()
    real.write_text("host: old\n", encoding="utf-8")
    link = tmp_path / "mqtt.yaml"
    link.symlink_to(real)

    write_atomically(link, "host: new\n")

    assert link.is_symlink()
    assert real.read_text(encoding="utf-8") == "host: new\n"


def test_bytes_are_written_as_they_are(tmp_path):
    target = tmp_path / "state.json"

    write_atomically(target, b"\x00\x01")

    assert target.read_bytes() == b"\x00\x01"


def test_update_yaml_field_goes_through_it(tmp_path, monkeypatch):
    """The panel's PWA name save rewrote config.yaml in place."""
    from boneio.core.config import yaml_util

    target = tmp_path / "config.yaml"
    target.write_text("web:\n  cloud:\n    pwa_name: old\n", encoding="utf-8")
    written = []
    real = yaml_util.write_atomically
    monkeypatch.setattr(
        yaml_util, "write_atomically", lambda p, c: (written.append(p), real(p, c))
    )

    result = yaml_util.update_yaml_field(str(target), "web.cloud", "pwa_name", "new")

    assert result["status"] == "success"
    assert written == [str(target)]
    assert "pwa_name: new" in target.read_text(encoding="utf-8")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.yaml"]
