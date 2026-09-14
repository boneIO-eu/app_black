"""Account model for the boneIO web UI."""

from __future__ import annotations

from dataclasses import dataclass
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

        return cls(
            username=username,
            password_hash=password_hash,
            role=role,
            created_at=str(raw.get("created_at", "")),
            updated_at=str(raw.get("updated_at", "")),
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
