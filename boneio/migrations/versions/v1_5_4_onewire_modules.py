"""Enable 1-Wire kernel modules (ds2482 and w1-therm) for DS2482/DS2484 I2C bridges."""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.5.4"
DESCRIPTION = "Load ds2482 and w1-therm kernel modules for 1-Wire support"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions."""
    return [
        InstallFile(
            src="modules-load.d/onewire.conf",
            dst="/etc/modules-load.d/onewire.conf",
            mode=0o644,
            owner="root",
            group="root",
        ),
    ]
