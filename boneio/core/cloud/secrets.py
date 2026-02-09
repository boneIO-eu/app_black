"""
Cloud API secrets for boneIO Black.

The MASTER_SECRET is resolved in this order:
1. Environment variable BONEIO_MASTER_SECRET (already set in shell/systemd)
2. BONEIO_MASTER_SECRET from .env file in working directory or /home/boneio/
3. Build-time injected value (replaced by GitHub Actions during PyPI build)

For local development, set BONEIO_MASTER_SECRET in your .env file or shell.
DO NOT commit real secrets to this file.
"""

import os
from pathlib import Path

# This placeholder is replaced by GitHub Actions during build.
# See .github/workflows/publish-to-pypi.yaml
_BUILD_SECRET = "__BONEIO_MASTER_SECRET_PLACEHOLDER__"


def _load_env_secret() -> str:
    """Load BONEIO_MASTER_SECRET from environment or .env file.

    Checks environment first, then looks for .env file in common locations.

    Returns:
        The master secret string (may be placeholder if not configured).
    """
    # 1. Already in environment?
    env_val = os.environ.get("BONEIO_MASTER_SECRET")
    if env_val:
        return env_val

    # 2. Try .env files
    env_paths = [
        Path.cwd() / ".env",
        Path.home() / ".env",
    ]
    for env_path in env_paths:
        if env_path.is_file():
            try:
                for line in env_path.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    if key.strip() == "BONEIO_MASTER_SECRET":
                        return value.strip().strip("'\"")
            except OSError:
                continue

    # 3. Fallback to build-time placeholder
    return _BUILD_SECRET


MASTER_SECRET = _load_env_secret()
