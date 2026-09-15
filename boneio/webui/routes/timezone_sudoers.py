"""Timezone/timedatectl sudoers management for boneIO.

Provides functions to check and fix sudoers configuration
for timezone / NTP management commands (timedatectl set-timezone, set-ntp).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import tempfile

_LOGGER = logging.getLogger(__name__)

# Sudoers file path for timezone commands
SUDOERS_FILE = "/etc/sudoers.d/boneio-timedatectl"

# Expected sudoers content template
# {user} will be replaced with the current system user
SUDOERS_TEMPLATE = """{user} ALL=(ALL) NOPASSWD: /usr/bin/timedatectl set-timezone *
{user} ALL=(ALL) NOPASSWD: /usr/bin/timedatectl set-ntp *
"""


def get_sudoers_content(user: str | None = None) -> str:
    """Generate expected sudoers file content for timedatectl.

    Args:
        user: System user name. Defaults to current user or 'boneio'.

    Returns:
        Sudoers file content string.
    """
    if user is None:
        user = os.environ.get("USER", "boneio")
    return SUDOERS_TEMPLATE.format(user=user)


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


async def create_timedatectl_sudoers_file(password: str) -> dict:
    """Create /etc/sudoers.d/boneio-timedatectl with NOPASSWD rules.

    Uses sudo with the provided password to write the sudoers file.

    Args:
        password: User's sudo password.

    Returns:
        Dictionary with status and message.
    """
    user = os.environ.get("USER", "boneio")
    content = get_sudoers_content(user)

    tmp_path = None
    try:
        # mkstemp, not a name built from the pid: it opens with O_EXCL at mode
        # 0600 under a name nobody can guess. The old path was predictable, so
        # another local account could pre-create it as a symlink and have this
        # write through it, or swap the contents between validation and
        # install. Owned by us at 0600 inside a sticky /tmp, neither is
        # possible any more.
        fd, tmp_path = tempfile.mkstemp(
            prefix="boneio-timedatectl-sudoers-", suffix=".tmp"
        )
        with os.fdopen(fd, "w") as handle:
            handle.write(content)

        # Validate the sudoers file before installing
        validate_cmd = ["sudo", "-S", "visudo", "-c", "-f", tmp_path]
        proc = await asyncio.create_subprocess_exec(
            *validate_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=(password + "\n").encode()),
            timeout=10,
        )

        if proc.returncode != 0:
            stderr_str = stderr.decode().strip()
            if "incorrect password" in stderr_str.lower() or "sorry" in stderr_str.lower():
                return {"status": "error", "message": "Authentication failed.", "_auth_failed": True}
            return {"status": "error", "message": f"Sudoers validation failed: {stderr_str}"}

        # install, not cp followed by chmod: it places the file with its final
        # owner and mode in one step. The old sequence left the file in
        # /etc/sudoers.d readable-and-writable for the moment between the two,
        # and left it that way for good if the chmod failed — a mode sudo
        # refuses to honour, so the rule would silently not apply.
        install_cmd = [
            "sudo",
            "-S",
            "install",
            "-m",
            "0440",
            "-o",
            "root",
            "-g",
            "root",
            tmp_path,
            SUDOERS_FILE,
        ]
        proc = await asyncio.create_subprocess_exec(
            *install_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(
            proc.communicate(input=(password + "\n").encode()),
            timeout=10,
        )

        if proc.returncode != 0:
            stderr_str = stderr.decode().strip()
            if "incorrect password" in stderr_str.lower() or "sorry" in stderr_str.lower():
                return {"status": "error", "message": "Authentication failed.", "_auth_failed": True}
            return {"status": "error", "message": f"Failed to install sudoers file: {stderr_str}"}

        _LOGGER.info("Successfully created sudoers file for timedatectl: %s", SUDOERS_FILE)
        return {
            "status": "success",
            "message": f"Sudoers file created at {SUDOERS_FILE}",
            "content": content,
        }

    except TimeoutError:
        return {"status": "error", "message": "sudo command timed out"}
    except Exception as e:
        _LOGGER.error("Failed to create timedatectl sudoers file: %s", e)
        return {"status": "error", "message": str(e)}
    finally:
        # One place, so no error path can leave the file behind — it holds the
        # sudoers rule we are about to install and should not linger in /tmp.
        if tmp_path:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
