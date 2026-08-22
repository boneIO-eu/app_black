"""BoneIO 1.5.8 — stop loading desktop AppArmor profiles at boot.

Debian's ``apparmor`` package ships ~106 profiles in /etc/apparmor.d. On this
controller they were, in full: 1password, balena-etcher, brave, buildah,
chrome, chromium, code, Discord, element-desktop, epiphany, evolution, firefox,
flatpak, geary, github-desktop, MongoDB_Compass, msedge, nautilus, obsidian,
opera, plasmashell, QtWebEngineProcess, qutebrowser, signal-desktop, slack,
steam, transmission, vivaldi-bin, Xorg, the whole sbuild-* and lxc-* families,
and so on.

apparmor.service loaded all 111 of them on every boot of a headless industrial
controller. Measured: 11.4 s, sitting on the critical path ahead of
networking.service.

Compiled policy is cached in /var/cache/apparmor (202 files, 9.1 MB), so the
cost is reading that from SD plus 111 kernel profile loads on a 1 GHz
single-core AM335x.

Measured effect of the keep-list below, apparmor_parser --replace with warm
cache, three runs each:

    before:  2.59 s / 2.17 s / 2.31 s   (111 profiles)
    after:   1.03 s / 0.83 s / 0.82 s   (13 profiles)

Roughly -64%. The boot-time figure is larger because the page cache is cold
there.

The keep-list is deliberately conservative — PAM's unix-chkpwd, the DHCP
client, systemd-coredump, and the container runtime bits Docker may reach for.
Container confinement itself is unaffected: dockerd generates the
``docker-default`` profile at runtime rather than loading it from
/etc/apparmor.d.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    DisableApparmorProfiles,
    MigrationAction,
)

VERSION = "1.5.8"
DESCRIPTION = "Disable desktop AppArmor profiles (11.4s of boot time)"
REQUIRES_ROOT = True

# Everything not listed here gets a symlink in /etc/apparmor.d/disable/.
_KEEP = [
    "unix-chkpwd",         # PAM password verification (ssh, sudo, login)
    "usr.sbin.dhclient",   # DHCP client
    "systemd-coredump",
    "runc",                # container runtime used by docker.io
    "crun",
    "rootlesskit",
    "slirp4netns",
    "unprivileged_userns",
    "userbindmount",
    "busybox",
    "toybox",
    "lsb_release",
    "nvidia_modprobe",
]


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.8.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        DisableApparmorProfiles(keep=_KEEP),
    ]
