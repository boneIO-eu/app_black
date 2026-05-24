"""Reusable Home Assistant dashboard card builders.

Generic building blocks for generating HA Lovelace dashboard YAML.
Not tied to any specific domain — can be used for irrigation, covers,
lights, etc.
"""

from __future__ import annotations

from typing import Any

import yaml


# ─── Entity ID ────────────────────────────────────────────────────────────


def build_entity_id(
    serial: str,
    entity_type: str,
    prefix: str,
    entity_id: str,
    suffix: str = "",
) -> str:
    """Build a Home Assistant entity ID.

    Pattern: ``{entity_type}.{serial}_{prefix}_{entity_id}[_{suffix}]``

    Args:
        serial: Device serial number (e.g. ``'blk3361e9'``).
        entity_type: HA entity type (``switch``, ``valve``, ``sensor``, …).
        prefix: Domain prefix (e.g. ``'irrigation'``, ``'cover'``).
        entity_id: Main entity identifier.
        suffix: Optional extra suffix appended after entity_id.

    Returns:
        Full entity ID (e.g. ``switch.blk3361e9_irrigation_garden_main``).
    """
    base = f"{prefix}_{entity_id}"
    if suffix:
        base = f"{base}_{suffix}"
    return f"{entity_type}.{serial}_{base}"


# ─── Card primitives ──────────────────────────────────────────────────────


def entity_badge(entity: str) -> dict[str, Any]:
    """Create an entity badge for use in heading cards.

    Args:
        entity: Full HA entity ID.

    Returns:
        Badge dict with ``type``, ``show_state``, ``show_icon``, ``entity``.
    """
    return {
        "type": "entity",
        "show_state": True,
        "show_icon": True,
        "entity": entity,
    }


def heading_card(
    heading: str,
    style: str = "title",
    badges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a heading card.

    Args:
        heading: Heading text (may include emoji).
        style: ``'title'`` or ``'subtitle'``.
        badges: Optional list of badge dicts.

    Returns:
        Heading card dict.
    """
    card: dict[str, Any] = {
        "type": "heading",
        "heading_style": style,
        "heading": heading,
    }
    if badges:
        card["badges"] = badges
    return card


def tile_card(
    entity: str,
    name: str,
    icon: str,
    *,
    state_content: list[str] | None = None,
    vertical: bool = False,
    tap_action: str = "toggle",
    hold_action: str = "more-info",
    icon_tap_action: str = "more-info",
    features: list[dict[str, Any]] | None = None,
    features_position: str = "bottom",
) -> dict[str, Any]:
    """Create a tile card.

    Args:
        entity: Full HA entity ID.
        name: Display name.
        icon: MDI icon string.
        state_content: State lines to display.
        vertical: Vertical layout.
        tap_action: Tap action type.
        hold_action: Hold action type.
        icon_tap_action: Icon tap action type.
        features: Optional features list.
        features_position: Features position.

    Returns:
        Tile card dict.
    """
    card: dict[str, Any] = {
        "type": "tile",
        "entity": entity,
        "name": name,
        "icon": icon,
    }
    if state_content:
        card["state_content"] = state_content
    card["vertical"] = vertical
    card["tap_action"] = {"action": tap_action}
    card["hold_action"] = {"action": hold_action}
    card["icon_tap_action"] = {"action": icon_tap_action}
    if features:
        card["features"] = features
    card["features_position"] = features_position
    return card


def sensor_tile(
    entity: str,
    name: str,
    icon: str,
    *,
    state_content: list[str] | None = None,
) -> dict[str, Any]:
    """Create a read-only sensor tile card (no actions).

    Args:
        entity: Full HA entity ID.
        name: Display name.
        icon: MDI icon string.
        state_content: State lines to display.

    Returns:
        Tile card dict.
    """
    card: dict[str, Any] = {
        "type": "tile",
        "entity": entity,
        "name": name,
        "icon": icon,
    }
    if state_content:
        card["state_content"] = state_content
    return card


def slider_tile(
    entity: str,
    name: str,
    icon: str = "mdi:timer-outline",
) -> dict[str, Any]:
    """Create a tile card with a numeric slider feature.

    Args:
        entity: Full HA entity ID (must be ``number.*``).
        name: Display name.
        icon: MDI icon string.

    Returns:
        Tile card dict with ``numeric-input`` slider.
    """
    return {
        "type": "tile",
        "entity": entity,
        "name": name,
        "icon": icon,
        "features": [{"type": "numeric-input", "style": "buttons"}],
    }


def entities_card(
    entities: list[str | dict[str, Any]],
    title: str = "",
) -> dict[str, Any]:
    """Create an entities card.

    Args:
        entities: List of entity IDs or entity config dicts.
        title: Optional card title.

    Returns:
        Entities card dict.
    """
    card: dict[str, Any] = {
        "type": "entities",
        "entities": entities,
    }
    if title:
        card["title"] = title
    return card


def button_card(
    entity: str,
    name: str,
    icon: str,
    *,
    tap_action: str = "toggle",
) -> dict[str, Any]:
    """Create a button card.

    Args:
        entity: Full HA entity ID.
        name: Display label.
        icon: MDI icon string.
        tap_action: Tap action type.

    Returns:
        Button card dict.
    """
    return {
        "type": "button",
        "entity": entity,
        "name": name,
        "icon": icon,
        "tap_action": {"action": tap_action},
        "show_name": True,
        "show_icon": True,
    }


def horizontal_stack(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a horizontal-stack card.

    Args:
        cards: List of card dicts to stack horizontally.

    Returns:
        Horizontal-stack card dict.
    """
    return {
        "type": "horizontal-stack",
        "cards": cards,
    }


# ─── YAML serialisation ──────────────────────────────────────────────────


def cards_to_yaml(cards: list[dict[str, Any]], *, grid: bool = True) -> str:
    """Serialize a list of cards to HA-compatible YAML.

    Args:
        cards: List of card dicts.
        grid: If True, wrap in a ``type: grid`` container.

    Returns:
        YAML string ready to paste into HA dashboard.
    """
    if grid:
        dashboard: dict[str, Any] = {"type": "grid", "cards": cards}
    else:
        dashboard = {"cards": cards}

    return yaml.dump(
        dashboard,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
