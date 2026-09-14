"""Sliding-window rate limiting for credential endpoints.

Generalised out of the sudo limiter, which the 1.5.0 pentest noted was wired to
the sudo routes and nowhere else — ``/api/login`` accepted unlimited guesses
(F-06).

Two deliberate properties:

**It throttles, it never locks out.** Every counter drains as its window slides,
so the worst an attacker can do is make the owner wait a few minutes. A
permanent lockout would recreate the failure this whole release is trying to
remove: the owner shut out of their own controller.

**It counts per IP *and* per account.** Either alone has a hole. Per IP is
blind behind a reverse proxy, where every client arrives as the proxy and one
attacker would throttle everybody. Per account is blind to spraying one guess
across many usernames. Counting both means a single attacker trips their own
bucket without taking the rest of the household with them.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock

_LOGGER = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window limiter keyed by an arbitrary string.

    Thread-safe. Counts failures per key and refuses further attempts once the
    threshold is reached, until the oldest failure ages out of the window.
    """

    def __init__(
        self,
        max_attempts: int,
        window_seconds: int,
        name: str = "rate limit",
    ) -> None:
        """
        Args:
            max_attempts: Failures allowed per key within the window.
            window_seconds: Length of the sliding window.
            name: Label used in log lines.
        """
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._name = name
        self._failures: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    @property
    def max_attempts(self) -> int:
        """Failures allowed per key within the window."""
        return self._max_attempts

    @property
    def window_seconds(self) -> int:
        """Length of the sliding window, in seconds."""
        return self._window_seconds

    def _prune(self, key: str) -> None:
        """Drop failure timestamps that have aged out.

        Args:
            key: Bucket key.
        """
        cutoff = time.monotonic() - self._window_seconds
        self._failures[key] = [t for t in self._failures[key] if t > cutoff]
        if not self._failures[key]:
            del self._failures[key]

    def check(self, key: str) -> bool:
        """Whether this key may attempt again.

        Args:
            key: Bucket key.

        Returns:
            True if attempts remain.
        """
        with self._lock:
            self._prune(key)
            count = len(self._failures.get(key, []))
            if count >= self._max_attempts:
                _LOGGER.warning(
                    "%s exceeded for %s (%d/%d in %ds window)",
                    self._name,
                    key,
                    count,
                    self._max_attempts,
                    self._window_seconds,
                )
                return False
            return True

    def check_all(self, *keys: str) -> bool:
        """Whether every key still has attempts left.

        Args:
            *keys: Bucket keys to test.

        Returns:
            True only if none of the keys is currently throttled.
        """
        return all(self.check(key) for key in keys)

    def record_failure(self, key: str) -> None:
        """Count one failure against a key.

        Args:
            key: Bucket key.
        """
        with self._lock:
            self._prune(key)
            self._failures[key].append(time.monotonic())
            count = len(self._failures[key])

        _LOGGER.warning(
            "Failed attempt (%s) for %s (%d/%d within %ds)",
            self._name,
            key,
            count,
            self._max_attempts,
            self._window_seconds,
        )

    def record_failures(self, *keys: str) -> None:
        """Count one failure against several keys at once.

        Args:
            *keys: Bucket keys to charge.
        """
        for key in keys:
            self.record_failure(key)

    def reset(self, *keys: str) -> None:
        """Clear the counters for these keys.

        Called after a success, so someone who mistyped their password twice
        and then got it right does not carry the failures around with them.

        Args:
            *keys: Bucket keys to clear.
        """
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)

    def remaining_attempts(self, key: str) -> int:
        """Attempts left before this key is throttled.

        Args:
            key: Bucket key.

        Returns:
            Remaining attempts, never below zero.
        """
        with self._lock:
            self._prune(key)
            return max(0, self._max_attempts - len(self._failures.get(key, [])))

    def seconds_until_reset(self, key: str) -> float:
        """How long until this key may attempt again.

        Args:
            key: Bucket key.

        Returns:
            Seconds to wait, or 0 when not throttled.
        """
        with self._lock:
            self._prune(key)
            failures = self._failures.get(key, [])
            if len(failures) < self._max_attempts:
                return 0.0
            return max(0.0, (failures[0] + self._window_seconds) - time.monotonic())

    def retry_after(self, *keys: str) -> int:
        """Seconds a client should wait, across several keys.

        Args:
            *keys: Bucket keys to consider.

        Returns:
            The longest wait among the keys, rounded up to whole seconds.
        """
        longest = max((self.seconds_until_reset(key) for key in keys), default=0.0)
        return max(1, int(longest + 0.999))


# Login attempts. Ten tries per five minutes, counted per IP and per account.
#
# The number is generous on purpose: a password check is a deliberately slow
# scrypt hash (~0.9 s on a BeagleBone), so ten guesses already cost an attacker
# about ten seconds of the device's CPU. The limiter is here to stop a grind
# that would otherwise run for days, not to punish someone fumbling their
# password on a phone keyboard.
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 300

login_rate_limiter = RateLimiter(
    max_attempts=LOGIN_MAX_ATTEMPTS,
    window_seconds=LOGIN_WINDOW_SECONDS,
    name="login rate limit",
)


def ip_key(ip: str) -> str:
    """Bucket key for a client address.

    Args:
        ip: Client IP.

    Returns:
        Namespaced key, so an address can never collide with a username.
    """
    return f"ip:{ip}"


def user_key(username: str) -> str:
    """Bucket key for an account name.

    Matching the store, names are compared case-insensitively, so 'Admin' and
    'admin' share one bucket instead of doubling an attacker's budget.

    Args:
        username: Username as supplied by the client.

    Returns:
        Namespaced key.
    """
    return f"user:{(username or '').strip().lower()}"
