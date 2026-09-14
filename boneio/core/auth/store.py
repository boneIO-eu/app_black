"""Persistent account store backed by ``users.json``.

The file sits next to ``config.yaml`` and is owned by the application: it is
written atomically with 0600 permissions and is never exposed through the file
editor. Keeping accounts out of ``config.yaml`` means the config can still be
exported, backed up or pasted into a support ticket without carrying
credentials with it.

Format::

    {"version": 1, "users": [{"username": ..., "password_hash": ..., ...}]}
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path

from boneio.core.auth.hashing import hash_password, verify_password
from boneio.core.auth.models import Role, User, utc_now

_LOGGER = logging.getLogger(__name__)

USERS_FILENAME = "users.json"
STORE_VERSION = 1

# Rejecting these keeps a username from being confused with a path segment or
# a shell word anywhere it is later logged, compared or embedded in a token.
_FORBIDDEN_CHARS = set('/\\:"\'`$\x00\r\n\t')
_MAX_USERNAME_LEN = 64
_MIN_PASSWORD_LEN = 8


class UserStoreError(Exception):
    """Raised when an account operation cannot be carried out."""


def normalize_username(username: str) -> str:
    """Validate a username and return its canonical form.

    Usernames are matched case-insensitively, because a user who registers
    ``Admin`` will try to log in as ``admin`` and should not be told their
    password is wrong.

    Args:
        username: Raw username from the client.

    Returns:
        Lower-cased, stripped username.

    Raises:
        UserStoreError: If the username is empty, too long, or contains a
            character that is not safe to round-trip.
    """
    cleaned = (username or "").strip()
    if not cleaned:
        raise UserStoreError("Username must not be empty")
    if len(cleaned) > _MAX_USERNAME_LEN:
        raise UserStoreError(
            f"Username must be at most {_MAX_USERNAME_LEN} characters"
        )
    if _FORBIDDEN_CHARS & set(cleaned):
        raise UserStoreError("Username contains a forbidden character")
    return cleaned.lower()


def validate_password(password: str) -> None:
    """Reject passwords that are too short to be worth hashing.

    Args:
        password: Plain-text password.

    Raises:
        UserStoreError: If the password is shorter than the minimum length.
    """
    if not password or len(password) < _MIN_PASSWORD_LEN:
        raise UserStoreError(
            f"Password must be at least {_MIN_PASSWORD_LEN} characters"
        )


class UserStore:
    """Loads, queries and persists web UI accounts."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        """
        Args:
            path: Full path to ``users.json``.
        """
        self._path = Path(path)
        self._users: dict[str, User] = {}
        self._lock = threading.RLock()
        self._loaded = False
        # Fingerprint of the file as last read, so an edit made outside this
        # process is picked up without a restart.
        self._stamp: tuple[int, int] | None = None

    @classmethod
    def for_config_file(cls, yaml_config_file: str | os.PathLike[str]) -> UserStore:
        """Build a store for the config directory holding ``yaml_config_file``.

        Args:
            yaml_config_file: Path to ``config.yaml``.

        Returns:
            Store pointing at ``users.json`` beside that config.
        """
        return cls(Path(yaml_config_file).parent / USERS_FILENAME)

    @property
    def path(self) -> Path:
        """Path of the backing file."""
        return self._path

    # ---------------------------------------------------------------- loading

    def load(self) -> None:
        """Read ``users.json`` into memory.

        A missing file is normal — it means the device has not been through
        onboarding yet — and leaves the store empty. A file that exists but
        cannot be parsed is an error the caller must see, because silently
        treating it as "no accounts" would drop the device back into an
        unauthenticated state.

        Raises:
            UserStoreError: If the file exists but cannot be read or parsed.
        """
        with self._lock:
            self._users = {}
            self._loaded = True

            self._stamp = self._file_stamp()

            if not self._path.exists():
                _LOGGER.debug("No %s yet — device is not provisioned", self._path)
                return

            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as err:
                raise UserStoreError(f"Cannot read {self._path}: {err}") from err

            if not isinstance(raw, dict):
                raise UserStoreError(f"{self._path} must contain a JSON object")

            entries = raw.get("users", [])
            if not isinstance(entries, list):
                raise UserStoreError(f"{self._path}: 'users' must be a list")

            for entry in entries:
                if not isinstance(entry, dict):
                    _LOGGER.warning("Skipping malformed user entry in %s", self._path)
                    continue
                try:
                    user = User.from_dict(entry)
                except ValueError as err:
                    _LOGGER.warning("Skipping user entry in %s: %s", self._path, err)
                    continue
                self._users[normalize_username(user.username)] = user

            _LOGGER.info(
                "Loaded %d account(s) from %s", len(self._users), self._path
            )

    def _file_stamp(self) -> tuple[int, int] | None:
        """Cheap fingerprint of the backing file.

        Returns:
            (mtime_ns, size), or None when the file does not exist.
        """
        try:
            info = self._path.stat()
        except OSError:
            return None
        return (info.st_mtime_ns, info.st_size)

    def _ensure_loaded(self) -> None:
        """Load the file on first use, and re-read it if it changed on disk.

        The running web server keeps this store in memory, so an account
        created or reset with ``boneio accounts`` would otherwise not take
        effect until the service restarted. Restarting a controller to recover
        a password would interrupt whatever it is automating, so the file is
        re-read instead — one stat call on the read paths.
        """
        if not self._loaded:
            self.load()
            return

        if self._file_stamp() != self._stamp:
            _LOGGER.info("%s changed on disk — reloading accounts", self._path)
            self.load()

    # ---------------------------------------------------------------- saving

    def _save(self) -> None:
        """Write the store to disk atomically with 0600 permissions.

        Raises:
            UserStoreError: If the file cannot be written.
        """
        payload = {
            "version": STORE_VERSION,
            "users": [user.to_dict() for user in self._users.values()],
        }

        dir_path = self._path.parent
        fd = None
        temp_path = None
        try:
            # Same directory as the target, so os.replace stays atomic; mkstemp
            # already creates the file 0600, which is exactly what we want the
            # final file to be.
            fd, temp_path = tempfile.mkstemp(
                suffix=".tmp", prefix=".users_", dir=dir_path
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = None  # os.fdopen took ownership
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())

            os.chmod(temp_path, 0o600)
            os.replace(temp_path, self._path)
            temp_path = None
            self._stamp = self._file_stamp()
        except OSError as err:
            raise UserStoreError(f"Cannot write {self._path}: {err}") from err
        finally:
            if fd is not None:
                os.close(fd)
            if temp_path is not None:
                # The rename never happened; do not leave the partial file with
                # a password hash in it lying around the config directory.
                try:
                    os.unlink(temp_path)
                except OSError:
                    _LOGGER.warning("Could not remove temp file %s", temp_path)

    # --------------------------------------------------------------- queries

    def is_provisioned(self) -> bool:
        """Report whether the device has at least one admin account.

        This is the single source of truth for "has onboarding been done?".

        Returns:
            True if an admin account exists.
        """
        self._ensure_loaded()
        with self._lock:
            return any(user.role is Role.ADMIN for user in self._users.values())

    def list_users(self) -> list[User]:
        """All accounts, ordered by username.

        Returns:
            List of users.
        """
        self._ensure_loaded()
        with self._lock:
            return sorted(self._users.values(), key=lambda user: user.username)

    def get_user(self, username: str) -> User | None:
        """Look up one account.

        Args:
            username: Username in any casing.

        Returns:
            The user, or None if there is no such account.
        """
        self._ensure_loaded()
        try:
            key = normalize_username(username)
        except UserStoreError:
            return None
        with self._lock:
            return self._users.get(key)

    def verify_credentials(self, username: str, password: str) -> User | None:
        """Check a username and password pair.

        When the username does not exist the password is still hashed against
        a throwaway value. Without that, an unknown username would return
        noticeably faster than a known one and turn the login route into a
        user-enumeration oracle.

        This is CPU-bound for a few hundred milliseconds on a BeagleBone, so
        async callers must run it in a worker thread.

        Args:
            username: Username supplied by the client.
            password: Password supplied by the client.

        Returns:
            The matching user, or None if the credentials are wrong.
        """
        user = self.get_user(username)
        if user is None:
            verify_password(password or "x", _DUMMY_HASH)
            return None

        if not verify_password(password, user.password_hash):
            return None
        return user

    # --------------------------------------------------------------- updates

    def add_user(
        self,
        username: str,
        password: str,
        role: Role = Role.ADMIN,
        enforce_policy: bool = True,
    ) -> User:
        """Create an account and persist it.

        Args:
            username: Desired username.
            password: Plain-text password.
            role: Role to grant.
            enforce_policy: Whether the password must satisfy the minimum
                length. Only the migration of a pre-1.6 ``web.auth`` block
                passes False: that password already guards the device, and
                rejecting it for being short would lock the owner out of their
                own box during an upgrade. Every interactive path leaves this
                True.

        Returns:
            The created user.

        Raises:
            UserStoreError: If the name or password is invalid, or the account
                already exists.
        """
        self._ensure_loaded()
        key = normalize_username(username)
        if enforce_policy:
            validate_password(password)
        elif not password:
            raise UserStoreError("Password must not be empty")

        with self._lock:
            if key in self._users:
                raise UserStoreError(f"Account '{username}' already exists")

            now = utc_now()
            user = User(
                username=username.strip(),
                password_hash=hash_password(password),
                role=role,
                created_at=now,
                updated_at=now,
            )
            self._users[key] = user
            self._save()

        _LOGGER.info("Created %s account '%s'", role, user.username)
        return user

    def set_password(self, username: str, password: str) -> User:
        """Replace an account's password.

        Args:
            username: Account to change.
            password: New plain-text password.

        Returns:
            The updated user.

        Raises:
            UserStoreError: If the account does not exist or the password is
                too short.
        """
        self._ensure_loaded()
        key = normalize_username(username)
        validate_password(password)

        with self._lock:
            user = self._users.get(key)
            if user is None:
                raise UserStoreError(f"No such account: {username}")
            user.password_hash = hash_password(password)
            user.updated_at = utc_now()
            self._save()

        _LOGGER.info("Password changed for account '%s'", user.username)
        return user

    def set_role(self, username: str, role: Role) -> User:
        """Change an account's role.

        Args:
            username: Account to change.
            role: New role.

        Returns:
            The updated user.

        Raises:
            UserStoreError: If the account does not exist, or the change would
                leave the device with no admin.
        """
        self._ensure_loaded()
        key = normalize_username(username)

        with self._lock:
            user = self._users.get(key)
            if user is None:
                raise UserStoreError(f"No such account: {username}")
            if user.role is Role.ADMIN and role is not Role.ADMIN:
                self._assert_not_last_admin(key)
            user.role = role
            user.updated_at = utc_now()
            self._save()

        _LOGGER.info("Account '%s' is now %s", user.username, role)
        return user

    def delete_user(self, username: str) -> None:
        """Remove an account.

        Args:
            username: Account to remove.

        Raises:
            UserStoreError: If the account does not exist, or removing it
                would leave the device with no admin.
        """
        self._ensure_loaded()
        key = normalize_username(username)

        with self._lock:
            user = self._users.get(key)
            if user is None:
                raise UserStoreError(f"No such account: {username}")
            if user.role is Role.ADMIN:
                self._assert_not_last_admin(key)
            del self._users[key]
            self._save()

        _LOGGER.info("Deleted account '%s'", username)

    def _assert_not_last_admin(self, key: str) -> None:
        """Refuse an operation that would remove the final admin.

        Locking the owner out of their own device needs a reflash to undo, so
        the store will not do it even when asked directly.

        Args:
            key: Normalised username about to lose admin.

        Raises:
            UserStoreError: If this is the only admin account left.
        """
        other_admins = [
            name
            for name, user in self._users.items()
            if user.role is Role.ADMIN and name != key
        ]
        if not other_admins:
            raise UserStoreError(
                "Refusing to remove the last admin account — the device would "
                "become unmanageable. Create another admin first."
            )


# Hashed once at import so an unknown username costs the same as a known one.
_DUMMY_HASH = hash_password("boneio-nonexistent-account-placeholder")
