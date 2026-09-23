"""The secret the panel signs its login tokens with.

Kept in ``jwt_secret`` next to config.yaml so a token outlives a restart. Here
rather than in the web server so recovery mode signs with the same secret
without importing the web server, which pulls in the whole Manager: a token
issued in recovery keeps working once the controller is back, and the other
way round.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

JWT_SECRET_FILENAME = "jwt_secret"


def load_or_create_jwt_secret(config_dir: str | os.PathLike[str]) -> str:
    """Read the token secret, creating it on first use.

    Never raises: a secret that cannot be persisted is replaced by one that
    lives as long as the process, which logs everybody out on the next restart
    but does not keep the panel from starting.

    Args:
        config_dir: The directory config.yaml is in.

    Returns:
        The secret.
    """
    jwt_secret_file = Path(config_dir) / JWT_SECRET_FILENAME

    try:
        if jwt_secret_file.exists():
            # Read existing secret
            with open(jwt_secret_file) as f:
                jwt_secret = f.read().strip()
                if jwt_secret:  # Verify it's not empty
                    return jwt_secret

        # Generate new secret if file doesn't exist or is empty
        jwt_secret = secrets.token_hex(32)  # 256-bit random secret

        # Save the secret
        with open(jwt_secret_file, "w") as f:
            f.write(jwt_secret)

        # Secure the file permissions (read/write only for owner)
        os.chmod(jwt_secret_file, 0o600)

    except Exception as e:
        # If we can't persist the secret, generate a temporary one
        _LOGGER.error(f"Failed to handle JWT secret file: {e}")
        jwt_secret = secrets.token_hex(32)
    return jwt_secret
