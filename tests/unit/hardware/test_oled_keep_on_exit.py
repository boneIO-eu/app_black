"""A notice drawn before a deliberate exit stays on the display."""

from __future__ import annotations

import pytest

luma = pytest.importorskip("luma.core.device")

from boneio.hardware.display import early_oled  # noqa: E402


def test_keep_on_exit_stops_luma_from_blanking_the_panel(monkeypatch):
    dev = luma.dummy(width=128, height=64, mode="1")
    monkeypatch.setattr(early_oled, "_early_device", dev)
    hidden: list[bool] = []
    monkeypatch.setattr(dev, "hide", lambda: hidden.append(True))

    early_oled.keep_on_exit()
    dev.cleanup()  # what luma's atexit hook runs

    assert dev.persist is True
    assert hidden == []


def test_keep_on_exit_without_a_display_is_a_no_op(monkeypatch):
    monkeypatch.setattr(early_oled, "_early_device", None)
    early_oled.keep_on_exit()


def test_a_crash_message_stays_on_the_display(monkeypatch):
    """bonecli and runner return 1 right after draw_crash; the panel must not blank."""
    dev = luma.dummy(width=128, height=64, mode="1")
    monkeypatch.setattr(early_oled, "_early_device", dev)
    monkeypatch.setattr(early_oled, "_taken_over", True)  # DisplayManager owns it
    hidden: list[bool] = []
    monkeypatch.setattr(dev, "hide", lambda: hidden.append(True))

    early_oled.draw_crash(RuntimeError("boom"))
    dev.cleanup()  # what luma's atexit hook runs

    assert dev.persist is True
    assert hidden == []
    assert early_oled.is_taken_over() is True


def test_draw_crash_without_a_display_is_a_no_op(monkeypatch):
    monkeypatch.setattr(early_oled, "_early_device", None)
    early_oled.draw_crash(RuntimeError("boom"))
