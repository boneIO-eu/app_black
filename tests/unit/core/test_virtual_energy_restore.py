"""A virtual energy counter must not overwrite its stored total at boot."""

import asyncio
import json
import sys
from unittest.mock import MagicMock

sys.modules.setdefault("gpiod", MagicMock())

from boneio.components.sensor import virtual_energy  # noqa: E402
from boneio.components.sensor.virtual_energy import VirtualEnergySensor  # noqa: E402
from boneio.const import ON  # noqa: E402


class _Bus:
    """A broker that connects only when the test says so."""

    def __init__(self):
        self.subscribed = asyncio.Event()
        self.listeners = {}
        self.sent = []

    async def subscribe_and_listen(self, topic, callback, *, retain_aware=False):
        self.listeners[topic] = callback

    async def unsubscribe_and_stop_listen(self, topic):
        self.listeners.pop(topic, None)

    async def wait_until_subscribed(self):
        await self.subscribed.wait()

    def send_message(self, topic, payload, retain=False, qos=0):
        self.sent.append((topic, payload))


async def test_slow_broker_does_not_reset_the_counter(monkeypatch):
    monkeypatch.setattr(virtual_energy, "RESTORE_GRACE_SECONDS", 0.05)
    bus = _Bus()
    output = MagicMock(id="out_01", state=ON)
    sensor = VirtualEnergySensor(
        id="lamp", name="Lamp", output=output, message_bus=bus, event_bus=MagicMock(),
        loop=asyncio.get_running_loop(), topic_prefix="boneio/x", sensor_type="power", power_usage=3600.0,
    )
    sensor.start_tracking()  # light was on at boot

    await asyncio.sleep(0.2)  # well past the grace, broker still away
    assert bus.sent == []

    bus.subscribed.set()
    await asyncio.sleep(0)
    await bus.listeners["boneio/x/energy/lamp"]("boneio/x/energy/lamp", json.dumps({"energy": 16429.0}))
    await asyncio.sleep(0.01)

    energy = bus.sent[-1][1]["energy"]
    # Stored total plus ~0.2 s at 3600 W (1 Wh per second) — not zero.
    assert 16429.1 < energy < 16430
    sensor.stop_tracking()
