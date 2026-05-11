"""Fix mosquitto_passwd sudoers rule for boneio user.

The baseline migration (v1.3.0) installed a sudoers rule that used ``-c -b``
flags for the ``boneio`` user.  The ``-c`` flag creates a *new* password file
(wiping all existing entries) — this was never intended. The WebUI endpoint
calls ``mosquitto_passwd -b`` (batch update) which did not match the ``-c -b``
sudoers rule, causing sudo to prompt for a password and fail.

This migration replaces the sudoers file with the corrected version where the
``boneio`` user entry uses ``-b`` only (same as ``homeassistant`` and ``mqtt``).
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.4.0"
DESCRIPTION = "Fix mosquitto_passwd sudoers rule: remove -c flag from boneio user entry"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        Single action to overwrite the sudoers file with the corrected version.
    """
    return [
        InstallFile(
            src="sudoers/boneio",
            dst="/etc/sudoers.d/boneio",
            mode=0o440,
            validate_cmd="visudo -cf",
        ),
    ]
