"""Tests for the prune_orphaned_journal_dirs migration handler.

Guards a destructive, root-run operation: it must delete only journal
directories belonging to a *previous* machine-id, and nothing else.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import logging
import logging.handlers
from pathlib import Path
from unittest.mock import patch

import pytest

_HELPER = Path(__file__).resolve().parents[3] / "boneio" / "migrations" / "bootstrap" / "boneio-migrate"

CURRENT = "4cab5fff9a994b2f9e725effec680753"
ORPHAN = "282629c0b66740a6b29e8aa88464cd66"


def _load_helper():
    """Load boneio-migrate with its root-only log handler stubbed out."""
    spec = importlib.util.spec_from_loader(
        "boneio_migrate_helper_journal",
        importlib.machinery.SourceFileLoader("boneio_migrate_helper_journal", str(_HELPER)),
    )
    module = importlib.util.module_from_spec(spec)
    with patch.object(logging.handlers, "RotatingFileHandler", lambda *a, **kw: logging.NullHandler()):
        spec.loader.exec_module(module)
    return module


helper = _load_helper()


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fake /etc/machine-id plus both journal roots."""
    machine_id_file = tmp_path / "machine-id"
    machine_id_file.write_text(CURRENT + "\n")

    ram = tmp_path / "var" / "log" / "journal"
    disk = tmp_path / "var" / "hdd.log" / "journal"
    for root in (ram, disk):
        for mid in (CURRENT, ORPHAN):
            d = root / mid
            d.mkdir(parents=True)
            (d / "system.journal").write_bytes(b"x" * 1024)

    real_path = helper.Path

    def fake_path(arg, *rest):
        m = {
            "/etc/machine-id": machine_id_file,
            "/var/log/journal": ram,
            "/var/hdd.log/journal": disk,
        }
        return m.get(str(arg), real_path(arg, *rest))

    monkeypatch.setattr(helper, "Path", fake_path)
    return ram, disk


def test_removes_orphan_keeps_current(tree) -> None:
    ram, disk = tree
    helper.handle_prune_orphaned_journal_dirs({}, assets_base="")

    for root in (ram, disk):
        assert (root / CURRENT).is_dir(), "current machine-id must survive"
        assert not (root / ORPHAN).exists(), "orphan must be removed"


def test_is_idempotent(tree) -> None:
    ram, disk = tree
    helper.handle_prune_orphaned_journal_dirs({}, assets_base="")
    helper.handle_prune_orphaned_journal_dirs({}, assets_base="")
    assert (ram / CURRENT).is_dir()


def test_ignores_names_that_are_not_machine_ids(tree) -> None:
    """Anything not matching 32 hex chars is left alone."""
    ram, _ = tree
    for name in ("remote-host.journal", "notamachineid", "4cab5fff"):
        (ram / name).mkdir()

    helper.handle_prune_orphaned_journal_dirs({}, assets_base="")

    for name in ("remote-host.journal", "notamachineid", "4cab5fff"):
        assert (ram / name).exists(), f"{name} must not be touched"


def test_refuses_to_run_on_empty_machine_id(tmp_path, monkeypatch) -> None:
    """A truncated machine-id must not cause everything to be deleted."""
    mid = tmp_path / "machine-id"
    mid.write_text("")
    ram = tmp_path / "journal"
    (ram / CURRENT).mkdir(parents=True)
    (ram / ORPHAN).mkdir(parents=True)

    real_path = helper.Path

    def fake_path(arg, *rest):
        m = {"/etc/machine-id": mid, "/var/log/journal": ram}
        return m.get(str(arg), real_path(arg, *rest))

    monkeypatch.setattr(helper, "Path", fake_path)
    helper.handle_prune_orphaned_journal_dirs({}, assets_base="")

    assert (ram / CURRENT).is_dir()
    assert (ram / ORPHAN).is_dir(), "must not prune when machine-id is unusable"


def test_missing_machine_id_file_is_a_noop(tmp_path, monkeypatch) -> None:
    real_path = helper.Path

    def fake_path(arg, *rest):
        if str(arg) == "/etc/machine-id":
            return tmp_path / "absent"
        return real_path(arg, *rest)

    monkeypatch.setattr(helper, "Path", fake_path)
    helper.handle_prune_orphaned_journal_dirs({}, assets_base="")
