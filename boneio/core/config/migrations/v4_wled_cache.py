"""Migration v4: Extract WLED effects/palettes/segments from config to JSON cache.

Before: WLED effects (219 items), palettes (72 items), and segments are stored
        inline in each remote_device's ``wled`` section inside config.yaml.
        This causes 3-5 second YAML serialization delays on ARM hardware.

After:  These fields are stripped from config and saved to a lightweight
        ``.wled_cache.json`` file.  The cache auto-regenerates from WLED API
        on device connect, so no data is permanently lost.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from boneio.core.atomic_file import write_atomically
from boneio.core.config.migrations import register_migration

_LOGGER = logging.getLogger(__name__)

# Fields to strip from each WLED device config — these are device metadata,
# not user configuration.
_WLED_CACHE_FIELDS = ("effects", "palettes", "segments")


def _persist_wled_cache_strip(config_file: str) -> None:
    """Strip effects/palettes/segments from WLED devices in the YAML file.

    Reads the config file(s), extracts WLED metadata into a JSON cache,
    and rewrites the YAML without those bulky lists.

    Args:
        config_file: Path to the main config.yaml file.
    """
    config_dir = Path(config_file).parent

    # First, find and extract WLED data from the in-memory parse
    # to save into .wled_cache.json before removing from YAML
    try:
        from yaml import load

        from boneio.core.config.yaml_compat import FastSafeLoader

        class IncludeLoader(FastSafeLoader):
            """YAML loader that tolerates boneIO's custom tags."""

        def _include_constructor(
            loader: IncludeLoader, node: object
        ) -> object:
            filename = loader.construct_scalar(node)  # type: ignore[arg-type]
            return type(
                "Include", (), {"filename": filename, "tag": "!include"}
            )()

        def _unknown_tag_constructor(
            loader: IncludeLoader, tag_suffix: str, node: object
        ) -> object:
            """Stand in for any tag this migration has no opinion about.

            Registering only !include is what broke this: a config using
            !secret — a documented feature, and the right way to keep an MQTT
            or device password out of config.yaml — raised
            "could not determine a constructor", the broad except below
            swallowed it, and the migration quietly did nothing for exactly the
            people who had followed the security advice.

            A placeholder is enough because the parse is only used to locate
            the WLED fields; the file itself is edited with regexes further
            down, so whatever a tag stood for is written back untouched. The
            catch-all covers tags added later too, so this cannot break the
            same way twice.
            """
            return type(
                "UnknownTag", (), {"tag": f"!{tag_suffix}", "node": node}
            )()

        IncludeLoader.add_constructor("!include", _include_constructor)
        IncludeLoader.add_multi_constructor("!", _unknown_tag_constructor)

        with open(config_file, encoding="utf-8") as f:
            config = load(f, Loader=IncludeLoader)  # noqa: S506

        if not config:
            return

        # Determine where remote_devices lives
        rd_section = config.get("remote_devices")
        if rd_section is None:
            return

        # If it's an !include, load the included file
        if hasattr(rd_section, "tag") and rd_section.tag == "!include":
            include_path = config_dir / rd_section.filename
            if include_path.exists():
                with open(include_path, encoding="utf-8") as f:
                    # Same tolerant loader: an included remote_devices.yaml
                    # carries device passwords, which is precisely where
                    # !secret belongs.
                    rd_list = load(f, Loader=IncludeLoader)  # noqa: S506
                _strip_wled_fields_from_file(include_path, rd_list, config_dir)
            return

        # Inline remote_devices — strip from main config file
        if isinstance(rd_section, list):
            _strip_wled_fields_from_file(
                Path(config_file), rd_section, config_dir
            )

    except Exception as exc:
        # Loud on purpose. This used to be the end of the road for any config
        # the loader could not parse, with nothing to tell the owner their
        # migration had not run.
        _LOGGER.error(
            "Failed to strip WLED cache fields from %s: %s. The WLED metadata "
            "stays in the YAML; nothing was lost, but this migration did not "
            "run.",
            config_file,
            exc,
        )


def _strip_wled_fields_from_file(
    yaml_path: Path, devices: list[dict] | None, config_dir: Path
) -> None:
    """Extract WLED metadata to JSON cache, then strip from YAML file.

    Args:
        yaml_path: Path to the YAML file containing remote_devices.
        devices: Parsed list of remote device dicts.
        config_dir: Config directory for placing the cache file.
    """
    if not devices:
        return

    # Extract cache data
    cache_data: dict[str, dict[str, list[dict[str, str | int]]]] = {}
    has_data = False

    for device in devices:
        if not isinstance(device, dict):
            continue
        wled = device.get("wled")
        if not isinstance(wled, dict):
            continue

        device_id = device.get("id", "")
        if not device_id:
            continue

        device_cache: dict[str, list[dict[str, str | int]]] = {}
        for field in _WLED_CACHE_FIELDS:
            if field in wled and isinstance(wled[field], list) and wled[field]:
                device_cache[field] = wled[field]
                has_data = True
        if device_cache:
            cache_data[device_id] = device_cache

    # Save extracted data to JSON cache
    if has_data:
        cache_path = config_dir / ".wled_cache.json"
        try:
            # Merge with existing cache (other migrations may have run)
            existing: dict[str, dict[str, list[dict[str, str | int]]]] = {}
            if cache_path.exists():
                with open(cache_path, encoding="utf-8") as f:
                    existing = json.load(f)

            existing.update(cache_data)

            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)

            _LOGGER.info(
                "Saved WLED metadata for %d device(s) to %s",
                len(cache_data),
                cache_path,
            )
        except Exception as exc:
            _LOGGER.warning("Failed to write WLED cache: %s", exc)

    # Now strip the fields from the YAML file using regex
    # This is safer than re-serializing the entire file
    with open(yaml_path, encoding="utf-8") as f:
        content = f.read()

    original_content = content

    # Remove effects/palettes/segments blocks from YAML
    # Pattern: indented key followed by a list of dicts
    for field in _WLED_CACHE_FIELDS:
        # Match the field key line and all following lines that are more indented
        # or are list items (- ) at deeper indent
        pattern = re.compile(
            rf"^( +){field}:\s*\n"        # field key line
            rf"((?:\1 .+\n|\1- .+\n)*)",  # indented content below
            re.MULTILINE,
        )
        content = pattern.sub("", content)

    if content != original_content:
        write_atomically(yaml_path, content)
        _LOGGER.info(
            "Stripped WLED cache fields from %s (saved %d bytes)",
            yaml_path.name,
            len(original_content) - len(content),
        )


@register_migration(
    version=4,
    name="Extract WLED effects/palettes/segments to JSON cache",
    migrate_file=_persist_wled_cache_strip,
)
def migrate(doc: dict) -> dict:
    """Strip effects, palettes, and segments from remote_devices in memory.

    These fields are device metadata auto-discovered from the WLED API,
    not user configuration.  Storing them in config.yaml causes slow saves
    on ARM hardware due to YAML serialization overhead (~64KB per 7 devices).

    After migration, this data lives in ``.wled_cache.json`` and is
    auto-populated from the WLED API on device connect.

    Args:
        doc: Raw config dict.

    Returns:
        Migrated config dict with WLED metadata fields removed.
    """
    remote_devices = doc.get("remote_devices")
    if not isinstance(remote_devices, list):
        return doc

    for device in remote_devices:
        if not isinstance(device, dict):
            continue
        wled = device.get("wled")
        if not isinstance(wled, dict):
            continue

        for field in _WLED_CACHE_FIELDS:
            if field in wled:
                items = wled[field]
                count = len(items) if isinstance(items, list) else 0
                _LOGGER.info(
                    "Stripping wled.%s (%d items) from device '%s'",
                    field,
                    count,
                    device.get("id", "?"),
                )
                del wled[field]

    return doc
