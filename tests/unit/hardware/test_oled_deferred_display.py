"""The OLED frame transfer must not run on the caller's thread.

Drawing a screen is cheap. Handing it to the panel is an I2C transfer of about
a kilobyte that first waits for the bus lock shared with the relay expanders
and every I2C sensor. The screens that redraw on output and input events are
rendered straight from the event bus worker, so that transfer used to sit on
the event loop — a kilobyte of I2C in front of the GPIO reader every time a
relay switched.
"""

from __future__ import annotations

import threading
import time

import pytest

from boneio.hardware.display.oled import _DeferredDisplay


class FakeDevice:
    """A luma-ish device that records frames and can be made slow."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.frames: list[object] = []
        self.threads: list[int] = []
        self.bounding_box = (0, 0, 127, 63)
        self.mode = "1"
        self.size = (128, 64)

    def display(self, image) -> None:
        self.threads.append(threading.get_ident())
        if self.delay:
            time.sleep(self.delay)
        self.frames.append(image)


@pytest.fixture
def device():
    """A wrapped fake device, stopped on teardown."""
    made: list[_DeferredDisplay] = []

    def _make(delay: float = 0.0) -> tuple[_DeferredDisplay, FakeDevice]:
        real = FakeDevice(delay=delay)
        wrapper = _DeferredDisplay(real)
        made.append(wrapper)
        return wrapper, real

    yield _make
    for wrapper in made:
        wrapper.stop(timeout=2.0)


class TestTransferIsOffTheCallersThread:
    def test_display_returns_before_the_transfer_finishes(self, device):
        """A slow panel must not hold up the caller."""
        wrapper, real = device(delay=0.3)

        start = time.monotonic()
        wrapper.display("frame")
        elapsed = time.monotonic() - start

        assert elapsed < 0.1, f"display() blocked the caller for {elapsed:.3f}s"
        assert wrapper.flush(timeout=2.0)
        assert real.frames == ["frame"]

    def test_transfer_runs_on_another_thread(self, device):
        """The I2C write must not happen on the calling thread."""
        wrapper, real = device()
        caller = threading.get_ident()

        wrapper.display("frame")
        assert wrapper.flush(timeout=2.0)

        assert real.threads and all(t != caller for t in real.threads)


class TestFramesAreCoalesced:
    def test_only_the_newest_frame_of_a_burst_is_sent(self, device):
        """A screen is a snapshot: stale frames are not worth sending."""
        wrapper, real = device(delay=0.2)

        # The first frame occupies the thread; the rest pile up behind it.
        wrapper.display("first")
        time.sleep(0.05)
        for frame in ("stale-1", "stale-2", "newest"):
            wrapper.display(frame)

        assert wrapper.flush(timeout=3.0)

        assert real.frames == ["first", "newest"], real.frames

    def test_a_burst_does_not_build_a_backlog(self, device):
        """Twenty redraws must not mean twenty transfers."""
        wrapper, real = device(delay=0.05)

        for i in range(20):
            wrapper.display(f"frame-{i}")

        assert wrapper.flush(timeout=3.0)

        assert len(real.frames) < 20
        assert real.frames[-1] == "frame-19"


class TestForwardingAndRobustness:
    def test_other_attributes_reach_the_real_device(self, device):
        """The drawing code still reads geometry off the device."""
        wrapper, real = device()

        assert wrapper.bounding_box == real.bounding_box
        assert wrapper.mode == "1"
        assert wrapper.size == (128, 64)

    def test_a_failing_transfer_does_not_kill_the_thread(self, device):
        """The panel is cosmetic; a bad frame must not end the worker."""
        wrapper, real = device()
        calls = {"n": 0}

        def flaky(image):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("i2c went away")
            real.frames.append(image)

        real.display = flaky

        wrapper.display("boom")
        assert wrapper.flush(timeout=2.0)
        wrapper.display("after")
        assert wrapper.flush(timeout=2.0)

        assert real.frames == ["after"]

    def test_stop_sends_what_is_queued(self, device):
        """Nothing in flight is dropped on shutdown."""
        wrapper, real = device(delay=0.1)

        wrapper.display("last")
        wrapper.stop(timeout=2.0)

        assert real.frames == ["last"]
