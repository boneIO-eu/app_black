"""The startup overlay check repairs through boneio-system.

It used to pipe an ad-hoc plan to the legacy boneio-migrate, which 1.6.6
removed, so on every 1.6.x controller it only logged that it could not help.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from boneio.core import system_ops
from boneio.core.utils import overlay as overlay_util
from boneio.migrations.runner import MigrationRunner

KERNEL = "6.18.2-bone12"


@pytest.fixture
def dtbs(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "dtbs"
    (root / KERNEL / "overlays").mkdir(parents=True)
    monkeypatch.setattr(overlay_util, "DTBS_ROOT", root)
    return root


@pytest.fixture
def helper(monkeypatch):
    """boneio-system as the runner sees it; records every call."""
    calls: list[str] = []
    state = {"verbs": ["overlay-get", "overlay-repair"], "result": None}

    monkeypatch.setattr(system_ops, "helper_supports", lambda verb: verb in state["verbs"])

    def _repair(timeout: int = 60) -> system_ops.Result:
        calls.append("overlay-repair")
        return state["result"]

    monkeypatch.setattr(system_ops, "overlay_repair", _repair)
    state["calls"] = calls
    return state


def _report(status: str, message: str | None) -> system_ops.Result:
    return system_ops.Result(
        0 if status != "problem" else 1,
        json.dumps({"status": status, "kernel": KERNEL, "running": KERNEL, "message": message}),
        "",
    )


def _repair(dtbs: Path) -> None:
    missing = overlay_util.missing_overlay_dirs(KERNEL)
    MigrationRunner.__new__(MigrationRunner)._repair_overlay_dirs(KERNEL, missing)


def test_an_old_helper_is_not_called(dtbs, helper, caplog):
    """Before 1.6.27 is applied the helper has no such verb: say so, no more."""
    helper["verbs"] = ["overlay-get"]
    with caplog.at_level(logging.WARNING):
        _repair(dtbs)
    assert helper["calls"] == []
    assert "1.6.27" in caplog.text
    assert "boneio-migrate" not in caplog.text


def test_a_repair_is_reported(dtbs, helper, caplog, monkeypatch):
    def _copied(timeout: int = 60) -> system_ops.Result:
        helper["calls"].append("overlay-repair")
        for directory in (dtbs / KERNEL, dtbs / KERNEL / "overlays"):
            (directory / "BONEIO-BLACK-PINS.dtbo").write_text("dtbo")
        return _report("repaired", "BONEIO-BLACK-PINS.dtbo was missing")

    monkeypatch.setattr(system_ops, "overlay_repair", _copied)
    with caplog.at_level(logging.WARNING):
        _repair(dtbs)
    assert helper["calls"] == ["overlay-repair"]
    assert "Overlay repaired for kernel" in caplog.text
    assert "still hold no boneIO overlay" not in caplog.text


def test_a_problem_is_an_error(dtbs, helper, caplog):
    helper["result"] = _report("problem", "no other kernel has it")
    with caplog.at_level(logging.WARNING):
        _repair(dtbs)
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert ["no other kernel has it" in r.getMessage() for r in errors] == [True]


def test_nothing_copied_is_not_claimed_as_copied(dtbs, helper, caplog):
    """uEnv.txt names no boneIO overlay: the helper has nothing to do."""
    helper["result"] = _report("ok", None)
    with caplog.at_level(logging.WARNING):
        _repair(dtbs)
    assert "repaired" not in caplog.text.replace("asking boneio-system to repair", "")
    assert "still hold no boneIO overlay" in caplog.text


def test_a_refused_call_is_an_error(dtbs, helper, caplog):
    helper["result"] = system_ops.Result(1, "", "REFUSED: something")
    with caplog.at_level(logging.WARNING):
        _repair(dtbs)
    assert "Overlay repair failed (rc=1): REFUSED: something" in caplog.text
