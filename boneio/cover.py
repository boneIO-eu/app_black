import asyncio
import atexit
from typing import Any
from boneio.const import COVER, IDLE, OPEN, OPENING, CLOSING, CLOSED
from boneio.helper.events import EventBus
from boneio.helper.mqtt import BasicMqtt
from boneio.relay import MCPRelay


class RelayHelper:
    def __init__(self, relay, time):
        self._relay = relay
        self._steps = 100 / time

    @property
    def relay(self):
        return self._relay

    @property
    def steps(self):
        return self._steps


class Cover(BasicMqtt):
    # react on messages

    def __init__(
        self,
        id: str,
        open_relay: Any,
        close_relay: MCPRelay,
        open_time: int,
        close_time: int,
        event_bus: EventBus,
        restored_state: int = 0,
        **kwargs,
    ):
        self._loop = asyncio.get_event_loop()
        self._id = id
        super().__init__(id=id, name=id, topic_type=COVER, **kwargs)
        self._lock = asyncio.Lock()
        self._open = RelayHelper(relay=open_relay, time=open_time)
        self._close = RelayHelper(relay=close_relay, time=close_time)
        self._set_position = None
        self._current_operation = IDLE
        self._position = restored_state
        self._requested_closing = True
        self._event_bus = event_bus
        self._timer_handle = None
        if self._position is None:
            self._closed = True
        else:
            self._closed = self._position <= 0
        atexit.register(self.__exit__)
        self._loop.call_soon_threadsafe(
            self._loop.call_later,
            0.5,
            self.send_state,
        )

    async def run_cover(
        self,
        current_operation: str,
    ) -> None:
        if self._current_operation != IDLE:
            self._stop_cover()
        self._current_operation = current_operation

        def get_relays():
            if current_operation == OPENING:
                return (self._open.relay, self._close.relay)
            else:
                return (self._close.relay, self._open.relay)

        (relay, inverted_relay) = get_relays()
        async with self._lock:
            if inverted_relay.is_active:
                inverted_relay.turn_off()
            self._timer_handle = self._event_bus.add_listener(
                f"{COVER}{id}", self.listen_cover
            )
            relay.turn_on()

    def __exit__(self):
        self._stop_cover(on_exit=True)

    @property
    def cover_state(self):
        return CLOSED if self._closed else OPEN

    def stop_cover(self):
        if self._current_operation != IDLE:
            self._stop_cover(on_exit=False)

    def send_state(self):
        self._send_message(topic=f"{self._send_topic}/state", payload=self.cover_state)
        self._send_message(
            topic=f"{self._send_topic}/pos", payload=round(self._position, 0)
        )

    def _stop_cover(self, on_exit=False):
        self._open.relay.turn_off()
        self._close.relay.turn_off()
        if self._timer_handle is not None:
            self._event_bus.remove_listener(f"{COVER}{id}")
            self._timer_handle = None
            self._set_position = None
            if not on_exit:
                self.send_state()
        self._current_operation = IDLE

    @property
    def current_cover_position(self):
        """Return the current position of the cover."""
        return round(self._position, 0)

    def listen_cover(self, *args):
        if self._current_operation == IDLE:
            return

        def get_step():
            if self._requested_closing:
                return -self._close.steps
            else:
                return self._open.steps

        step = get_step()
        self._position += step
        rounded_pos = round(self._position, 0)
        if self._set_position:
            if self._requested_closing:
                if rounded_pos < 95:
                    rounded_pos = round(self._position, -1)
            elif rounded_pos > 5:
                rounded_pos = round(self._position, -1)
        print("POSTIION PUBLISHED", rounded_pos)
        self._send_message(topic=f"{self._send_topic}/pos", payload=rounded_pos)
        if rounded_pos in (100, 0, self._set_position):
            self._stop_cover()
            self._position = rounded_pos

        self._closed = self.current_cover_position <= 0

    async def close_cover(self):
        if self._position == 0:
            return
        if self._position is None:
            self._closed = True
            return

        self._requested_closing = True
        self._send_message(topic=f"{self._send_topic}/state", payload=CLOSING)
        await self.run_cover(
            current_operation=CLOSING,
        )

    async def open_cover(self):
        if self._position == 100:
            return
        if self._position is None:
            self._closed = False
            return

        self._requested_closing = False
        self._send_message(topic=f"{self._send_topic}/state", payload=OPENING)
        await self.run_cover(
            current_operation=OPENING,
        )

    async def set_cover_position(self, position: int):
        """Move the cover to a specific position."""
        set_position = round(position, -1)
        print("SETTING POSITION", position, set_position)
        if self._position == position or set_position == self._set_position:
            return
        if self._set_position:
            self._stop_cover(on_exit=True)
        self._set_position = set_position

        self._requested_closing = position < self._position
        current_operation = CLOSING if self._requested_closing else OPENING
        self._send_message(topic=f"{self._send_topic}/state", payload=current_operation)
        await self.run_cover(
            current_operation=current_operation,
        )
