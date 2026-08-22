"""BoneIO 1.5.12 — take the OLED splash off the boot critical path.

Two units spent measured time rendering text with Python and PIL while
everything else waited.

boneio-oled-boot.service — 4.54 s, ordered ``Before=sysinit.target``
    Everything downstream of sysinit (basic.target, mosquitto, boneIO) was
    pushed back by the full render time, to paint a splash screen.
    ``WantedBy=sysinit.target`` still starts it at the same early point; without
    the ordering, the render overlaps the ~45 s that follows instead of
    preceding it.

    ``Before=boneio.service`` is kept: boneIO writes to the same SH1106 over I2C
    through early_oled, and two writers on one bus garble the display.

boneio.service ExecStartPre — 2.96 s
    ``oled_msg.sh`` has a fast FIFO path, but the daemon serving it is not
    running yet at boot, so it fell back to spawning Python with PIL.

    Removing it loses no information: boneio-oled-boot already shows
    "OS is starting. / Please wait...", its ExecStop switches to
    "App is loading...", and early_oled then reports real progress
    ("Loading config...", "Importing modules...", "Initializing...").
    The removed line was near-duplicate text costing 2.96 s.

Measured before this change: boneio.service Starting @49.75 s, Started @52.71 s.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlDaemonReload,
)

VERSION = "1.5.12"
DESCRIPTION = "OLED splash off the critical path (~7.5s of boot time)"
REQUIRES_ROOT = True

_BONEIO_USER = "boneio"
_BONEIO_HOME = f"/home/{_BONEIO_USER}"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.12.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    template_vars = {
        "BONEIO_USER": _BONEIO_USER,
        "BONEIO_HOME": _BONEIO_HOME,
    }

    return [
        InstallFile(
            src="systemd/boneio-oled-boot.service",
            dst="/etc/systemd/system/boneio-oled-boot.service",
            mode=0o644,
        ),
        InstallFile(
            src="systemd/boneio.service",
            dst="/etc/systemd/system/boneio.service",
            mode=0o644,
            template_vars=template_vars,
            on_change=SystemctlDaemonReload(),
        ),
    ]
