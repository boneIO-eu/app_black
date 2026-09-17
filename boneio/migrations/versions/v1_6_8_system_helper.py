"""Replace the last broad sudo rules with a named-operation helper.

Three features still reached root the two worst ways available. CAN interface
setup and the device-tree overlay change asked the operator for their system
password over HTTP — the same password on every controller that shipped, so an
endpoint collecting it is a way to intercept it. And the rules behind them were
wildcards: ``ip link set can0 *`` and, for the overlay, a ``sed -i`` expression
composed in the application and executed as root on /boot/uEnv.txt.

``boneio-system`` takes their place with a closed vocabulary — an interface from
a list of two, a bitrate from a list of nine, an overlay from the four this
board ships, a hostname matched against DNS label rules. The uEnv.txt edit
happens inside the helper against a compiled pattern instead of root running a
pattern the application wrote.

This is also what has to exist before the ``docker`` and ``admin`` group
memberships can go (the next and last step): nothing may still depend on them.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.8.applied`` and
restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.8"
DESCRIPTION = "Install boneio-system for CAN, overlay and hostname operations"
REQUIRES_ROOT = True

TRUSTED_DIR = "/usr/lib/boneio/trusted"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    The helper goes in before the sudoers fragment that names it, so an
    interrupted run never leaves a rule pointing at a binary that is not there.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        # Pristine copy first: boneio-helpers-heal.service restores from here,
        # and recovery must never depend on the application.
        InstallFile(
            src="helpers/boneio-system",
            dst=f"{TRUSTED_DIR}/boneio-system",
            mode=0o755,
            owner="root",
            group="root",
        ),
        InstallFile(
            src="helpers/boneio-system",
            dst="/usr/sbin/boneio-system",
            mode=0o755,
            owner="root",
            group="root",
            validate_cmd="python3 -m py_compile",
            validate="python",
        ),
        # The fragment now names three helpers. install_file rewrites it only
        # when the content differs, so a device that applied 1.6.5 gets the
        # third line added and nothing else disturbed.
        InstallFile(
            src="sudoers/boneio-helpers",
            dst="/etc/sudoers.d/boneio-helpers",
            mode=0o440,
            owner="root",
            group="root",
            validate_cmd="visudo -cf",
            validate="sudoers",
        ),
    ]
