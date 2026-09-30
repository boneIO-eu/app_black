"""The SSH login says what this controller is, and how fresh its system is.

Until now an SSH login showed the base image's text, before the password
prompt and again on every ``ssh host command``::

    BeagleBoard.org Debian Trixie Base Image 2026-05-19
    Support: https://bbb.io/debian

That date is when BeagleBoard built the image the flasher started from, not
the state of the system. A controller that has since taken every Debian point
release, a new kernel from the panel and a week of unattended security updates
still says May, and reads to the customer like a device shipped with a system
months out of date. The support link is BeagleBoard's, not ours.

Two parts, split by what is known when:

**Before the password prompt** - ``/etc/ssh/boneio-banner``, via a drop-in that
sets ``Banner``. Static text frozen into a signed plan, and shown to anybody who
connects to port 22, so it carries no date, no version and no password hint:
a date there would be stale after the next unattended upgrade, which is the
same trap 1.6.12 describes for the panel's port, and a password hint is wrong
on units upgraded from 1.5, which may still have the shipped one or their own.
Only the login name, which the old banner gave too.

The drop-in rather than an edit of ``/etc/issue.net``, which belongs to
``base-files``, and rather than another line in ``10-boneio-hardening.conf``,
which ``setup_boneio.sh`` also writes. sshd keeps the first value it reads and
Debian's ``sshd_config`` includes ``sshd_config.d`` before its own
``Banner /etc/issue.net``, so the drop-in wins without either file changing.

**After login** - ``/etc/update-motd.d/20-boneio``, computed at login: boneIO's
version and whether it runs, the panel's address, the Debian point release and
kernel, when dpkg last changed anything, and the base image line from
``/etc/dogtag``, labelled as such.

The address follows the rule the panel and Home Assistant already use
(``_preferred_url``): https on ``<hostname>.local`` through the proxy, on
``web.proxy_port`` or 8443, because the hostname survives a new DHCP lease and
Caddy's certificate names it. It is shown only when something really listens
on that port, and the panel's own http port only when the service listens on
it beyond loopback - with ``web.expose: proxy`` it does not. Both come from the
socket table at login, so they are right on the device that shows them; a port
in a static file could not be, which is why 1.6.12's console line has none.
That last one stays because support needs to know which flasher a unit came
from; it just no longer poses as the system's age.

The base images ship ``/etc/update-motd.d`` and the vendor's scripts in it
without execute bits, so the dynamic MOTD has been empty on every controller:
``/run/motd.dynamic`` is written on each login, zero bytes. pam_motd runs
``run-parts`` as root, which enters the directory regardless, and ``run-parts``
runs what is executable - so this script, at 0755, runs, and the vendor's stay
switched off. Their ``uname`` line is folded into ours.

The script runs as root on every session, so it reads the boneio account's
files without executing them; see its header. About 0.3 s on the board, most
of it one ``systemctl show``.

Order: the files that cannot fail first, the drop-in last - its ``sshd -t``
is the only step that can refuse, and a failed migration stops the ones after
it. The banner file exists before sshd is told to read it.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.28.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction, SystemctlReload

VERSION = "1.6.28"
DESCRIPTION = "Show boneIO's status on SSH login instead of the base image's date"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        # run-parts skips names with a dot, so no ".sh".
        InstallFile(
            src="motd/20-boneio",
            dst="/etc/update-motd.d/20-boneio",
            mode=0o755,
        ),
        InstallFile(
            src="sshd/boneio-banner",
            dst="/etc/ssh/boneio-banner",
            mode=0o644,
        ),
        InstallFile(
            src="sshd/20-boneio-banner.conf",
            dst="/etc/ssh/sshd_config.d/20-boneio-banner.conf",
            mode=0o644,
            validate="sshd",
            # sshd reads Banner per connection from its config, which a reload
            # re-reads; the unit is ssh, not the sshd alias (see 1.6.4).
            on_change=SystemctlReload(unit="ssh"),
        ),
    ]
