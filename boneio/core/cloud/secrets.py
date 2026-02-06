"""
Cloud API secrets for boneIO Black.

The MASTER_SECRET is resolved in this order:
1. Environment variable BONEIO_MASTER_SECRET (for local development)
2. Build-time injected value (replaced by GitHub Actions during PyPI build)

For local development, set BONEIO_MASTER_SECRET in your .env file or shell.
DO NOT commit real secrets to this file.
"""

import os

# This placeholder is replaced by GitHub Actions during build.
# See .github/workflows/publish-to-pypi.yaml
_BUILD_SECRET = "__BONEIO_MASTER_SECRET_PLACEHOLDER__"

MASTER_SECRET = os.environ.get("BONEIO_MASTER_SECRET", _BUILD_SECRET)
