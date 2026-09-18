"""Take away the sudo rules nothing needs any more.

Four operations used to reach root through a rule that accepted an argument the
caller chose:

    mosquitto_passwd -b /etc/mosquitto/passwd <account> *
    systemctl reload mosquitto
    hostnamectl set-hostname *

The first is the one that mattered: the new broker password stood in the
process table, readable by every local account, for as long as the command ran.
All of them now go through ``boneio-system``, which takes a verb from a fixed
list, validates what it is given against the schema, and reads the password from
stdin.

``ip link set can0/can1 *`` deliberately stays. The CAN bring-up falls back to it
on a controller that has not installed that helper yet, and taking it away would
stop CAN on a device that has it working today. It goes once the installed base
has the helper.

This runs after 1.6.8, which installs the helper, so the rules are never removed
before their replacement exists.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.10.applied`` and
restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.10"
DESCRIPTION = "Remove the sudo rules replaced by the privileged helpers"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="sudoers/boneio",
            dst="/etc/sudoers.d/boneio",
            mode=0o440,
            owner="root",
            group="root",
            # A fragment sudo refuses to parse takes every privileged operation
            # with it, including the ones needed to put it back.
            validate_cmd="visudo -cf",
            validate="sudoers",
        ),
    ]
