"""Show the device's address on the serial console login prompt.

A controller in a cabinet is reached over the network, and the first thing
anybody attaching a serial cable wants to know is which address it ended up
with. Until now the console said only the hostname, so the answer meant logging
in and running ``ip addr`` — on a device that, after the 1.6 hardening, an
installer may not have an account on.

``agetty`` expands the escape when it draws the prompt, not when it starts, so
the address is current rather than whatever DHCP had managed by the time the
getty came up. If the lease had not arrived yet the field is simply blank, and
pressing Enter redraws the prompt with the address filled in — which is what
the hint on the line is for.

The interface is named explicitly. A bare ``\\4`` means "the first fully
configured interface", and this device has ``docker0`` and a compose bridge
holding 172.17/172.18 addresses that are of no use to anybody standing at the
cabinet.

It goes in ``/etc/issue.d`` rather than into ``/etc/issue``, which belongs to
``base-files`` and already carries text the board vendor put there.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.12.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.12"
DESCRIPTION = "Show the IP address on the serial console"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="issue.d/10-boneio.issue",
            dst="/etc/issue.d/10-boneio.issue",
            mode=0o644,
            owner="root",
            group="root",
        )
    ]
