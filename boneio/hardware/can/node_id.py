"""CAN node ID management for boneIO.

Generates a deterministic, unique CANopen node_id (1-127) from the device's
MAC address and persists it in the config directory alongside config.yaml.
"""

from __future__ import annotations

import logging
import os

_LOGGER = logging.getLogger(__name__)

# CANopen node_id valid range
NODE_ID_MIN = 1
NODE_ID_MAX = 127

# Persistence filename (stored next to config.yaml)
NODE_ID_FILENAME = "can_node_id"

# Unconfigured node ID
UNCONFIGURED_NODE_ID = 127


def _derive_node_id_from_mac(mac_address: str) -> int:
    """Derive deterministic CAN node_id from a MAC address.

    Args:
        mac_address: Device MAC address string, e.g. ``aa:bb:cc:dd:ee:ff``.

    Returns:
        Deterministic node ID in valid CANopen range 1-127.
    """
    clean_mac = mac_address.replace(":", "").replace("-", "").strip().lower()
    if len(clean_mac) != 12:
        raise ValueError(f"Invalid MAC address format: {mac_address!r}")

    mac_int = int(clean_mac, 16)
    return (mac_int % NODE_ID_MAX) + NODE_ID_MIN


def _read_persisted_node_id(config_dir: str) -> int | None:
    """Read persisted node_id from config directory.

    Args:
        config_dir: Directory where config.yaml lives.

    Returns:
        Persisted node_id or None if not found/invalid.
    """
    path = os.path.join(config_dir, NODE_ID_FILENAME)
    try:
        with open(path) as f:
            value = int(f.read().strip())
        if NODE_ID_MIN <= value <= NODE_ID_MAX:
            return value
        _LOGGER.warning("Persisted node_id %d out of range, ignoring", value)
        return None
    except FileNotFoundError:
        return None
    except (ValueError, OSError) as e:
        _LOGGER.warning("Cannot read persisted node_id: %s", e)
        return None


def persist_node_id(config_dir: str, node_id: int) -> bool:
    """Persist node_id to config directory.

    Args:
        config_dir: Directory where config.yaml lives.
        node_id: Node ID to persist.

    Returns:
        True if successfully written.
    """
    path = os.path.join(config_dir, NODE_ID_FILENAME)
    try:
        with open(path, "w") as f:
            f.write(str(node_id))
        _LOGGER.info("Persisted CAN node_id=%d to %s", node_id, path)
        return True
    except OSError as e:
        _LOGGER.error("Failed to persist node_id to %s: %s", path, e)
        return False


def resolve_node_id(
    node_id_config: str | int,
    mac_address: str,
    config_dir: str,
) -> int:
    """Resolve the CAN node_id from configuration.

    Logic:
    1. If node_id_config is an integer 1-127, use it directly (manual override).
    2. If node_id_config is 'auto':
       a. Try to read persisted node_id from {config_dir}/can_node_id.
       b. If not found, use UNCONFIGURED_NODE_ID (127) as default.

    Args:
        node_id_config: Value from config ('auto' or integer 1-127).
        mac_address: Device MAC address (e.g., 'aa:bb:cc:dd:ee:ff').
        config_dir: Directory where config.yaml lives.

    Returns:
        Resolved node_id (1-127).

    Raises:
        ValueError: If node_id cannot be resolved.
    """
    # Manual override
    if isinstance(node_id_config, int):
        if not NODE_ID_MIN <= node_id_config <= NODE_ID_MAX:
            raise ValueError(
                f"node_id {node_id_config} out of range ({NODE_ID_MIN}-{NODE_ID_MAX})"
            )
        _LOGGER.info("Using manually configured CAN node_id=%d", node_id_config)
        return node_id_config

    # Auto mode
    if str(node_id_config).lower() == "auto":
        # Try persisted first
        persisted = _read_persisted_node_id(config_dir)
        if persisted is not None:
            _LOGGER.info("Using persisted CAN node_id=%d", persisted)
            return persisted

        # Derive from MAC and persist for stable future boots
        node_id = _derive_node_id_from_mac(mac_address)
        persist_ok = persist_node_id(config_dir, node_id)
        if not persist_ok:
            _LOGGER.warning(
                "CAN node_id=%d computed from MAC but could not be persisted",
                node_id,
            )
        _LOGGER.info(
            "No persisted CAN node_id found, using MAC-derived ID=%d",
            node_id,
        )
        return node_id

    raise ValueError(
        f"Invalid node_id config: {node_id_config!r} (expected 'auto' or integer 1-127)"
    )
