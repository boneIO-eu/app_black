"""BoneIO system migration framework.

Provides versioned, idempotent OS-level migrations (systemd services,
config files, helper scripts) that are applied automatically on startup
when a new version of boneio is installed.
"""

from boneio.migrations.runner import MigrationRunner, MigrationStatus

__all__ = ["MigrationRunner", "MigrationStatus"]
