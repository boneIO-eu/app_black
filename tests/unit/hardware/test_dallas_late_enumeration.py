"""A Dallas sensor the kernel has not enumerated yet is bound on a later update.

The w1 master finds slaves on its periodic search, which can land after the
application has started. A sensor missing at startup used to be dropped while
its update loop kept running, logging "not initialized" forever.
"""

from __future__ import annotations

import os

os.environ.setdefault("W1THERMSENSOR_NO_KERNEL_MODULE", "1")

from unittest.mock import MagicMock

import w1thermsensor
from w1thermsensor.errors import NoSensorFoundError

from boneio.hardware.onewire import DallasSensor


class _FakeW1:
    present = False

    def __init__(self, sensor_type, sensor_id):
        if not _FakeW1.present:
            raise NoSensorFoundError("not enumerated yet")
        self.sensor_id = sensor_id

    def get_temperature(self):
        return 21.5


async def test_sensor_missing_at_startup_is_bound_later(monkeypatch):
    monkeypatch.setattr(w1thermsensor, "W1ThermSensor", _FakeW1)
    _FakeW1.present = False

    sensor = DallasSensor(
        address="28-00000f898a41",
        id="28_00000f898a41",
        manager=MagicMock(),
        message_bus=MagicMock(),
        topic_prefix="boneio",
        update_interval=None,
    )
    sensor._publish_state = MagicMock()
    assert sensor._pct is None

    await sensor.async_update(timestamp=1.0)
    assert sensor._pct is None
    sensor._publish_state.assert_not_called()

    _FakeW1.present = True
    await sensor.async_update(timestamp=2.0)
    assert sensor._pct.sensor_id == "00000f898a41"
    assert sensor.state == 21.5
