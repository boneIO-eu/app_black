import asyncio
import datetime as dt
import logging
import signal
import time
from datetime import datetime
from typing import Any, Coroutine, List, Optional, Callable, Optional


from boneio.helper.util import callback

_LOGGER = logging.getLogger(__name__)
UTC = dt.timezone.utc
EVENT_TIME_CHANGED = "event_time_changed"
CALLBACK_TYPE = Callable[[], None]


def utcnow() -> dt.datetime:
    return dt.datetime.now(UTC)


time_tracker_utcnow = utcnow


def _async_create_timer(
    loop: asyncio.AbstractEventLoop, event_callback
) -> CALLBACK_TYPE:
    """Create a timer that will start on BoneIO start."""
    handle = None

    def schedule_tick(now: dt.datetime) -> None:
        """Schedule a timer tick when the next second rolls around."""
        nonlocal handle
        slp_seconds = 1 - (now.microsecond / 10**6)
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
        self._output_listeners = {}
        self._sigterm_listeners = []
        self._haonline_listeners = []
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
        self._output_listeners = {}
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

    def add_output_listener(self, name, target):
        """Add output listener."""
        self._output_listeners[name] = ListenerJob(target=target)
        return self._output_listeners[name]
    
    def trigger_output_event(self, event):
        asyncio.create_task(self.async_trigger_output_event(event=event))
    
    async def async_trigger_output_event(self, event):
        listener = self._output_listeners.get(event)
        if listener:
            await listener.target(event)

    def add_haonline_listener(self, target):
        """Add HA Online listener."""
        self._haonline_listeners.append(target)

    def signal_ha_online(self):
        """Call events if HA goes online."""
        for target in self._haonline_listeners:
            target()

    def remove_listener(self, name):
        """Remove regular listener."""
        if name in self._listeners:
            del self._listeners[name]


def as_utc(dattim: dt.datetime) -> dt.datetime:
    """Return a datetime as UTC time.

    Assumes datetime without tzinfo to be in the DEFAULT_TIME_ZONE.
    """
    if dattim.tzinfo == UTC:
        return dattim
    return dattim.astimezone(UTC)


@callback
def async_track_point_in_time(
    loop: asyncio.AbstractEventLoop,
    action,
    point_in_time: datetime,
) -> CALLBACK_TYPE:
    """Add a listener that fires once after a specific point in UTC time."""
    # Ensure point_in_time is UTC
    utc_point_in_time = as_utc(point_in_time)
    expected_fire_timestamp = utc_point_in_time.timestamp()

    # Since this is called once, we accept a so we can avoid
    # having to figure out how to call the action every time its called.
    cancel_callback: Optional[asyncio.TimerHandle] = None

    @callback
    def run_action(job) -> None:
        """Call the action."""
        nonlocal cancel_callback

        # Depending on the available clock support (including timer hardware
        # and the OS kernel) it can happen that we fire a little bit too early
        # as measured by utcnow(). That is bad when callbacks have assumptions
        # about the current time. Thus, we rearm the timer for the remaining
        # time.
        delta = expected_fire_timestamp - time.time()
        if delta > 0:
            _LOGGER.debug("Called %f seconds too early, rearming", delta)

            cancel_callback = loop.call_later(delta, run_action, job)
            return

        loop.call_soon(job, utc_point_in_time)

    delta = expected_fire_timestamp - time.time()
    cancel_callback = loop.call_later(delta, run_action, action)

    @callback
    def unsub_point_in_time_listener() -> None:
        """Cancel the call_later."""
        assert cancel_callback is not None
        cancel_callback.cancel()

    return unsub_point_in_time_listener


@callback
def async_track_point_in_timestamp(
    loop: asyncio.AbstractEventLoop,
    action,
    timestamp: float,
) -> CALLBACK_TYPE:
    """Add a listener that fires once after a specific point in UTC time."""
    # Since this is called once, we accept a so we can avoid
    # having to figure out how to call the action every time its called.
    cancel_callback: Optional[asyncio.TimerHandle] = None

    @callback
    def run_action(job) -> None:
        """Call the action."""
        nonlocal cancel_callback

        now = time.time()

        # Depending on the available clock support (including timer hardware
        # and the OS kernel) it can happen that we fire a little bit too early
        # as measured by utcnow(). That is bad when callbacks have assumptions
        # about the current time. Thus, we rearm the timer for the remaining
        # time.
        delta = timestamp - now
        if delta > 0:
            _LOGGER.debug("Called %f seconds too early, rearming", delta)

            cancel_callback = loop.call_later(delta, run_action, job)
            return

        loop.call_soon(job, timestamp)

    now = time.time()
    delta = timestamp - now
    cancel_callback = loop.call_later(delta, run_action, action)

    @callback
    def unsub_point_in_time_listener() -> None:
        """Cancel the call_later."""
        assert cancel_callback is not None
        cancel_callback.cancel()

    return unsub_point_in_time_listener


@callback
def async_call_later_miliseconds(
    loop: asyncio.AbstractEventLoop,
    action,
    delay: float,
) -> CALLBACK_TYPE:
    """Add a listener that fires once after a specific point in UTC time."""
    # Ensure point_in_time is UTC
    expected_fire_timestamp = time.time() + (delay / 1000)
    return async_track_point_in_timestamp(
        loop=loop, action=action, timestamp=expected_fire_timestamp
    )


def create_unawaited_task_threadsafe(
    loop: asyncio.AbstractEventLoop,
    transient_tasks: List["asyncio.Task[Any]"],
    coro: Coroutine[Any, Any, None],
    task_future: Optional["asyncio.Future[asyncio.Task[Any]]"] = None,
) -> None:
    """
    Schedule a coroutine on the loop and add the Task to transient_tasks.
    """

    def callback() -> None:
        task = loop.create_task(coro)
        transient_tasks.append(task)
        if task_future is not None:
            task_future.set_result(task)

    loop.call_soon_threadsafe(callback)
