"""API keys: credentials an AI agent or a script uses instead of a login.

A key is ``boneio_pat_`` and 43 characters of randomness, shown once when it
is made. Only its SHA-256 is stored, in ``api_keys.json`` beside
``users.json``: with 256 bits of randomness a slow hash adds nothing, and
scrypt would cost close to a second on a BeagleBone on every request.

A key belongs to an administrator and acts within one scope. It expires,
and it stops working the moment it is revoked or its owner is no longer an
administrator - no restart, as the file is re-read when it changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from boneio.core.atomic_file import write_atomically
from boneio.core.auth.models import Role
from boneio.core.auth.store import UserStore

_LOGGER = logging.getLogger(__name__)

API_KEYS_FILENAME = "api_keys.json"
KEY_PREFIX = "boneio_pat_"
#: The lifetimes offered, in days. There is no "never": a key pasted into an
#: agent's configuration will leak sooner or later.
LIFETIMES_DAYS = (7, 30, 90, 365)
DEFAULT_LIFETIME_DAYS = 30
#: last_used is kept in memory and written at most this often per key: a
#: write per request would be an SD card write per request.
_LAST_USED_PERSIST_S = 3600


class KeyScope(StrEnum):
    """What a key may do; see boneio.webui.middleware.policy for the routes."""

    READ = "read"
    PROPOSE = "propose"
    WRITE = "write"


class ApiKeyError(Exception):
    """A key could not be made, found or stored."""


@dataclass(slots=True)
class ApiKey:
    id: str
    name: str
    owner: str
    scope: KeyScope
    digest: str
    created_at: str
    expires_at: str
    last_used: str = ""

    def public(self) -> dict:
        """What the panel may see: everything but the digest."""
        data = asdict(self)
        del data["digest"]
        data["scope"] = str(self.scope)
        return data


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


class ApiKeyStore:
    """Loads, checks and persists API keys."""

    def __init__(self, path: str | Path, users: UserStore) -> None:
        self._path = Path(path)
        self._users = users
        self._keys: dict[str, ApiKey] = {}
        self._stamp: tuple[int, int] | None = None
        self._loaded = False
        self._lock = threading.RLock()
        self._persisted_use: dict[str, float] = {}

    @classmethod
    def beside(cls, users: UserStore) -> ApiKeyStore:
        """The store next to ``users.json``."""
        return cls(users.path.parent / API_KEYS_FILENAME, users)

    # ---------------------------------------------------------------- file

    def _file_stamp(self) -> tuple[int, int] | None:
        try:
            info = self._path.stat()
        except OSError:
            return None
        return (info.st_mtime_ns, info.st_size)

    def _ensure_loaded(self) -> None:
        stamp = self._file_stamp()
        if self._loaded and stamp == self._stamp:
            return
        keys: dict[str, ApiKey] = {}
        if stamp is not None:
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                for entry in raw.get("keys", []):
                    entry["scope"] = KeyScope(entry["scope"])
                    keys[entry["id"]] = ApiKey(**entry)
            except (OSError, ValueError, TypeError, KeyError) as err:
                # A key file that cannot be read grants nothing; keys must be
                # made again, but no request is let through on a guess.
                _LOGGER.error("Cannot read %s, no API key is accepted: %s", self._path, err)
                keys = {}
        self._keys, self._stamp, self._loaded = keys, stamp, True

    def _save(self) -> None:
        payload = {"version": 1, "keys": [asdict(k) for k in self._keys.values()]}
        try:
            write_atomically(self._path, json.dumps(payload, indent=2), mode=0o600)
        except OSError as err:
            raise ApiKeyError(f"Cannot write {self._path}: {err}") from err
        self._stamp = self._file_stamp()

    # ------------------------------------------------------------- queries

    def list_keys(self) -> list[ApiKey]:
        with self._lock:
            self._ensure_loaded()
            return sorted(self._keys.values(), key=lambda k: k.created_at)

    def create(self, name: str, owner: str, scope: KeyScope, days: int) -> tuple[ApiKey, str]:
        """Make a key and return it with its secret, which is never stored.

        Raises:
            ApiKeyError: For a missing name, an unknown lifetime, or an owner
                who is not an administrator.
        """
        name = (name or "").strip()
        if not name or len(name) > 64:
            raise ApiKeyError("Give the key a name of up to 64 characters.")
        if days not in LIFETIMES_DAYS:
            raise ApiKeyError(f"A key lasts one of {', '.join(map(str, LIFETIMES_DAYS))} days.")
        user = self._users.get_user(owner)
        if user is None or user.role is not Role.ADMIN:
            raise ApiKeyError("Only an administrator can make an API key.")
        secret = KEY_PREFIX + secrets.token_urlsafe(32)
        now = _now()
        key = ApiKey(
            id=secrets.token_hex(4),
            name=name,
            owner=user.username,
            scope=KeyScope(scope),
            digest=_digest(secret),
            created_at=now.isoformat(timespec="seconds"),
            expires_at=(now + timedelta(days=days)).isoformat(timespec="seconds"),
        )
        with self._lock:
            self._ensure_loaded()
            self._keys[key.id] = key
            self._save()
        _LOGGER.info("API key '%s' (%s, %s) made by %s", key.name, key.id, key.scope, key.owner)
        return key, secret

    def revoke(self, key_id: str) -> ApiKey:
        """Remove a key; it stops working at once.

        Raises:
            ApiKeyError: If there is no such key.
        """
        with self._lock:
            self._ensure_loaded()
            key = self._keys.pop(key_id, None)
            if key is None:
                raise ApiKeyError("There is no such API key.")
            self._save()
        _LOGGER.info("API key '%s' (%s) revoked", key.name, key.id)
        return key

    def authenticate(self, secret: str) -> ApiKey | None:
        """The key this secret belongs to, if it is current; None otherwise."""
        if not secret.startswith(KEY_PREFIX):
            return None
        digest = _digest(secret)
        with self._lock:
            self._ensure_loaded()
            key = next((k for k in self._keys.values() if secrets.compare_digest(k.digest, digest)), None)
            if key is None:
                return None
            if datetime.fromisoformat(key.expires_at) <= _now():
                return None
            user = self._users.get_user(key.owner)
            if user is None or user.role is not Role.ADMIN:
                return None
            self._note_use(key)
            return key

    def _note_use(self, key: ApiKey) -> None:
        key.last_used = _now().isoformat(timespec="seconds")
        if time.monotonic() - self._persisted_use.get(key.id, float("-inf")) < _LAST_USED_PERSIST_S:
            return
        self._persisted_use[key.id] = time.monotonic()
        try:
            self._save()
        except ApiKeyError as err:
            _LOGGER.warning("Could not record when API key %s was used: %s", key.id, err)
