"""Configuration migration system for boneIO.

Migrations are versioned and executed once per config file.
The config_version field in the boneio section tracks which
migrations have already been applied.

Each migration module registers itself via the @register_migration decorator.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

# Current schema version — bump this when adding new migrations
CURRENT_SCHEMA_VERSION = 4

# Minimum app version that introduced each schema version.
# Used by the WebUI to warn before rolling back to an incompatible version.
SCHEMA_VERSION_APP_MAP: dict[int, str] = {
    0: "1.0.0",       # original schema
    1: "1.2.0dev1",   # proxy_port rename
    2: "1.3.0dev1",   # transition timeperiod
    3: "1.3.0dev7",   # irrigation section
    4: "1.5.0dev13",  # WLED effects/palettes → JSON cache
}


@dataclass
class Migration:
    """A single config migration step.

    Attributes:
        version: Target schema version after this migration.
        name: Human-readable description.
        migrate_dict: Transforms the raw config dict in memory.
        migrate_file: Optional — persists changes directly in the YAML file.
    """

    version: int
    name: str
    migrate_dict: Callable[[dict], dict]
    migrate_file: Callable[[str], None] | None = None


# Global ordered registry of migrations
_MIGRATIONS: list[Migration] = []


def register_migration(
    version: int,
    name: str,
    migrate_file: Callable[[str], None] | None = None,
) -> Callable:
    """Decorator to register a dict migration function.

    Args:
        version: Target schema version after this migration.
        name: Human-readable description.
        migrate_file: Optional file-level persistence function.

    Returns:
        Decorator that registers the function and returns it unchanged.
    """

    def decorator(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
        _MIGRATIONS.append(
            Migration(
                version=version,
                name=name,
                migrate_dict=fn,
                migrate_file=migrate_file,
            )
        )
        # Keep sorted by version
        _MIGRATIONS.sort(key=lambda m: m.version)
        return fn

    return decorator


def get_config_version(doc: dict) -> int:
    """Read config_version from the boneio section (default 0).

    Args:
        doc: Raw config dict.

    Returns:
        Current config version number.
    """
    boneio = doc.get("boneio")
    if isinstance(boneio, dict):
        return boneio.get("config_version", 0)
    return 0


def run_migrations(
    doc: dict,
    from_version: int | None = None,
    config_file: str | None = None,
) -> tuple[dict, int]:
    """Run all pending migrations on a config dict.

    Args:
        doc: Raw config dict (will be mutated in place).
        from_version: Override starting version (default: read from doc).
        config_file: If provided, also persist file-level migrations
                     and update config_version in the file.

    Returns:
        Tuple of (migrated dict, new config_version).
    """
    if from_version is None:
        from_version = get_config_version(doc)

    if from_version >= CURRENT_SCHEMA_VERSION:
        return doc, from_version

    applied: list[str] = []

    for migration in _MIGRATIONS:
        if migration.version <= from_version:
            continue
        if migration.version > CURRENT_SCHEMA_VERSION:
            break

        _LOGGER.info(
            "Running migration v%d: %s", migration.version, migration.name
        )
        doc = migration.migrate_dict(doc)
        applied.append(f"v{migration.version}: {migration.name}")

        # Persist file-level changes
        if config_file and migration.migrate_file:
            try:
                migration.migrate_file(config_file)
            except Exception as e:
                _LOGGER.error(
                    "Failed to persist migration v%d to file: %s",
                    migration.version,
                    e,
                )

    new_version = CURRENT_SCHEMA_VERSION

    if applied:
        _LOGGER.info("Migrations applied: %s", ", ".join(applied))

        # Persist config_version to file
        if config_file:
            try:
                _persist_config_version(config_file, new_version)
            except Exception as e:
                _LOGGER.error("Failed to persist config_version: %s", e)

    # Update in-memory dict
    if "boneio" not in doc or not isinstance(doc.get("boneio"), dict):
        doc["boneio"] = {}
    doc["boneio"]["config_version"] = new_version

    return doc, new_version


def _persist_config_version(config_file: str, version: int) -> None:
    """Write config_version into the boneio section of the YAML file.

    Handles three cases:
    - config_version already exists → update value
    - boneio section exists but no config_version → insert after 'boneio:'
    - no boneio section → skip (shouldn't happen in practice)

    Args:
        config_file: Path to the YAML config file.
        version: New config_version value to write.
    """
    with open(config_file, encoding="utf-8") as f:
        lines = f.readlines()

    updated_lines: list[str] = []
    version_written = False
    in_boneio = False
    boneio_indent = -1
    config_version_re = re.compile(r"^(\s*)config_version:\s*\d+")

    for i, line in enumerate(lines):
        stripped = line.rstrip()

        # Check if we're entering the boneio section
        if stripped == "boneio:" or stripped.startswith("boneio:"):
            in_boneio = True
            boneio_indent = len(line) - len(line.lstrip())
            updated_lines.append(line)
            continue

        if in_boneio and not version_written:
            line_indent = len(line) - len(line.lstrip())

            # Existing config_version line — replace it
            if config_version_re.match(line):
                indent = " " * (boneio_indent + 2)
                updated_lines.append(f"{indent}config_version: {version}\n")
                version_written = True
                continue

            # Left the boneio section (non-empty line at same or lower indent)
            if stripped and line_indent <= boneio_indent and i > 0:
                # Insert config_version before leaving
                indent = " " * (boneio_indent + 2)
                updated_lines.append(f"{indent}config_version: {version}\n")
                version_written = True
                in_boneio = False

        updated_lines.append(line)

    # If boneio was the last section and we haven't written yet
    if in_boneio and not version_written:
        indent = " " * (boneio_indent + 2)
        updated_lines.append(f"{indent}config_version: {version}\n")

    with open(config_file, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)

    _LOGGER.info("Persisted config_version: %d to %s", version, config_file)


# Import migration modules to trigger registration
from boneio.core.config.migrations import (
    v1_proxy_port,  # noqa: E402, F401
    v2_transition,  # noqa: E402, F401
    v4_wled_cache,  # noqa: E402, F401
)
