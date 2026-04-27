"""Fix OLED boot splash timing and stale messages.

Changes:
- oled_boot_splash.py: new ultra-fast boot splash script using raw smbus2
  (no luma/PIL), starts in <200ms vs ~9s for luma-based oled_msg.py
- oled_msg.py: added fast I2C clear to wipe stale display on soft-reboot
- boneio-oled-boot.service: switched to fast splash script, dropped
  After=local-fs.target for earlier start, added ConditionPathExists=/dev/i2c-2
- boneio.service: add ExecStartPre to show "is starting..." on OLED
  before app launches (prevents stale "has stopped" message on restart),
  add ExecStopPost to show stopped message, add After=boneio-oled-boot.service
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlDaemonReload,
)

VERSION = "1.3.0dev18"
DESCRIPTION = "Fast OLED boot splash and stale display fix"
REQUIRES_ROOT = True

_BONEIO_USER = "boneio"
_BONEIO_HOME = f"/home/{_BONEIO_USER}"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    template_vars = {
        "BONEIO_USER": _BONEIO_USER,
        "BONEIO_HOME": _BONEIO_HOME,
    }

    return [
        # New ultra-fast boot splash script (smbus2 only, no luma)
        InstallFile(
            src="usr-sbin/oled_boot_splash.py",
            dst="/usr/sbin/oled_boot_splash.py",
            mode=0o755,
        ),
        # Shell wrapper for boot splash (handles venv Python discovery)
        InstallFile(
            src="usr-sbin/oled_boot_splash.sh",
            dst="/usr/sbin/oled_boot_splash.sh",
            mode=0o755,
        ),
        # Updated oled_msg.py with fast I2C clear on startup
        InstallFile(
            src="usr-sbin/oled_msg.py",
            dst="/usr/sbin/oled_msg.py",
            mode=0o755,
        ),
        # Updated boot splash service — uses fast script, earlier deps
        InstallFile(
            src="systemd/boneio-oled-boot.service",
            dst="/etc/systemd/system/boneio-oled-boot.service",
            mode=0o644,
            on_change=SystemctlDaemonReload(),
        ),
        # Updated main service: ExecStartPre + ExecStopPost for OLED messages
        InstallFile(
            src="systemd/boneio.service",
            dst="/etc/systemd/system/boneio.service",
            mode=0o644,
            template_vars=template_vars,
            on_change=SystemctlDaemonReload(),
        ),
    ]
