"""Wait for udev to hand a device node over while boneIO starts.

boneio.service no longer waits for multi-user.target, so on the very first
boot of a fresh image it can reach /dev/i2c-* or /dev/gpiochip* before udev
has applied the rules that hand them to the gpio group. The node is then
missing or not ours yet, and a single attempt to open it fails for good: the
I2C bus crashed the start, the GPIO inputs were silently dead.

:class:`NodeWait` turns that single attempt into a short wait. The callers
keep their own loops, because the I2C bus is opened synchronously and the GPIO
chips from a coroutine, and each keeps its own error message for when the
wait runs out.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

#: How long the device nodes together may take to become usable.
#:
#: A controller from dev17 failed three starts in a row on /dev/i2c-2; that
#: gap was at least ~30 s (three starts, each RestartSec plus the imports
#: before the bus is opened). 60 s covers it with margin while staying under
#: systemd's default TimeoutStopSec of 90 s: neither wait notices a stop - the
#: I2C one blocks the event loop and the runner only looks at the shutdown
#: signal once startup is over - so a stop arriving during a wait is handled
#: when it ends.
#:
#: The budget is shared rather than per node. It starts when the first node
#: is found not ready, and a node that comes later only gets what is left:
#: udev works through the rules once, so if the bus took 50 s the chips have
#: had those 50 s too, and two separate minutes would push a stop past the
#: limit.
STARTUP_WAIT_SECONDS = 60.0

#: Pause between attempts.
RETRY_SECONDS = 1.0

#: Monotonic time the shared budget runs out, set by the first wait.
_budget_ends: float | None = None


def reset_startup_budget() -> None:
    """Forget the shared budget (for tests, which each start at time zero)."""
    global _budget_ends
    _budget_ends = None


def is_not_ready(err: BaseException) -> bool:
    """Whether ``err`` is one of the two states udev leaves a node in before its rule runs.

    Missing (ENOENT) or not accessible yet (EACCES/EPERM). Anything else is a
    real failure and is not waited out.
    """
    return isinstance(err, (PermissionError, FileNotFoundError))


class NodeWait:
    """One device node's wait for udev, inside the budget all nodes share.

    The caller tries to open the node in a loop. On an error it asks
    :meth:`retry`: True means sleep :data:`RETRY_SECONDS` and try again, False
    means give up and fail the way it did before there was a wait. After a
    successful open it calls :meth:`opened`. The start of the wait is logged
    once at WARNING and its end at INFO, so a slow udev leaves two lines in
    the journal, not one per second.
    """

    def __init__(
        self,
        path: str,
        logger: logging.Logger,
        wait: float = STARTUP_WAIT_SECONDS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Initialize the wait.

        Args:
            path: Device node, for the log messages.
            logger: Logger of the caller, so the messages read as its own.
            wait: Longest this node may wait, within the shared budget; 0
                means no retry at all.
            clock: Monotonic clock; defaults to :func:`time.monotonic`.
        """
        self.path = path
        self._logger = logger
        self._wait = wait
        self._clock = clock or time.monotonic
        self._started: float | None = None
        self._deadline = 0.0

    @property
    def waiting(self) -> bool:
        """Whether a wait has started, i.e. at least one attempt was retried."""
        return self._started is not None

    @property
    def elapsed(self) -> float:
        """Seconds since the wait started, 0 if it never did."""
        if self._started is None:
            return 0.0
        return self._clock() - self._started

    def retry(self, err: BaseException) -> bool:
        """Say whether to try again after ``err``.

        Args:
            err: What the last attempt raised.

        Returns:
            True to sleep and retry, False to give up.
        """
        if not is_not_ready(err):
            return False
        now = self._clock()
        if self._started is None:
            global _budget_ends
            if _budget_ends is None:
                _budget_ends = now + STARTUP_WAIT_SECONDS
            deadline = min(_budget_ends, now + self._wait)
            if now >= deadline:
                return False
            self._started = now
            self._deadline = deadline
            strerror = getattr(err, "strerror", None)
            self._logger.warning(
                "%s not accessible yet (%s), waiting for udev", self.path, strerror or err
            )
            return True
        return now < self._deadline

    def opened(self) -> None:
        """Record that the node opened; log the end of the wait if there was one."""
        if self._started is not None:
            self._logger.info("%s accessible after %.1f s", self.path, self.elapsed)
