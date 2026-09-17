"""BoneIO 1.6.4 — throttle SSH logins the way the web login already is.

Deliverable 3 rate-limited ``/api/login`` and left SSH alone, so the finding
about excessive authentication attempts (F-06, CVE-2026-77057) is only half
closed: the panel counts attempts, ``sshd`` runs on Debian's defaults, and an
attacker on the LAN can keep guessing the shipped password for as long as they
care to.

A drop-in in ``/etc/ssh/sshd_config.d/`` cuts attempts per connection from six
to three, shortens the window to make them in, and stops root logging in over
SSH. None of that locks anyone out — both key and password authentication keep
working.

Two deliberate choices worth knowing about:

``validate_cmd`` runs ``sshd -t -f`` against the file before it is moved into
place. A config ``sshd`` refuses to parse is unrecoverable on a device reached
only over the network: the running daemon survives until the next restart, and
then there is no way back in without a serial console. The cost is that a
validation failure fails this migration, and a failed migration stops the ones
after it — so this is ordered last, behind the changes that cannot fail.

The unit is ``ssh``, not ``sshd``. Debian ships ``sshd.service`` as an alias,
and reloading an alias is not reliable across systemd versions.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction, SystemctlReload

VERSION = "1.6.4"
DESCRIPTION = "Limit SSH authentication attempts and disable root login (F-06)"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.6.4.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="sshd/10-boneio-hardening.conf",
            dst="/etc/ssh/sshd_config.d/10-boneio-hardening.conf",
            mode=0o644,
            owner="root",
            group="root",
            # Checked as a standalone config, which is what the helper hands
            # it: the file names no HostKey, so sshd falls back to the defaults
            # under /etc/ssh, which exist by first boot.
            validate_cmd="sshd -t -f",
            # Only when the file actually changed — the helper skips the write
            # when the hash already matches, and a reload then has no purpose.
            on_change=SystemctlReload(unit="ssh"),
        ),
    ]
