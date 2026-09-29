"""The helper's verb list is read once per installed helper, not per request."""

from __future__ import annotations

import json
import subprocess

import pytest

from boneio.core import system_ops


@pytest.fixture
def helper(tmp_path, monkeypatch):
    path = tmp_path / "boneio-system"
    path.write_text("v1")
    monkeypatch.setattr(system_ops, "HELPER_PATH", str(path))
    monkeypatch.setattr(system_ops, "_verbs_cache", None)
    calls = []
    verbs = {"list": ["os-update-state"], "rc": 0}

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, verbs["rc"], json.dumps(verbs["list"]), "")

    monkeypatch.setattr(system_ops.subprocess, "run", fake_run)
    return path, calls, verbs


def test_second_ask_does_not_start_the_helper(helper):
    _, calls, _ = helper
    assert system_ops.helper_supports("os-update-state")
    assert not system_ops.helper_supports("os-update-start")
    assert len(calls) == 1


def test_a_replaced_helper_is_asked_again(helper):
    path, calls, verbs = helper
    assert not system_ops.helper_supports("os-update-start")
    verbs["list"] = ["os-update-state", "os-update-start"]
    path.write_text("v2 is longer")
    assert system_ops.helper_supports("os-update-start")
    assert len(calls) == 2


def test_a_failed_start_is_not_remembered(helper):
    _, calls, verbs = helper
    verbs["rc"], verbs["list"] = 1, []
    assert not system_ops.helper_supports("os-update-state")
    verbs["rc"], verbs["list"] = 0, ["os-update-state"]
    assert system_ops.helper_supports("os-update-state")
    assert len(calls) == 2


def test_no_helper_installed(helper):
    path, calls, _ = helper
    path.unlink()
    assert not system_ops.helper_supports("os-update-state")
    assert calls == []
