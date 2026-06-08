"""Fix OLED FIFO permission denied error.

- oled_msg.py: set FIFO permissions to 0o666 after mkfifo so all users
  (boneio, root) can write to it
- oled_msg.sh: wrap FIFO write in subshell so bash file-open errors
  are properly suppressed by 2>/dev/null
"""
from __future__ import annotations

from boneio.migrations.actions import InstallFile

VERSION = "1.5.0"
DESCRIPTION = "Fix OLED FIFO permission denied (oled_msg.py chmod + oled_msg.sh subshell)"
REQUIRES_ROOT = True


def plan() -> list:
    """Return declarative list of actions."""
    return [
        InstallFile(
            src="usr-sbin/oled_msg.py",
            dst="/usr/sbin/oled_msg.py",
            mode=0o755,
            owner="root",
            group="root",
        ),
        InstallFile(
            src="usr-sbin/oled_msg.sh",
            dst="/usr/sbin/oled_msg.sh",
            mode=0o755,
            owner="root",
            group="root",
        ),
    ]
