"""The web UI registers a global listener per event type; each must exist.

``add_all_websocket_listeners`` subscribed to ``schedule`` events, but the bus
had no ``schedule`` slot, so the call raised ``KeyError``. It runs inside the
WebSocket handler, right after the first state dump — the handler died there,
the browser reconnected every second, and nothing after the dump ever arrived.
"""

from __future__ import annotations

import asyncio

from boneio.core.events.bus import EventBus


async def _noop(_event) -> None:
    return None


def test_every_websocket_event_type_can_be_listened_to() -> None:
    bus = EventBus(loop=asyncio.new_event_loop())
    for event_type in ("output", "group", "cover", "input", "modbus_device", "sensor", "schedule"):
        bus.add_event_listener(
            event_type=event_type, entity_id="", listener_id=f"ws_{event_type}_global", target=_noop
        )
        bus.remove_event_listener(event_type=event_type, listener_id=f"ws_{event_type}_global")
