"""Warnings and errors reach the serial console without a login.

A controller that does not start is diagnosed at the cabinet, over the debug
UART. Until now that showed the kernel and nothing else: the boneio account is
locked by default, so the serial getty cannot be used to read the journal, and
without the network there is no other way in. A journald drop-in forwards
every entry at warning level or worse to ``/dev/ttyS0`` as it is logged,
early boot included, so failing units and systemd's own complaints are on the
wire for anyone with a USB-serial adapter. No extra process: journald does
the forwarding itself.

Only what journald files at warning or worse is forwarded. boneIO's own lines
do not qualify yet: it writes plain text to stdout, and systemd records that at
the unit's default level, info, whatever the text says. systemd's line that
``boneio.service`` failed, and the restart loop, do reach the console.

On what this exposes: the UART header needs the enclosure open, and whoever
has that has the SD card and eMMC, with the whole journal and configuration
on them. Secrets are masked where the panel shows the journal
(``/api/logs``), not in the journal itself, so the console carries the same
lines ``journalctl`` does. This is part of adapting the 1.6 series to the CRA:
a device that fails should be diagnosable without weakening its login.

Drop-in rather than another edit of ``journald.conf``, which 1.5.7 and 1.5.14
install whole: a later change to either file does not undo the other.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.25.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlRestart,
)

VERSION = "1.6.25"
DESCRIPTION = "Forward journal warnings and errors to the serial console"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        # The helper creates journald.conf.d; Debian does not ship it.
        InstallFile(
            src="journald/boneio-console.conf",
            dst="/etc/systemd/journald.conf.d/boneio-console.conf",
            mode=0o644,
            on_change=SystemctlRestart(unit="systemd-journald"),
        ),
    ]
