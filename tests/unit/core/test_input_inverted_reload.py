"""Regression tests for changing 'inverted' on a running binary sensor.

'inverted' is decided in GpioInputBinarySensor.__init__ and baked into the
detector, so a config reload used to leave the sensor on the old polarity until
the whole application was restarted.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

# Mock gpiod before importing boneio modules (tests run off-target).
mock_gpiod = MagicMock()
mock_gpiod.line = MagicMock()
sys.modules.setdefault("gpiod", mock_gpiod)
sys.modules.setdefault("gpiod.line", mock_gpiod.line)

from boneio.components.input.detectors import BinarySensorDetector  # noqa: E402
from boneio.const import PRESSED, RELEASED  # noqa: E402


@dataclass
class FakeEdgeEvent:
    """Minimal fake gpiod.EdgeEvent for testing."""

    class Type:
        FALLING_EDGE = "FALLING"
        RISING_EDGE = "RISING"

    event_type: str
    timestamp_ns: int


def _falling(ts_s: float) -> FakeEdgeEvent:
    return FakeEdgeEvent(FakeEdgeEvent.Type.FALLING_EDGE, int(ts_s * 1_000_000_000))


def _rising(ts_s: float) -> FakeEdgeEvent:
    return FakeEdgeEvent(FakeEdgeEvent.Type.RISING_EDGE, int(ts_s * 1_000_000_000))


# ── BinarySensorDetector.resync ──────────────────────────────────────────────


class TestDetectorResync:
    """The detector must honour a polarity change made while it is running."""

    @pytest.fixture
    def detector(self):
        loop = MagicMock()
        return BinarySensorDetector(
            loop=loop,
            callback=MagicMock(),
            debounce_ms=30.0,
            inverted=False,
            name="Door",
            pin="P8_34",
        )

    def test_first_edge_after_resync_uses_the_new_polarity(self, detector):
        """Pin LOW reads PRESSED normally; once inverted, HIGH is the pressed one."""
        detector.handle_event(_falling(1.0))
        assert detector._callback.call_args[0][0] == PRESSED
        detector._callback.reset_mock()

        # Pin is still LOW, which under the new polarity means RELEASED.
        detector.resync(inverted=True, current_state=False)
        detector.handle_event(_rising(2.0))

        detector._callback.assert_called_once()
        assert detector._callback.call_args[0][0] == PRESSED

    def test_stale_anchor_would_swallow_the_edge(self, detector):
        """Why resync re-anchors: the cached state still describes the old polarity."""
        detector.handle_event(_falling(1.0))
        detector._callback.reset_mock()

        detector._inverted = True  # polarity flipped without re-anchoring
        detector.handle_event(_rising(2.0))

        detector._callback.assert_not_called()

    def test_resync_clears_debounce_anchor(self, detector):
        """The pending debounce window belongs to the old polarity."""
        detector.handle_event(_falling(1.0))
        assert detector._state.last_press_ts is not None

        detector.resync(inverted=True, current_state=False)
        assert detector._state.last_press_ts is None


# ── GpioInputBinarySensor.update_inverted ────────────────────────────────────


def _make_sensor(inverted: bool, gpio_manager):
    """Build a sensor off-target.

    The loop is only stored and handed to the (mocked) GPIO manager, so a mock
    stands in for it — running a real loop here would leave the thread without
    a current event loop and break later tests in the same session.
    """
    from boneio.components.input.binary_sensor import GpioInputBinarySensor
    from boneio.core.utils import TimePeriod

    with (
        patch("asyncio.get_running_loop", return_value=MagicMock()),
        patch(
            "boneio.components.input.binary_sensor.get_gpio_manager",
            return_value=gpio_manager,
        ),
    ):
        return GpioInputBinarySensor(
            pin="P8_34",
            name="Door",
            id="door",
            actions={},
            input_type="sensor",
            event_bus=MagicMock(),
            bounce_time=TimePeriod(milliseconds=50),
            inverted=inverted,
        )


class TestUpdateInverted:
    """update_inverted() applies the new polarity without a restart."""

    @pytest.fixture
    def gpio_manager(self):
        gm = MagicMock()
        gm.read_value.return_value = False  # pin LOW
        return gm

    @pytest.fixture
    def sensor(self, gpio_manager):
        return _make_sensor(False, gpio_manager)

    def test_unchanged_value_is_a_no_op(self, sensor, gpio_manager):
        assert sensor.update_inverted(False) is False
        assert sensor._inverted is False
        assert sensor._click_type == (PRESSED, RELEASED)

    def test_change_updates_sensor_and_detector(self, sensor, gpio_manager):
        with patch(
            "boneio.components.input.binary_sensor.get_gpio_manager",
            return_value=gpio_manager,
        ):
            assert sensor.update_inverted(True) is True

        assert sensor._inverted is True
        assert sensor._click_type == (RELEASED, PRESSED)
        assert sensor._detector._inverted is True

    def test_detector_state_matches_the_pin_after_the_change(self, sensor, gpio_manager):
        """Pin LOW + inverted means RELEASED, and the detector must agree."""
        with patch(
            "boneio.components.input.binary_sensor.get_gpio_manager",
            return_value=gpio_manager,
        ):
            sensor.update_inverted(True)

        assert sensor._detector._state.current_state is False


# ── InputManager reload path ─────────────────────────────────────────────────


class TestBinarySensorReloadAppliesInverted:
    """_configure_binary_sensor must push 'inverted' onto the running sensor."""

    @pytest.fixture
    def input_manager(self):
        from boneio.core.manager.inputs import InputManager

        im = InputManager.__new__(InputManager)
        im._manager = MagicMock()
        im._inputs = {}
        im._long_press_mqtt_last_ts = {}
        return im

    def _existing(self, changed: bool):
        existing = MagicMock()
        existing._name = "Door"
        existing.area = None
        existing._device_class = None
        existing.update_inverted.return_value = changed
        return existing

    def test_reload_pushes_inverted_to_the_running_sensor(self, input_manager):
        existing = self._existing(changed=True)
        with patch.object(input_manager, "_publish_input_ha_discovery"):
            input_manager._configure_binary_sensor(
                gpio={"id": "door", "inverted": True},
                pin="P8_34",
                existing_input=existing,
            )
        existing.update_inverted.assert_called_once_with(True)

    def test_state_is_republished_when_polarity_flips(self, input_manager):
        """The reported state is now the opposite one — say so straight away."""
        existing = self._existing(changed=True)
        with patch.object(input_manager, "_publish_input_ha_discovery"):
            input_manager._configure_binary_sensor(
                gpio={"id": "door", "inverted": True},
                pin="P8_34",
                existing_input=existing,
            )
        existing.send_current_state.assert_called_once()

    def test_no_republish_when_nothing_changed(self, input_manager):
        existing = self._existing(changed=False)
        with patch.object(input_manager, "_publish_input_ha_discovery"):
            input_manager._configure_binary_sensor(
                gpio={"id": "door"},
                pin="P8_34",
                existing_input=existing,
            )
        existing.update_inverted.assert_called_once_with(False)
        existing.send_current_state.assert_not_called()
