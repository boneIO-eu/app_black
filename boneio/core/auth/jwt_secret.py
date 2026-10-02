"""The secret the panel signs its login tokens with.

Kept in ``jwt_secret`` next to config.yaml so a token outlives a restart. Here
rather than in the web server so recovery mode signs with the same secret
without importing the web server, which pulls in the whole Manager: a token
issued in recovery keeps working once the controller is back, and the other
way round.

The secret belongs to one controller, and the file says which: its second
line is a hash of the machine-id it was drawn on. A file that names another
machine — or none — came from somewhere else, most likely an SD card image
built on a controller that had already run, and every device flashed from that
image would otherwise sign with the same key. Anyone holding the image could
then sign an administrator's token for all of them. Such a file is replaced
rather than trusted, which signs everybody out once.

Only the hash is stored: machine-id is meant to stay on the machine, and the
file needs no more than to recognise it.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

JWT_SECRET_FILENAME = "jwt_secret"

#: Where systemd keeps this installation's identity. Emptied when an image is
#: sealed and drawn afresh on the first boot, which is what makes it the thing
#: to bind to.
MACHINE_ID_PATH = Path("/etc/machine-id")

_BINDING_PREFIX = "machine:"


def _machine_binding(machine_id_path: Path) -> str | None:
    """The binding line for this machine, or None when it has no identity yet.

    None is not an error. On an image being built machine-id is empty on
    purpose; a secret drawn then stays unbound and is replaced on the first
    boot, once there is an identity to bind it to.

    Args:
        machine_id_path: The machine-id file.

    Returns:
        ``machine:<sha256 of machine-id>``, or None.
    """
    try:
        machine_id = machine_id_path.read_text().strip()
    except OSError:
        return None
    if not machine_id:
        return None
    digest = hashlib.sha256(f"boneio-jwt:{machine_id}".encode()).hexdigest()
    return f"{_BINDING_PREFIX}{digest}"


def _write_secret(path: Path, secret: str, binding: str | None) -> None:
    """Write the secret readable by its owner only, from the first byte.

    Created 0600 rather than chmod-ed afterwards, and swapped in with a rename,
    so there is never a moment when the key is on disk with looser permissions
    or half written.
    """
    content = secret + (f"\n{binding}" if binding else "") + "\n"
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.unlink()
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_or_create_jwt_secret(
    config_dir: str | os.PathLike[str],
    machine_id_path: Path = MACHINE_ID_PATH,
) -> str:
    """Read the token secret, creating it on first use.

    A stored secret is used only if it was drawn on this machine. One with no
    binding, or another machine's, is replaced — unless this machine has no
    identity to compare with, in which case it is kept as it is: replacing it
    then would sign everybody out on every start.

    Never raises: a secret that cannot be persisted is replaced by one that
    lives as long as the process, which logs everybody out on the next restart
    but does not keep the panel from starting.

    Args:
        config_dir: The directory config.yaml is in.
        machine_id_path: The machine-id file. A parameter for the tests.

    Returns:
        The secret.
    """
    jwt_secret_file = Path(config_dir) / JWT_SECRET_FILENAME
    binding = _machine_binding(machine_id_path)

    try:
        if jwt_secret_file.exists():
            lines = jwt_secret_file.read_text().split()
            stored = lines[0] if lines else ""
            stored_binding = lines[1] if len(lines) > 1 else None
            if stored and (binding is None or stored_binding == binding):
                return stored
            if stored:
                _LOGGER.warning(
                    "The token secret was not drawn on this controller; "
                    "replacing it. Everybody signed in has to sign in again."
                )

        jwt_secret = secrets.token_hex(32)  # 256-bit random secret
        _write_secret(jwt_secret_file, jwt_secret, binding)
    except Exception as e:
        # If we can't persist the secret, generate a temporary one
        _LOGGER.error(f"Failed to handle JWT secret file: {e}")
        jwt_secret = secrets.token_hex(32)
    return jwt_secret
