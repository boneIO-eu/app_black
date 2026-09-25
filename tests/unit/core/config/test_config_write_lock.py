"""Config saves wait for each other.

A section save from the panel runs in an executor thread; yaml_patch edits —
the broker password, frame-ancestors, removing the pre-1.6 login block — took
no lock at all. Each reads the whole file and writes it back, so two at once
left only the later one's change on disk.
"""

from __future__ import annotations

import threading

from boneio.core.config import yaml_patch, yaml_util
from boneio.core.config.write_lock import CONFIG_WRITE_LOCK


def test_yaml_util_and_yaml_patch_share_one_lock():
    assert yaml_util._yaml_write_lock is CONFIG_WRITE_LOCK


def test_a_patch_waits_for_a_save_in_progress(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("mqtt:\n  host: localhost\n", encoding="utf-8")
    done = threading.Event()

    def patch():
        yaml_patch.set_scalar(config, ("mqtt", "password"), "nowe")
        done.set()

    with CONFIG_WRITE_LOCK:
        worker = threading.Thread(target=patch)
        worker.start()
        assert not done.wait(0.3), "wrote while another save held the lock"

    worker.join(timeout=5)
    assert done.is_set()
    assert 'password: "nowe"' in config.read_text(encoding="utf-8")


def test_a_patch_can_run_inside_a_held_lock(tmp_path):
    """Routes hold it across a check, a backup and an edit."""
    config = tmp_path / "config.yaml"
    config.write_text("web:\n  auth:\n    username: a\n", encoding="utf-8")

    with CONFIG_WRITE_LOCK:
        assert yaml_patch.remove_section(config, ("web", "auth")) is True


def test_two_saves_at_once_both_land(tmp_path):
    """The lost update itself: field from one, password from the other."""
    config = tmp_path / "config.yaml"
    config.write_text(
        "web:\n  cloud:\n    pwa_name: old\nmqtt:\n  host: localhost\n",
        encoding="utf-8",
    )
    barrier = threading.Barrier(2)

    def field():
        barrier.wait()
        yaml_util.update_yaml_field(str(config), "web.cloud", "pwa_name", "new")

    def password():
        barrier.wait()
        yaml_patch.set_scalar(config, ("mqtt", "password"), "nowe")

    threads = [threading.Thread(target=f) for f in (field, password)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    text = config.read_text(encoding="utf-8")
    assert "pwa_name: new" in text
    assert 'password: "nowe"' in text
