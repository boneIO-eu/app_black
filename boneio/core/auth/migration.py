"""One-way migration of pre-1.6 ``web.auth`` credentials into ``users.json``.

Up to 1.5.x a device had a single account written in plain text in
``config.yaml``::

    web:
      auth:
        username: pawel
        password: sekret          # or: !secret web_password

From 1.6 accounts live in ``users.json`` as scrypt hashes. This module moves an
existing pair across on first start so an upgrade never costs the owner their
login, and reports what happened so the caller can tell the user to delete the
now-redundant block.

The migration never touches ``config.yaml``. Rewriting a user's hand-maintained
YAML — comments, anchors, ``!secret`` tags and all — to strip four lines is a
poor trade against telling them to delete it themselves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from boneio.core.auth.models import Role
from boneio.core.auth.store import UserStore, UserStoreError

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MigrationResult:
    """Outcome of a legacy credential migration."""

    migrated: bool
    username: str | None = None
    reason: str = ""
    used_secret_file: bool = False

    def __bool__(self) -> bool:
        """True when an account was actually created."""
        return self.migrated


def migrate_legacy_auth(
    store: UserStore,
    legacy_auth: dict | None,
    *,
    secrets_values: set[str] | None = None,
) -> MigrationResult:
    """Create an admin account from a pre-1.6 ``web.auth`` block.

    Does nothing when the device already has an admin, so this is safe to call
    on every start. A legacy password that is shorter than the current policy
    is still migrated — it is what already guards the device, and refusing it
    here would turn an upgrade into a lockout.

    Args:
        store: Destination account store.
        legacy_auth: The ``web.auth`` mapping from config.yaml, already parsed
            (so a ``!secret`` reference arrives resolved).
        secrets_values: Values defined in ``secrets.yaml``, used only to notice
            that the password came from there and mention it in the log.

    Returns:
        What happened, for the caller to log or surface in the UI.
    """
    if store.is_provisioned():
        return MigrationResult(False, reason="already_provisioned")

    if not isinstance(legacy_auth, dict) or not legacy_auth:
        return MigrationResult(False, reason="no_legacy_auth")

    username = str(legacy_auth.get("username") or "").strip()
    password = str(legacy_auth.get("password") or "")

    if not username or not password:
        _LOGGER.warning(
            "web.auth in config.yaml is incomplete (username and password are "
            "both required) — starting the first-run wizard instead."
        )
        return MigrationResult(False, reason="incomplete_legacy_auth")

    from_secret = bool(secrets_values) and password in secrets_values

    try:
        store.add_user(username, password, Role.ADMIN, enforce_policy=False)
    except UserStoreError as err:
        # A name the new store cannot represent (a slash, a quote) is not worth
        # mangling into something the owner did not choose. Leave the device
        # unprovisioned so the wizard runs and they pick a name deliberately.
        _LOGGER.error(
            "Could not migrate the account from web.auth: %s. "
            "The first-run wizard will ask you to create an admin account.",
            err,
        )
        return MigrationResult(False, reason=f"invalid_legacy_auth: {err}")

    _LOGGER.warning(
        "Migrated the web.auth account '%s' from config.yaml into %s as a "
        "hashed admin account. Please DELETE the 'web.auth' block from "
        "config.yaml — it is no longer read, and it still holds your password "
        "in plain text.%s",
        username,
        store.path,
        (
            " The password came from secrets.yaml; you can remove that entry too."
            if from_secret
            else ""
        ),
    )

    return MigrationResult(
        True, username=username, reason="migrated", used_secret_file=from_secret
    )
