"""WLED metadata cache — JSON-based storage for effects, palettes, and segments.

Stores auto-discovered WLED device metadata in ``<config_dir>/.wled_cache.json``
instead of config.yaml.  This avoids slow YAML serialization of ~64KB data
(219 effects × 72 palettes × N devices) on ARM hardware.

The cache is populated from the WLED ``/json`` API on device connect and is
**not** included in config backups — it auto-regenerates.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

# In-memory cache, lazily populated from disk
_cache: dict[str, dict[str, list[dict[str, str | int]]]] | None = None
_cache_path: Path | None = None


def init_cache(config_dir: str | Path) -> None:
    """Initialize cache path and load from disk if available.

    Call this once at startup with the config directory path.

    Args:
        config_dir: Path to the boneIO config directory.
    """
    global _cache_path, _cache
    _cache_path = Path(config_dir) / ".wled_cache.json"
    _cache = None  # Force reload on next access
    _LOGGER.debug("WLED cache path: %s", _cache_path)


def _load_cache() -> dict[str, dict[str, list[dict[str, str | int]]]]:
    """Load cache from disk.

    Returns:
        Dict mapping device_id to {effects, palettes, segments}.
    """
    global _cache
    if _cache is not None:
        return _cache

    _cache = {}
    if _cache_path and _cache_path.exists():
        try:
            with open(_cache_path, encoding="utf-8") as f:
                _cache = json.load(f)
            _LOGGER.debug(
                "Loaded WLED cache: %d device(s)", len(_cache)
            )
        except Exception as exc:
            _LOGGER.warning("Failed to load WLED cache: %s", exc)
            _cache = {}

    return _cache


def get_device_metadata(device_id: str) -> dict[str, list[dict[str, str | int]]]:
    """Get cached metadata for a WLED device.

    Args:
        device_id: WLED device identifier.

    Returns:
        Dict with 'effects', 'palettes', 'segments' lists.
        Empty dict if not cached.
    """
    cache = _load_cache()
    return cache.get(device_id, {})


def get_all_metadata() -> dict[str, dict[str, list[dict[str, str | int]]]]:
    """Get cached metadata for all WLED devices.

    Returns:
        Dict mapping device_id to metadata.
    """
    return _load_cache()


def update_device_metadata(
    device_id: str,
    *,
    effects: list[dict[str, str | int]] | None = None,
    palettes: list[dict[str, str | int]] | None = None,
    segments: list[dict[str, str | int]] | None = None,
) -> None:
    """Update cached metadata for a device and persist to disk.

    Only updates fields that are provided (not None).

    Args:
        device_id: WLED device identifier.
        effects: List of effect dicts with 'id' and 'name'.
        palettes: List of palette dicts with 'id' and 'name'.
        segments: List of segment dicts with 'id', 'name', etc.
    """
    cache = _load_cache()

    if device_id not in cache:
        cache[device_id] = {}

    if effects is not None:
        cache[device_id]["effects"] = effects
    if palettes is not None:
        cache[device_id]["palettes"] = palettes
    if segments is not None:
        cache[device_id]["segments"] = segments

    _persist_cache(cache)

    _LOGGER.info(
        "Updated WLED cache for '%s' (effects=%s, palettes=%s, segments=%s)",
        device_id,
        len(effects) if effects is not None else "-",
        len(palettes) if palettes is not None else "-",
        len(segments) if segments is not None else "-",
    )


def _persist_cache(
    cache: dict[str, dict[str, list[dict[str, str | int]]]]
) -> None:
    """Write cache to disk as JSON.

    Args:
        cache: Full cache dict to persist.
    """
    if not _cache_path:
        _LOGGER.warning("WLED cache path not initialized, skipping persist")
        return

    try:
        with open(_cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        _LOGGER.warning("Failed to write WLED cache: %s", exc)
