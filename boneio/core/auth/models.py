"""Account model for the boneIO web UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class Role(StrEnum):
    """What a web UI account is allowed to do.

    ADMIN may change configuration and operate the device. VIEWER may only
    read state and drive existing outputs — the distinction is enforced in the
    auth middleware, not here.
    """

    ADMIN = "admin"
    VIEWER = "viewer"


def utc_now() -> str:
    """Current time as an ISO-8601 string in UTC.

    Returns:
        Timestamp such as ``2026-09-14T08:30:00+00:00``.
    """
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class User:
    """A single web UI account."""

    username: str
    password_hash: str
    role: Role = Role.ADMIN
    created_at: str = ""
    updated_at: str = ""
    # Bumped whenever the password changes. Login tokens carry the value they
    # were issued under, and one that no longer matches is refused, which is
    # how a password change signs every other session out.
    session_version: int = 0
    # Single browser sessions cut off after too many wrong passwords, as
    # session id → the unix time its token expires, after which the entry is
    # pointless and gets pruned.
    revoked_sessions: dict[str, int] = field(default_factory=dict)
    # Wrong passwords typed per session while it was signed in, as session id
    # → {"count": n, "until": token expiry}. Kept here, not in memory, so a
    # restart does not hand a guessing session a fresh allowance.
    session_failures: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialise for ``users.json``.

        Returns:
            Plain dictionary with JSON-safe values.
        """
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "role": str(self.role),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "session_version": self.session_version,
            "revoked_sessions": dict(self.revoked_sessions),
            "session_failures": {k: dict(v) for k, v in self.session_failures.items()},
        }

    @classmethod
    def from_dict(cls, raw: dict) -> User:
        """Build a user from a ``users.json`` entry.

        An unknown or missing role falls back to VIEWER rather than ADMIN, so
        a hand-edited or partially corrupted file cannot silently grant more
        privilege than it names.

        Args:
            raw: One entry from the ``users`` array.

        Returns:
            Parsed user.

        Raises:
            ValueError: If the entry has no username or no password hash.
        """
        username = str(raw.get("username", "")).strip()
        password_hash = str(raw.get("password_hash", ""))
        if not username or not password_hash:
            raise ValueError("User entry needs a username and a password_hash")

        try:
            role = Role(str(raw.get("role", "")).strip().lower())
        except ValueError:
            role = Role.VIEWER

        # Absent in every users.json written before 1.6.0.dev23, and those
        # accounts' tokens carry no version either: both read as 0.
        try:
            session_version = int(raw.get("session_version", 0))
        except (TypeError, ValueError):
            session_version = 0

        return cls(
            revoked_sessions=_int_map(raw.get("revoked_sessions")),
            session_failures=_failure_map(raw.get("session_failures")),
            username=username,
            password_hash=password_hash,
            role=role,
            created_at=str(raw.get("created_at", "")),
            updated_at=str(raw.get("updated_at", "")),
            session_version=session_version,
        )

    def to_public_dict(self) -> dict:
        """Serialise for API responses, without the password hash.

        Returns:
            Dictionary safe to return over HTTP.
        """
        return {
            "username": self.username,
            "role": str(self.role),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _int_map(raw) -> dict[str, int]:
    """Read a ``{str: int}`` map from users.json, dropping what does not fit.

    Args:
        raw: Whatever the file holds under the key.

    Returns:
        The well-formed entries.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool):
            out[key] = value
    return out


def _failure_map(raw) -> dict[str, dict]:
    """Read the per-session failure counts, dropping what does not fit.

    Args:
        raw: Whatever the file holds under the key.

    Returns:
        ``{session_id: {"count": int, "until": int}}`` for the entries that
        have both.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        count, until = value.get("count"), value.get("until")
        if all(isinstance(v, int) and not isinstance(v, bool) for v in (count, until)):
            out[key] = {"count": count, "until": until}
    return out
