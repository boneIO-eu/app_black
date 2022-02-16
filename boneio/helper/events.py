import asyncio
import datetime as dt
import signal
import logging

_LOGGER = logging.getLogger(__name__)
UTC = dt.timezone.utc
EVENT_TIME_CHANGED = "event_time_changed"


def utcnow():
    return dt.datetime.now(UTC)


def _async_create_timer(loop: asyncio.AbstractEventLoop, event_callback) -> None:
    """Create a timer that will start on BoneIO start."""
    handle = None

    def schedule_tick(now: dt.datetime) -> None:
        """Schedule a timer tick when the next second rolls around."""
        nonlocal handle
        slp_seconds = 1 - (now.microsecond / 10 ** 6)
        handle = loop.call_later(slp_seconds, fire_time_event)

    def fire_time_event() -> None:
        """Fire next time event."""
        now = utcnow()
        event_callback(now)
        schedule_tick(now)

    def stop_timer() -> None:
        """Stop the timer."""
        if handle is not None:
            handle.cancel()

    schedule_tick(utcnow())
    return stop_timer


class GracefulExit(SystemExit):
    """Graceful exit."""

    def __init__(self, msg=None, code=None):
        super(GracefulExit, self).__init__(msg)
        self.code = code


class ListenerJob:
    """Listener to represent jobs during runtime."""

    def __init__(self, target) -> None:
        """Initialize listener."""
        self.target = target
        self._handle = None

    def add_handle(self, handle):
        """Add handle to listener."""
        self._handle = handle

    @property
    def handle(self):
        """Return handle."""
        return self._handle


class EventBus:
    """Simple event bus which ticks every second."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        """Initialize handler"""
        self._loop = loop or asyncio.get_event_loop()
        self._listeners = {}
        self._sigterm_listeners = []
        self._timer_handle = _async_create_timer(self._loop, self._run_second_event)
        for signame in {"SIGINT", "SIGTERM"}:
            self._loop.add_signal_handler(
                getattr(signal, signame),
                self.ask_exit,
            )

    def _run_second_event(self, time):
        """Run event every second."""
        for key, listener in self._listeners.items():
            if listener.target:
                self._listeners[key].add_handle(
                    self._loop.call_soon(listener.target, time)
                )

    def ask_exit(self):
        """Function to call on exit. Should invoke all sigterm listeners."""
        _LOGGER.debug("Exiting process started.")
        self._listeners = {}
        for target in self._sigterm_listeners:
            target()
        self._timer_handle()
        _LOGGER.info("Shutdown gracefully.")
        raise GracefulExit(code=0)

    def add_listener(self, name, target):
        """Add listener on every second job."""
        self._listeners[name] = ListenerJob(target=target)
        return self._listeners[name]

    def add_sigterm_listener(self, target):
        """Add sigterm listener."""
        self._sigterm_listeners.append(target)

    def remove_listener(self, name):
        """Remove regular listener."""
        if name in self._listeners:
            del self._listeners[name]
