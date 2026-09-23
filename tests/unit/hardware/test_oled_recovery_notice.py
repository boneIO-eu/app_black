"""The recovery notice on the OLED: whole URL on its own line, display awake."""

from __future__ import annotations

import pytest

luma = pytest.importorskip("luma.core.device")

from boneio.hardware.display import early_oled  # noqa: E402


class _Device(luma.dummy):
    def __init__(self):
        super().__init__(width=128, height=64, mode="1")
        self.shown = 0

    def show(self):
        self.shown += 1


def test_notice_is_drawn_after_handoff_and_turns_the_display_on(monkeypatch):
    monkeypatch.setattr(early_oled, "_taken_over", True)
    drawn: list[str] = []

    import luma.core.render as render

    class _Recorder(render.canvas):
        def __enter__(self):
            draw = super().__enter__()
            original = draw.text

            def text(xy, value, *args, **kwargs):
                drawn.append(value)
                return original(xy, value, *args, **kwargs)

            draw.text = text
            return draw

    monkeypatch.setattr(render, "canvas", _Recorder)
    dev = _Device()
    early_oled.draw_recovery(
        title="Recovery mode",
        message="Crash occurred. Check web panel for more info:",
        url="https://192.168.50.220:8443",
        device=dev,
    )
    assert dev.shown == 1
    assert "Recovery mode" in drawn
    assert "https://192.168.50.220:8443" in drawn
    assert dev.image.getbbox() is not None
