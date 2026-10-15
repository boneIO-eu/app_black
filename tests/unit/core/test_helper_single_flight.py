"""Threads asking the helpers the same thing at once share one helper run.

Each run costs seconds of CPU on a BeagleBone; at startup the panel, the
warm-up and the migration check used to ask four times over.
"""

from __future__ import annotations

import subprocess
import threading
import time

import pytest

from boneio.core import system_ops
from boneio.migrations import runner as runner_module


@pytest.fixture
def helper(tmp_path, monkeypatch):
    path = tmp_path / "boneio-system"
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    monkeypatch.setattr(system_ops, "HELPER_PATH", str(path))
    monkeypatch.setattr(system_ops, "_available", None)
    calls = []

    def slow_run(argv, **kwargs):
        calls.append(argv[3:])
        time.sleep(0.2)
        return subprocess.CompletedProcess(argv, 0, '{"state": "set"}', "")

    monkeypatch.setattr(system_ops.subprocess, "run", slow_run)
    return calls


def _at_once(fn, n=4):
    results = []
    threads = [threading.Thread(target=lambda: results.append(fn())) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_concurrent_state_reads_share_one_run(helper):
    results = _at_once(system_ops.service_password_state)
    assert results == ["set"] * 4
    assert helper.count(["--list-verbs"]) == 1
    assert helper.count(["service-password-state"]) == 1


def test_a_read_after_the_last_one_finished_runs_again(helper):
    system_ops.os_update_state()
    system_ops.os_update_state()
    assert helper.count(["os-update-state"]) == 2


def test_verbs_with_stdin_are_never_shared(helper):
    _at_once(lambda: system_ops.service_password_change("old", "new"), n=2)
    assert helper.count(["service-password-change"]) == 2


def test_concurrent_status_and_startup_share_one_selftest(tmp_path, monkeypatch):
    path = tmp_path / "boneio-migrate-v2"
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    monkeypatch.setattr(runner_module, "HELPER_V2_PATH", str(path))
    calls = []

    def slow_run(argv, **kwargs):
        calls.append(argv)
        time.sleep(0.2)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(runner_module.subprocess, "run", slow_run)
    runner = runner_module.MigrationRunner()
    assert _at_once(runner.helper_v2_available, n=3) == [True] * 3
    assert len(calls) == 1
    assert runner.helper_v2_available(recheck=True)
    assert len(calls) == 2
