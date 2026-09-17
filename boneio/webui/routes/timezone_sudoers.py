"""Reporting on the timedatectl sudoers rule.

Read-only. The rule that lets boneIO run ``timedatectl set-timezone`` and
``set-ntp`` is installed by migration 1.6.7, not from here — it used to be
created by an endpoint that accepted the operator's sudo password over HTTP,
and that password is shared across controllers.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

# Sudoers file path for timezone commands
SUDOERS_FILE = "/etc/sudoers.d/boneio-timedatectl"

#: The rule as it is actually shipped. Read from the migration asset rather
#: than repeated here: the asset is what lands on the device, and a second copy
#: in this module would drift from it silently — it already had, with "(ALL)"
#: here against the narrower "(root)" in the asset, which would have made the
#: check below report a mismatch on a correctly configured controller.
SUDOERS_ASSET = (
    Path(__file__).resolve().parents[2]
    / "migrations" / "assets" / "sudoers" / "boneio-timedatectl"
)


def get_sudoers_content(user: str | None = None) -> str:
    """The sudoers rules boneIO expects for timedatectl.

    Args:
        user: Ignored; kept so existing callers do not break. The rule is
            written for the service account, and taking the name from the
            environment meant the expected content depended on who happened to
            be logged in.

    Returns:
        The rule lines, comments stripped, as they appear in the shipped asset.
    """
    try:
        text = SUDOERS_ASSET.read_text(encoding="utf-8")
    except OSError:
        _LOGGER.warning("Cannot read %s; falling back to the built-in rule", SUDOERS_ASSET)
        text = (
            "boneio ALL=(root) NOPASSWD: /usr/bin/timedatectl set-timezone *\n"
            "boneio ALL=(root) NOPASSWD: /usr/bin/timedatectl set-ntp *\n"
        )
    rules = [
        line.rstrip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return "\n".join(rules) + "\n"


async def check_sudo_nopasswd_for_timedatectl() -> dict:
    """Check if sudo NOPASSWD is configured for timedatectl set-timezone/set-ntp.

    Uses 'sudo -n -l' to list allowed commands and verifies that
    timedatectl set-timezone and set-ntp are permitted without a password.

    Returns:
        Dictionary with:
            - needs_password: bool — True if NOPASSWD rule is missing
            - sudoers_file_exists: bool — True if /etc/sudoers.d/boneio-timedatectl exists
            - error: str | None — error message if check failed
    """
    result = {
        "needs_password": True,
        "sudoers_file_exists": os.path.exists(SUDOERS_FILE),
        "error": None,
    }

    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo", "-n", "-l",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)

        if proc.returncode != 0:
            stderr_str = stderr.decode().strip()
            if "password is required" in stderr_str or "a terminal is required" in stderr_str:
                result["needs_password"] = True
                result["error"] = "sudo requires a password to list allowed commands"
            else:
                result["error"] = stderr_str
            return result

        sudo_list = stdout.decode()

        has_set_timezone = any(
            "timedatectl set-timezone" in line
            for line in sudo_list.splitlines()
            if "NOPASSWD" in line
        )
        has_set_ntp = any(
            "timedatectl set-ntp" in line
            for line in sudo_list.splitlines()
            if "NOPASSWD" in line
        )

        if has_set_timezone and has_set_ntp:
            result["needs_password"] = False
        else:
            result["needs_password"] = True
            missing = []
            if not has_set_timezone:
                missing.append("timedatectl set-timezone")
            if not has_set_ntp:
                missing.append("timedatectl set-ntp")
            result["error"] = (
                f"No NOPASSWD rule found for: {', '.join(missing)}. "
                "Changing timezone/NTP settings will fail."
            )

    except TimeoutError:
        result["error"] = "sudo check timed out"
    except FileNotFoundError:
        result["error"] = "sudo command not found"
    except Exception as e:
        result["error"] = str(e)

    return result


# create_timedatectl_sudoers_file() is gone with the endpoint that called it.
# It took the operator's sudo password, validated the fragment with
# `sudo -S visudo` and installed it. The file now arrives through migration
# 1.6.7, over a channel that needs no password at all — see the module that
# replaced it for why an endpoint asking for that password was worth removing
# even though it never stored one.
