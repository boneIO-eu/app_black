"""Automatic security updates, on by default; recover dpkg after a power loss.

Two things a controller in a cabinet needs from the operating system without
anyone logging in.

**Security fixes arrive by themselves.** unattended-upgrades is on the image
but was switched off, along with the apt timers, to keep boot fast. It is back,
restricted by ``52boneio-unattended`` to the Debian-Security archive alone —
Debian's default also takes point-release changes from the main archive — and
never rebooting: the panel says when a restart is due. The BeagleBoard kernel
comes from the rcn-ee archive, so it never arrives this way; a kernel changes
what the next boot loads and stays with the panel's system update, which checks
the boneIO overlay first. Nothing is removed unattended.

The timers get the catch-up drop-in from 1.5.11, so a controller that is
power-cycled rather than left running does not start apt at every boot, and a
low CPU and IO weight so apt never competes with boneIO. The owner can switch
the updates off in the panel (``boneio-system os-autoupdate-set``), which is
why they are on by default: off is the choice to make, not the default to
find out about.

**An interrupted upgrade finishes itself.** dpkg cut short by a power loss
refuses every later apt run — the panel's and the automatic ones — until
``dpkg --configure -a`` is typed over SSH. ``boneio-dpkg-recover.service`` does
it at boot, and only when dpkg's journal or status says it was interrupted, so
a healthy boot pays nothing.

boneio-system is reinstalled for the switch and for the update state that now
reports it. Trusted copy first, as in 1.6.17.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.22.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    AptInstall,
    InstallFile,
    MigrationAction,
    SystemctlDaemonReload,
    SystemctlEnable,
    SystemctlRestart,
)

VERSION = "1.6.22"
DESCRIPTION = "Automatic security updates and dpkg recovery after a power loss"
REQUIRES_ROOT = True

_TRUSTED_DIR = "/usr/lib/boneio/trusted"
_TIMERS = ("apt-daily.timer", "apt-daily-upgrade.timer")
_SERVICES = ("apt-daily.service", "apt-daily-upgrade.service")


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    actions: list[MigrationAction] = [
        AptInstall(packages=["unattended-upgrades"], optional=True),
    ]
    for dst in (f"{_TRUSTED_DIR}/boneio-system", "/usr/sbin/boneio-system"):
        actions.append(
            InstallFile(
                src="helpers/boneio-system", dst=dst, mode=0o755,
                owner="root", group="root", validate="python",
            )
        )
    for name in ("52boneio-unattended", "52boneio-periodic"):
        actions.append(
            InstallFile(src=f"apt/{name}", dst=f"/etc/apt/apt.conf.d/{name}", mode=0o644)
        )
    for timer in _TIMERS:
        actions.append(
            InstallFile(
                src="systemd/dropins/timer-no-persistent.conf",
                dst=f"/etc/systemd/system/{timer}.d/50-boneio-no-catchup.conf",
                mode=0o644,
            )
        )
    for service in _SERVICES:
        actions.append(
            InstallFile(
                src="systemd/dropins/apt-daily-priority.conf",
                dst=f"/etc/systemd/system/{service}.d/50-boneio-priority.conf",
                mode=0o644,
            )
        )
    actions.append(
        InstallFile(
            src="systemd/boneio-dpkg-recover.service",
            dst="/etc/systemd/system/boneio-dpkg-recover.service",
            mode=0o644,
        )
    )
    actions.append(SystemctlDaemonReload())
    actions.append(SystemctlEnable(unit="boneio-dpkg-recover.service"))
    for timer in _TIMERS:
        actions.append(SystemctlEnable(unit=timer))
        # enable alone would leave the timer stopped until the next boot.
        actions.append(SystemctlRestart(unit=timer))
    return actions
