"""Timezone/timedatectl sudoers management for boneIO.

Provides functions to check and fix sudoers configuration
for timezone / NTP management commands (timedatectl set-timezone, set-ntp).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os

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

    try:
        # Write content to a temp file first, then move it with sudo
        tmp_path = f"/tmp/boneio-timedatectl-sudoers-{os.getpid()}"

        with open(tmp_path, "w") as f:
            f.write(content)

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
            os.unlink(tmp_path)
            if "incorrect password" in stderr_str.lower() or "sorry" in stderr_str.lower():
                return {"status": "error", "message": "Authentication failed.", "_auth_failed": True}
            return {"status": "error", "message": f"Sudoers validation failed: {stderr_str}"}

        # Copy the validated file to /etc/sudoers.d/ and set correct permissions
        install_cmd = ["sudo", "-S", "cp", tmp_path, SUDOERS_FILE]
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
            os.unlink(tmp_path)
            if "incorrect password" in stderr_str.lower() or "sorry" in stderr_str.lower():
                return {"status": "error", "message": "Authentication failed.", "_auth_failed": True}
            return {"status": "error", "message": f"Failed to install sudoers file: {stderr_str}"}

        # Set correct permissions (must be 0440)
        chmod_cmd = ["sudo", "-S", "chmod", "0440", SUDOERS_FILE]
        proc = await asyncio.create_subprocess_exec(
            *chmod_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(
            proc.communicate(input=(password + "\n").encode()),
            timeout=10,
        )

        # Clean up temp file
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)

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
