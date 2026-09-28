"""The display says so while system migrations run at startup.

They run inside Manager.__init__, after the display has taken over and before
the web server starts. Without this the screen froze on host and version with
no uptime, and the controller looked hung for the minutes an apt install takes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from boneio.core.manager.display import DisplayManager
from boneio.migrations.runner import MigrationRunner


def _display(oled=None) -> DisplayManager:
    display = DisplayManager.__new__(DisplayManager)
    display._oled = oled
    display._early_oled_device = object()
    return display


def test_progress_goes_to_the_running_display():
    oled = MagicMock()
    _display(oled).show_migration_progress(40, "Applying migration 1.6.22: Security updates")
    title, lines = oled.show_notice.call_args.args
    assert title == "Updating"
    assert lines() == ["Do not power off.", "40% 1.6.22: Security updates"]
    assert oled.show_notice.call_args.kwargs["still_needed"]() is True


def test_without_an_oled_section_the_boot_screen_shows_it():
    """No oled: in the config, so early_oled still owns the screen."""
    display = _display()
    with patch("boneio.hardware.display.early_oled.draw_status") as draw:
        display.show_migration_progress(0, "Applying migration 1.6.26: x")
    assert draw.call_args.args[0] == "Updating system 0%"
    assert draw.call_args.kwargs["device"] is display._early_oled_device


def test_a_display_error_does_not_reach_the_migration():
    oled = MagicMock()
    oled.show_notice.side_effect = OSError("i2c gone")
    _display(oled).show_migration_progress(10, "Applying migration 1.6.22: x")


def test_the_notice_goes_once_the_migrations_are_over():
    oled = MagicMock()
    oled.notice = ("Updating", ["Do not power off."])
    _display(oled).clear_migration_progress()
    oled.clear_notice.assert_called_once()


def test_another_notice_is_left_alone():
    """The setup notice is not the migrations' to take down."""
    oled = MagicMock()
    oled.notice = ("Setup required", [])
    _display(oled).clear_migration_progress()
    oled.clear_notice.assert_not_called()


def test_startup_check_reports_progress(monkeypatch):
    runner = MigrationRunner()
    pending = [MagicMock(version="1.6.25"), MagicMock(version="1.6.26")]
    monkeypatch.setattr(runner, "_load_manifest", lambda: None)
    monkeypatch.setattr(runner, "_discover_migrations", lambda: None)
    monkeypatch.setattr(runner, "_load_applied_flags", lambda: None)
    monkeypatch.setattr(runner, "_get_pending", lambda: pending)
    monkeypatch.setattr(runner, "_any_helper_available", lambda: True)
    monkeypatch.setattr(runner, "_ensure_helper_up_to_date", lambda: None)
    monkeypatch.setattr(runner, "_check_overlay_in_current_kernel", lambda: None)
    applied = []
    monkeypatch.setattr(
        runner, "_apply_pending", lambda p, cb=None: applied.append(cb) or True
    )
    callback = MagicMock()
    runner.startup_check(progress_callback=callback)
    assert applied == [callback]
