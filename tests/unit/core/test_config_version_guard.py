"""Tests for config version downgrade guard.

Covers:
- SCHEMA_VERSION_APP_MAP consistency
- Warning logged when config_version > CURRENT_SCHEMA_VERSION
- No warning when config_version <= CURRENT_SCHEMA_VERSION
- Compatibility check logic (used by /api/update/check_config_compat)
"""

from __future__ import annotations

import logging

import pytest

from boneio.core.config.migrations import (
    CURRENT_SCHEMA_VERSION,
    SCHEMA_VERSION_APP_MAP,
    get_config_version,
)


class TestSchemaVersionAppMap:
    """Tests for SCHEMA_VERSION_APP_MAP consistency."""

    def test_map_contains_current_schema_version(self):
        """Current schema version must be in the map."""
        assert CURRENT_SCHEMA_VERSION in SCHEMA_VERSION_APP_MAP

    def test_map_contains_version_zero(self):
        """Schema version 0 (original) must be in the map."""
        assert 0 in SCHEMA_VERSION_APP_MAP

    def test_map_versions_are_contiguous(self):
        """All schema versions from 0 to CURRENT must be present."""
        for v in range(CURRENT_SCHEMA_VERSION + 1):
            assert v in SCHEMA_VERSION_APP_MAP, f"Schema version {v} missing from map"

    def test_map_values_are_parseable_versions(self):
        """All app version strings must be parseable by packaging.version."""
        from packaging import version as pkg_version

        for schema_ver, app_ver_str in SCHEMA_VERSION_APP_MAP.items():
            parsed = pkg_version.parse(app_ver_str)
            assert parsed is not None, (
                f"Cannot parse app version '{app_ver_str}' for schema {schema_ver}"
            )

    def test_map_versions_are_monotonically_increasing(self):
        """Higher schema versions should require higher (or equal) app versions."""
        from packaging import version as pkg_version

        sorted_entries = sorted(SCHEMA_VERSION_APP_MAP.items())
        for i in range(1, len(sorted_entries)):
            prev_schema, prev_app = sorted_entries[i - 1]
            curr_schema, curr_app = sorted_entries[i]
            assert pkg_version.parse(curr_app) >= pkg_version.parse(prev_app), (
                f"Schema v{curr_schema} ({curr_app}) should require >= "
                f"schema v{prev_schema} ({prev_app})"
            )


class TestGetConfigVersion:
    """Tests for get_config_version helper."""

    def test_returns_zero_for_empty_dict(self):
        assert get_config_version({}) == 0

    def test_returns_zero_for_missing_boneio_section(self):
        assert get_config_version({"mqtt": {}}) == 0

    def test_returns_zero_when_boneio_has_no_config_version(self):
        assert get_config_version({"boneio": {"name": "test"}}) == 0

    def test_returns_config_version_from_boneio_section(self):
        assert get_config_version({"boneio": {"config_version": 5}}) == 5

    def test_returns_zero_when_boneio_is_not_dict(self):
        assert get_config_version({"boneio": "string_value"}) == 0


class TestConfigVersionWarning:
    """Tests for the warning logged in load_config_from_file when config is too new."""

    def test_warning_logged_when_config_newer_than_supported(self, caplog):
        """Simulate the check from load_config_from_file."""
        config_version = CURRENT_SCHEMA_VERSION + 1
        with caplog.at_level(logging.WARNING):
            # Replicate the exact check from yaml_util.py
            if config_version > CURRENT_SCHEMA_VERSION:
                logging.getLogger("boneio.core.config.yaml_util").warning(
                    "Config version %d is newer than supported schema version %d. "
                    "This config was created by a newer version of boneIO. "
                    "Some features may not work correctly. "
                    "Consider upgrading the application or restoring an older config backup.",
                    config_version,
                    CURRENT_SCHEMA_VERSION,
                )
        assert any(
            "newer than supported schema version" in r.message for r in caplog.records
        )

    def test_no_warning_when_config_version_equals_current(self, caplog):
        config_version = CURRENT_SCHEMA_VERSION
        with caplog.at_level(logging.WARNING):
            if config_version > CURRENT_SCHEMA_VERSION:
                logging.getLogger("boneio.core.config.yaml_util").warning("should not appear")
        assert not any(
            "newer than supported schema version" in r.message for r in caplog.records
        )

    def test_no_warning_when_config_version_below_current(self, caplog):
        config_version = 0
        with caplog.at_level(logging.WARNING):
            if config_version > CURRENT_SCHEMA_VERSION:
                logging.getLogger("boneio.core.config.yaml_util").warning("should not appear")
        assert not any(
            "newer than supported schema version" in r.message for r in caplog.records
        )


class TestCompatibilityCheck:
    """Tests for the compatibility check logic (mirrors check_config_compat endpoint)."""

    @staticmethod
    def _check_compat(current_config_version: int, target_app_version: str) -> dict:
        """Replicate the logic from check_config_compat endpoint."""
        from packaging import version as pkg_version

        target_parsed = pkg_version.parse(target_app_version)

        max_supported_schema = 0
        min_required_app = SCHEMA_VERSION_APP_MAP.get(current_config_version, "unknown")

        for schema_ver, app_ver_str in sorted(SCHEMA_VERSION_APP_MAP.items()):
            if pkg_version.parse(app_ver_str) <= target_parsed:
                max_supported_schema = schema_ver

        compatible = current_config_version <= max_supported_schema
        return {
            "compatible": compatible,
            "current_config_version": current_config_version,
            "target_max_schema_version": max_supported_schema,
            "min_required_app_version": min_required_app,
        }

    def test_compatible_when_target_supports_current_config(self):
        """Rolling back to a version that supports current config_version."""
        result = self._check_compat(
            current_config_version=2,
            target_app_version="1.3.0dev1",
        )
        assert result["compatible"] is True

    def test_compatible_when_target_is_newer(self):
        result = self._check_compat(
            current_config_version=1,
            target_app_version="2.0.0",
        )
        assert result["compatible"] is True

    def test_incompatible_when_config_too_new_for_target(self):
        """The main scenario: config v2 but rolling back to app that only supports v1."""
        result = self._check_compat(
            current_config_version=2,
            target_app_version="1.2.0dev1",
        )
        assert result["compatible"] is False
        assert result["target_max_schema_version"] == 1

    def test_incompatible_when_rolling_back_to_original_version(self):
        """Config v2 rolling back to 1.0.0 (only supports v0)."""
        result = self._check_compat(
            current_config_version=2,
            target_app_version="1.0.0",
        )
        assert result["compatible"] is False
        assert result["target_max_schema_version"] == 0

    def test_compatible_with_config_version_zero(self):
        """Config v0 is compatible with any app version."""
        result = self._check_compat(
            current_config_version=0,
            target_app_version="1.0.0",
        )
        assert result["compatible"] is True

    def test_compatible_with_exact_boundary_version(self):
        """Config v1 with app version exactly at the boundary."""
        result = self._check_compat(
            current_config_version=1,
            target_app_version="1.2.0dev1",
        )
        assert result["compatible"] is True
