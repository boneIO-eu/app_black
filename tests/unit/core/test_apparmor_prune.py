"""Tests for the disable_apparmor_profiles migration handler.

The handler runs as root inside boneio-migrate, so its behaviour is pinned
here: keep-list semantics, no file deletion, idempotency, and that include
directories are never touched.
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


def _load_helper():
    """Load the boneio-migrate helper (no .py suffix) as a module.

    The helper configures a RotatingFileHandler on /var/log/boneio-migrate.log
    at import time, which is root-only. Swap it for a no-op handler while the
    module body executes.
    """
    spec = importlib.util.spec_from_loader(
        "boneio_migrate_helper",
        importlib.machinery.SourceFileLoader("boneio_migrate_helper", str(_HELPER)),
    )
    module = importlib.util.module_from_spec(spec)
    with patch.object(logging.handlers, "RotatingFileHandler", lambda *a, **kw: logging.NullHandler()):
        spec.loader.exec_module(module)
    return module


helper = _load_helper()


@pytest.fixture
def apparmor_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a fake /etc/apparmor.d and point the handler at it."""
    root = tmp_path / "apparmor.d"
    root.mkdir()
    for name in ("brave", "chrome", "Discord", "steam", "unix-chkpwd", "runc"):
        (root / name).write_text(f"# profile {name}\n")
    # Include trees that must never be disabled
    for d in ("abstractions", "tunables", "local"):
        (root / d).mkdir()
        (root / d / "something").write_text("# include\n")

    real_path = helper.Path

    def fake_path(arg, *rest):
        # The handler hardcodes /etc/apparmor.d; redirect just that path.
        if str(arg) == "/etc/apparmor.d":
            return root
        return real_path(arg, *rest)

    monkeypatch.setattr(helper, "Path", fake_path)
    return root


def test_keeps_listed_profiles_and_disables_the_rest(apparmor_tree: Path) -> None:
    helper.handle_disable_apparmor_profiles(
        {"keep": ["unix-chkpwd", "runc"]}, assets_base=""
    )

    disable = apparmor_tree / "disable"
    disabled = sorted(p.name for p in disable.iterdir())
    assert disabled == ["Discord", "brave", "chrome", "steam"]
    assert not (disable / "unix-chkpwd").exists()
    assert not (disable / "runc").exists()


def test_original_profiles_are_not_deleted(apparmor_tree: Path) -> None:
    """Files belong to the apparmor package; deleting them would fight dpkg."""
    helper.handle_disable_apparmor_profiles({"keep": []}, assets_base="")

    for name in ("brave", "chrome", "Discord", "steam", "unix-chkpwd", "runc"):
        assert (apparmor_tree / name).is_file(), f"{name} must still exist"


def test_include_directories_are_untouched(apparmor_tree: Path) -> None:
    helper.handle_disable_apparmor_profiles({"keep": []}, assets_base="")

    disable = apparmor_tree / "disable"
    for d in ("abstractions", "tunables", "local"):
        assert not (disable / d).exists(), f"{d} is an include tree, not a profile"
        assert (apparmor_tree / d).is_dir()


def test_is_idempotent(apparmor_tree: Path) -> None:
    helper.handle_disable_apparmor_profiles({"keep": ["runc"]}, assets_base="")
    first = sorted(p.name for p in (apparmor_tree / "disable").iterdir())

    helper.handle_disable_apparmor_profiles({"keep": ["runc"]}, assets_base="")
    second = sorted(p.name for p in (apparmor_tree / "disable").iterdir())

    assert first == second


def test_symlinks_point_at_the_real_profile(apparmor_tree: Path) -> None:
    helper.handle_disable_apparmor_profiles({"keep": []}, assets_base="")

    link = apparmor_tree / "disable" / "brave"
    assert link.is_symlink()
    assert link.resolve() == (apparmor_tree / "brave").resolve()


def test_missing_apparmor_dir_is_a_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Systems without AppArmor must not raise."""
    absent = tmp_path / "nope"
    real_path = helper.Path

    def fake_path(arg, *rest):
        if str(arg) == "/etc/apparmor.d":
            return absent
        return real_path(arg, *rest)

    monkeypatch.setattr(helper, "Path", fake_path)
    helper.handle_disable_apparmor_profiles({"keep": []}, assets_base="")
    assert not absent.exists()
