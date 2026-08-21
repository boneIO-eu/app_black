"""Install kernel postinst hook to copy boneIO overlays to new kernel DTB dirs.

Fixes: overlays missing after kernel upgrade (Debian 13.2 -> 13.3 etc.)
The hook is triggered by dpkg after installing a new kernel package and
copies all BONEIO-BLACK-PINS*.dtbo files from an existing kernel overlay
directory to the new one.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.5.5"
DESCRIPTION = "Kernel postinst hook for overlay DTB propagation across kernel upgrades"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of actions: installs the kernel postinst hook.
    """
    return [
        InstallFile(
            src="kernel/postinst-boneio-overlay",
            dst="/etc/kernel/postinst.d/zz-boneio-overlay",
            mode=0o755,
            owner="root",
            group="root",
        ),
    ]
