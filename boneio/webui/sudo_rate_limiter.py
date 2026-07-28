"""Rate limiter for sudo password attempts.

Prevents brute-force attacks on endpoints that accept sudo passwords.
Uses a sliding window approach: max N attempts per IP within a time window.
After exhausting attempts, the IP is locked out until the window expires.

Usage::

    from boneio.webui.sudo_rate_limiter import sudo_rate_limiter

    # In an endpoint:
    client_ip = request.client.host if request.client else "unknown"
    if not sudo_rate_limiter.check(client_ip):
        return {"status": "error", "message": "Too many attempts. Try again later."}

    # After a failed sudo attempt:
    sudo_rate_limiter.record_failure(client_ip)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock

_LOGGER = logging.getLogger(__name__)

# Configuration
_MAX_ATTEMPTS = 3
"""Maximum failed sudo attempts per IP within the time window."""

_WINDOW_SECONDS = 300
"""Time window in seconds (5 minutes)."""

# Generic error message — intentionally vague to avoid leaking auth info
SUDO_RATE_LIMITED_RESPONSE: dict[str, str] = {
    "status": "error",
    "message": "Too many attempts. Try again later.",
}

SUDO_AUTH_FAILED_RESPONSE: dict[str, str] = {
    "status": "error",
    "message": "Authentication failed.",
}


class SudoRateLimiter:
    """Sliding-window rate limiter for sudo password attempts.

    Thread-safe. Tracks failed attempts per client IP and blocks
    further requests once the threshold is exceeded.
    """

    def __init__(self, max_attempts: int = _MAX_ATTEMPTS, window_seconds: int = _WINDOW_SECONDS):
        """Initialize the rate limiter.

        Args:
            max_attempts: Maximum allowed failures per IP within the window.
            window_seconds: Duration of the sliding window in seconds.
        """
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._failures: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _prune(self, ip: str) -> None:
        """Remove expired failure timestamps for the given IP.

        Args:
            ip: Client IP address.
        """
        cutoff = time.monotonic() - self._window_seconds
        self._failures[ip] = [t for t in self._failures[ip] if t > cutoff]
        if not self._failures[ip]:
            del self._failures[ip]

    def check(self, ip: str) -> bool:
        """Check if the IP is allowed to attempt sudo.

        Args:
            ip: Client IP address.

        Returns:
            True if the IP has remaining attempts, False if rate-limited.
        """
        with self._lock:
            self._prune(ip)
            count = len(self._failures.get(ip, []))
            if count >= self._max_attempts:
                _LOGGER.warning(
                    "Sudo rate limit exceeded for IP %s (%d/%d attempts in %ds window)",
                    ip,
                    count,
                    self._max_attempts,
                    self._window_seconds,
                )
                return False
            return True

    def record_failure(self, ip: str) -> None:
        """Record a failed sudo attempt for the given IP.

        Args:
            ip: Client IP address.
        """
        with self._lock:
            self._prune(ip)
            self._failures[ip].append(time.monotonic())
            count = len(self._failures[ip])

        _LOGGER.warning(
            "Failed sudo attempt from IP %s (%d/%d within %ds window)",
            ip,
            count,
            self._max_attempts,
            self._window_seconds,
        )

    def remaining_attempts(self, ip: str) -> int:
        """Get the number of remaining attempts for the given IP.

        Args:
            ip: Client IP address.

        Returns:
            Number of attempts remaining before rate limiting kicks in.
        """
        with self._lock:
            self._prune(ip)
            return max(0, self._max_attempts - len(self._failures.get(ip, [])))

    def seconds_until_reset(self, ip: str) -> float:
        """Get seconds until the oldest failure expires for the given IP.

        Args:
            ip: Client IP address.

        Returns:
            Seconds until the next attempt becomes available, or 0 if not limited.
        """
        with self._lock:
            self._prune(ip)
            failures = self._failures.get(ip, [])
            if len(failures) < self._max_attempts:
                return 0.0
            oldest = failures[0]
            return max(0.0, (oldest + self._window_seconds) - time.monotonic())


# Module-level singleton — shared across all sudo endpoints
sudo_rate_limiter = SudoRateLimiter()
