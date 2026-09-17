"""Tests for how the runner chooses between the two migration helpers.

This is where it is decided whether CVE-2026-77055 is open on a given boot, so
the interesting cases are the transitions: no v2 yet, v2 present but broken, v2
working, and the moment in between when the pivot has just installed it.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from boneio.migrations.runner import (
    HARDENING_FIRST,
    HELPER_V2_PATH,
    MigrationInfo,
    MigrationRunner,
    PIVOT_VERSIONS,
)


@pytest.fixture
def runner() -> MigrationRunner:
    return MigrationRunner()


def _info(version: str) -> MigrationInfo:
    return MigrationInfo(
        version=version,
        module_name=f"boneio.migrations.versions.v{version.replace('.', '_')}",
        description=f"migration {version}",
    )


def _completed(returncode: int, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout="", stderr=stderr
    )


# ------------------------------------------------------------------- selftest


def test_v2_is_unavailable_when_it_is_not_installed(runner, monkeypatch):
    monkeypatch.setattr("os.path.isfile", lambda path: False)
    assert runner.helper_v2_available() is False


def test_v2_is_unavailable_when_its_selftest_fails(runner, monkeypatch):
    """Presence is not enough.

    A helper that parses but cannot verify signatures would refuse every
    migration, silently, on a device in a cabinet — so the decision to retire
    the old helper rests on the selftest, not on the file existing.
    """
    monkeypatch.setattr("os.path.isfile", lambda path: True)
    monkeypatch.setattr("os.access", lambda path, mode: True)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _completed(1, "anchor missing")
    )
    assert runner.helper_v2_available() is False


def test_v2_is_available_when_its_selftest_passes(runner, monkeypatch):
    monkeypatch.setattr("os.path.isfile", lambda path: True)
    monkeypatch.setattr("os.access", lambda path, mode: True)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed(0))
    assert runner.helper_v2_available() is True


def test_the_selftest_runs_once_per_startup(runner, monkeypatch):
    calls: list[list[str]] = []

    monkeypatch.setattr("os.path.isfile", lambda path: True)
    monkeypatch.setattr("os.access", lambda path, mode: True)

    def _run(argv, **kwargs):
        calls.append(argv)
        return _completed(0)

    monkeypatch.setattr(subprocess, "run", _run)
    runner.helper_v2_available()
    runner.helper_v2_available()
    assert len(calls) == 1
    assert calls[0] == ["sudo", "-n", HELPER_V2_PATH, "--selftest"]


def test_a_recheck_asks_again(runner, monkeypatch):
    """Needed right after the pivot, which installs v2 mid-run."""
    answers = iter([1, 0])
    monkeypatch.setattr("os.path.isfile", lambda path: True)
    monkeypatch.setattr("os.access", lambda path, mode: True)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed(next(answers)))

    assert runner.helper_v2_available() is False
    assert runner.helper_v2_available(recheck=True) is True


def test_a_selftest_that_cannot_run_is_not_treated_as_success(runner, monkeypatch):
    monkeypatch.setattr("os.path.isfile", lambda path: True)
    monkeypatch.setattr("os.access", lambda path, mode: True)

    def _explode(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="selftest", timeout=90)

    monkeypatch.setattr(subprocess, "run", _explode)
    assert runner.helper_v2_available() is False


# ---------------------------------------------------------------------- order


def test_the_hardening_migrations_go_first(runner, monkeypatch):
    """1.6.4 can fail and a failure stops everything behind it."""
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: False)
    pending = [_info(v) for v in ("1.5.4", "1.6.2", "1.6.4", "1.6.5", "1.6.6")]
    ordered = [m.version for m in runner._pivot_first(pending)]
    assert ordered[:2] == list(HARDENING_FIRST)
    assert ordered[2:] == ["1.5.4", "1.6.2", "1.6.4"]


def test_the_pivot_comes_before_the_retirement(runner, monkeypatch):
    """Retiring the old helper before installing the new one would be fatal."""
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: False)
    pending = [_info("1.6.6"), _info("1.6.5")]
    assert [m.version for m in runner._pivot_first(pending)] == ["1.6.5", "1.6.6"]


def test_the_order_is_untouched_when_nothing_needs_hoisting(runner, monkeypatch):
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: True)
    pending = [_info(v) for v in ("1.5.4", "1.6.2")]
    assert [m.version for m in runner._pivot_first(pending)] == ["1.5.4", "1.6.2"]


def test_a_device_still_on_15x_does_not_stall_before_the_pivot(runner, monkeypatch):
    """The failure this ordering exists to prevent.

    In plain version order the whole 1.5.x backlog would be applied through the
    legacy helper before the pivot was ever reached, leaving the escalation path
    open for the entire run.
    """
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: False)
    backlog = [_info(v) for v in ("1.5.4", "1.5.5", "1.5.6", "1.6.0", "1.6.5")]
    assert runner._pivot_first(backlog)[0].version == "1.6.5"


# ------------------------------------------------------------------- dispatch


def test_v2_gets_a_version_and_nothing_else(runner, monkeypatch):
    """The entire fix, expressed as what is not in the request."""
    sent: dict = {}

    def _run(argv, input=None, **kwargs):
        sent.update(json.loads(input))
        return _completed(0)

    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: True)
    monkeypatch.setattr(subprocess, "run", _run)
    monkeypatch.setattr(runner, "_write_applied_flag", lambda migration: None)

    assert runner._apply_one(_info("1.6.1")) is True
    assert set(sent) == {"protocol", "version", "package_root"}
    assert sent["protocol"] == 2
    assert sent["version"] == "1.6.1"
    assert "actions" not in sent
    assert "assets_base" not in sent
    assert "validate_cmd" not in json.dumps(sent)


def test_a_refusal_from_v2_is_a_failure(runner, monkeypatch):
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: True)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _completed(1, "REFUSED: not signed")
    )
    flagged: list = []
    monkeypatch.setattr(runner, "_write_applied_flag", flagged.append)

    assert runner._apply_one(_info("1.6.1")) is False
    assert flagged == [], "a refused migration must not be marked as applied"


def test_without_v2_the_legacy_helper_is_used_and_the_state_is_reported(
    runner, monkeypatch
):
    """Refusing here would be stricter and wrong.

    A device with no v2 yet is in exactly the state it is in today. Blocking
    every migration would leave it unable to update at all, which is worse than
    unhardened — so legacy stays the fallback and the UI is told the hardening
    is unfinished.
    """
    used: list[str] = []
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: False)
    monkeypatch.setattr(
        runner, "_apply_via_legacy", lambda migration: used.append(migration.version) or True
    )

    assert runner._apply_one(_info("1.5.4")) is True
    assert used == ["1.5.4"]
    assert runner.hardening_pending is True


def test_the_pivot_itself_goes_through_the_legacy_helper(runner, monkeypatch):
    """It installs v2, so it cannot go through v2."""
    used: list[str] = []
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: False)
    monkeypatch.setattr(
        runner, "_apply_via_legacy", lambda migration: used.append(migration.version) or True
    )

    pivot = sorted(PIVOT_VERSIONS)[0]
    assert runner._apply_one(_info(pivot)) is True
    assert used == [pivot]


def test_v2_is_preferred_once_it_works(runner, monkeypatch):
    legacy: list[str] = []
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: True)
    monkeypatch.setattr(runner, "_apply_via_legacy", legacy.append)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed(0))
    monkeypatch.setattr(runner, "_write_applied_flag", lambda migration: None)

    pivot = sorted(PIVOT_VERSIONS)[0]
    runner._apply_one(_info(pivot))
    assert legacy == [], "the pivot went through legacy even though v2 works"


# ----------------------------------------------------------- the pivot moment


def test_v2_is_rechecked_immediately_after_the_pivot(runner, monkeypatch):
    """Otherwise the retirement migration would go through the old helper.

    That would mean the legacy helper removing itself over the very channel
    being closed — and it would do so using a plan supplied over stdin.
    """
    rechecks: list[bool] = []
    applied: list[str] = []

    def _available(recheck=False):
        rechecks.append(recheck)
        return False

    monkeypatch.setattr(runner, "helper_v2_available", _available)
    monkeypatch.setattr(
        runner, "_apply_via_legacy", lambda m: applied.append(m.version) or True
    )
    monkeypatch.setattr(runner, "_write_applied_flag", lambda m: None)

    runner._apply_pending([_info("1.6.5")])
    assert applied == ["1.6.5"]
    assert True in rechecks, "the runner did not re-evaluate v2 after the pivot"


def test_a_failed_pivot_leaves_the_device_working(runner, monkeypatch):
    """The whole reason v2 is installed at its own path."""
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: False)
    monkeypatch.setattr(runner, "_apply_via_legacy", lambda m: False)

    assert runner._apply_pending([_info("1.6.5"), _info("1.5.4")]) is False
    assert runner.status == "error"
    # The old helper is untouched by the pivot, so the next boot retries.
    assert runner.hardening_pending is True


def test_the_status_says_which_protocol_is_in_play(runner, monkeypatch):
    """The UI has to tell "not hardened yet" from "broken"."""
    monkeypatch.setattr(runner, "_load_manifest", lambda: None)
    monkeypatch.setattr(runner, "_discover_migrations", lambda: None)
    monkeypatch.setattr(runner, "_load_applied_flags", lambda: None)
    monkeypatch.setattr(runner, "_get_pending", lambda: [])
    monkeypatch.setattr(runner, "_helper_installed", lambda: True)
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: False)
    runner.hardening_pending = True

    status = runner.get_status_dict()
    assert status["helper_v2"] is False
    assert status["hardening_pending"] is True


# ------------------------------------------------- the gate after retirement


def test_a_device_with_only_v2_is_not_asked_to_bootstrap(runner, monkeypatch):
    """The bug this guards against would have surfaced on the first upgrade.

    Migration 1.6.6 removes /usr/sbin/boneio-migrate. The startup gate used to
    check that path alone, so the next pending migration on a hardened device
    would report "bootstrap required" and ask for a system password — putting
    back the prompt the whole exercise removes.
    """
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: True)
    monkeypatch.setattr(runner, "_helper_installed", lambda: False)
    assert runner._any_helper_available() is True


def test_a_device_with_only_the_legacy_helper_still_migrates(runner, monkeypatch):
    """The state every field device is in before the pivot."""
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: False)
    monkeypatch.setattr(runner, "_helper_installed", lambda: True)
    assert runner._any_helper_available() is True


def test_a_device_with_no_helper_at_all_needs_bootstrap(runner, monkeypatch):
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: False)
    monkeypatch.setattr(runner, "_helper_installed", lambda: False)
    assert runner._any_helper_available() is False


def test_the_startup_gate_uses_both_helpers(runner, monkeypatch):
    """End to end: v2 present, legacy gone, migrations pending."""
    monkeypatch.setattr(runner, "_load_manifest", lambda: None)
    monkeypatch.setattr(runner, "_discover_migrations", lambda: None)
    monkeypatch.setattr(runner, "_load_applied_flags", lambda: None)
    monkeypatch.setattr(runner, "_get_pending", lambda: [_info("1.6.10")])
    monkeypatch.setattr(runner, "_check_overlay_in_current_kernel", lambda: None)
    monkeypatch.setattr(runner, "helper_v2_available", lambda recheck=False: True)
    monkeypatch.setattr(runner, "_helper_installed", lambda: False)
    monkeypatch.setattr(runner, "_ensure_helper_up_to_date", lambda: None)
    applied: list[str] = []
    monkeypatch.setattr(
        runner, "_apply_one", lambda m: applied.append(m.version) or True
    )

    runner.startup_check()
    assert runner.bootstrap_required is False, "a hardened device was asked for a password"
    assert applied == ["1.6.10"]
