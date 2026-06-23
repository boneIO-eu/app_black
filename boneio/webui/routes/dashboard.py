"""HA Dashboard Wizard API routes.

Provides endpoints for the step-by-step dashboard YAML generator:
- /api/dashboard/meta — returns available entity types, counts, and areas
- /api/dashboard/generate — generates Sections-layout YAML for selected types
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Query

from boneio.const import COVER, LED, LIGHT, NONE, SWITCH, VALVE
from boneio.webui.dashboard_cards import (
    cards_to_yaml,
    ha_slugify,
    heading_card,
    sections_to_yaml,
    tile_card,
)
from boneio.webui.modbus_card_templates import generate_cards_for_device


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# ─── Constants ────────────────────────────────────────────────────────────

# Map output_type -> HA entity type for entity_id construction
_OUTPUT_TYPE_TO_HA_ENTITY = {
    SWITCH: "switch",
    LIGHT: "light",
    LED: "light",
    VALVE: "valve",
}

# Map output_type -> MDI icon for tile cards
_OUTPUT_TYPE_ICON = {
    SWITCH: "mdi:toggle-switch-outline",
    LIGHT: "mdi:lightbulb",
    LED: "mdi:led-on",
    VALVE: "mdi:valve",
}

# Icons for group cards (distinct from single output icons)
_GROUP_TYPE_ICON = {
    SWITCH: "mdi:toggle-switch-outline",
    LIGHT: "mdi:lightbulb-group",
    LED: "mdi:lightbulb-group",
    VALVE: "mdi:valve",
}

# Map output_type -> emoji for headings
_OUTPUT_TYPE_EMOJI = {
    SWITCH: "🔌",
    LIGHT: "💡",
    LED: "💡",
    VALVE: "🚿",
}


# ─── Helpers ──────────────────────────────────────────────────────────────


def _ha_slugify(text: str) -> str:
    """Normalize text to match HA entity_id format.

    Delegates to the canonical ha_slugify in dashboard_cards.

    Args:
        text: Raw entity ID text.

    Returns:
        HA-compatible slugified string.
    """
    return ha_slugify(text)


def _get_irrigation_output_ids(manager: Any) -> set[str]:
    """Collect all output IDs used by irrigation controllers.

    Includes zone valves and water source outputs.

    Args:
        manager: Application manager instance.

    Returns:
        Set of output IDs that belong to irrigation.
    """
    ids: set[str] = set()
    if not hasattr(manager, "irrigation"):
        return ids
    for ctrl in manager.irrigation.controllers.values():
        for zone in ctrl.zones:
            valve = getattr(zone, "valve", None)
            if valve is not None:
                ids.add(getattr(valve, "id", ""))
        for src in getattr(ctrl, "_water_sources", []):
            for output in getattr(src, "outputs", []):
                ids.add(getattr(output, "id", ""))
    ids.discard("")
    return ids


# ─── Card generators ─────────────────────────────────────────────────────


def _generate_output_cards_by_area(
    outputs: dict[str, Any],
    serial: str,
    exclude_ids: set[str] | None = None,
) -> dict[str, list[dict]]:
    """Generate output cards grouped by area.

    Args:
        outputs: Dict of output_id -> output object.
        serial: Device serial number.
        exclude_ids: Set of output IDs to exclude (e.g. irrigation valves).

    Returns:
        Dict mapping area display name to list of card dicts.
    """
    # Group by area, then by output_type
    grouped: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    _exclude = exclude_ids or set()

    for output_id, output in outputs.items():
        if output_id in _exclude:
            continue
        out_type = getattr(output, "output_type", None)
        if out_type in (NONE, COVER, None):
            continue
        area = getattr(output, "area", None) or "other"
        grouped[area][out_type].append((output_id, output))

    result: dict[str, list[dict]] = {}
    sorted_areas = sorted(grouped.keys(), key=lambda a: (a == "other", a))

    for area in sorted_areas:
        area_types = grouped[area]
        area_display = area.replace("_", " ").title() if area != "other" else "Other"
        cards: list[dict] = [heading_card(f"🏠 {area_display}", style="title")]

        type_order = [LIGHT, LED, SWITCH, VALVE]
        sorted_types = sorted(
            area_types.keys(),
            key=lambda t: type_order.index(t) if t in type_order else 99,
        )

        for out_type in sorted_types:
            output_list = area_types[out_type]
            emoji = _OUTPUT_TYPE_EMOJI.get(out_type, "⚡")
            type_label = out_type.title() if out_type != LED else "LED"
            cards.append(heading_card(f"{emoji} {type_label}", style="subtitle"))

            output_list.sort(key=lambda x: getattr(x[1], "name", None) or x[0])

            for output_id, output in output_list:
                ha_entity_type = _OUTPUT_TYPE_TO_HA_ENTITY.get(out_type, "switch")
                entity_id = f"{ha_entity_type}.{_ha_slugify(f'{serial}_{output_id}')}"
                name = getattr(output, "name", None) or output_id
                icon = _OUTPUT_TYPE_ICON.get(out_type, "mdi:toggle-switch-outline")
                cards.append(
                    tile_card(
                        entity=entity_id,
                        name=name,
                        icon=icon,
                        state_content=["state", "last_changed"],
                    )
                )

        result[area_display] = cards

    return result


def _generate_cover_cards_by_area(
    covers: dict[str, Any],
    serial: str,
) -> dict[str, list[dict]]:
    """Generate cover cards grouped by area.

    Args:
        covers: Dict of cover_id -> cover object.
        serial: Device serial number.

    Returns:
        Dict mapping area display name to list of card dicts.
    """
    grouped: dict[str, list] = defaultdict(list)

    for cover_id, cover in covers.items():
        area = getattr(cover, "area", None) or "other"
        grouped[area].append((cover_id, cover))

    result: dict[str, list[dict]] = {}
    sorted_areas = sorted(grouped.keys(), key=lambda a: (a == "other", a))

    for area in sorted_areas:
        cover_list = grouped[area]
        area_display = area.replace("_", " ").title() if area != "other" else "Other"
        cards: list[dict] = [
            heading_card(f"🪟 {area_display}", style="title"),
        ]

        cover_list.sort(key=lambda x: getattr(x[1], "name", None) or x[0])

        cards.append(heading_card("🪟 Covers", style="subtitle"))

        for cover_id, cover in cover_list:
            entity_id = f"cover.{_ha_slugify(f'{serial}_{cover_id}')}"
            name = getattr(cover, "name", None) or cover_id
            cards.append(
                tile_card(
                    entity=entity_id,
                    name=name,
                    icon="mdi:window-shutter",
                    state_content=["state", "current_position"],
                    features=[{"type": "cover-open-close"}, {"type": "cover-position"}],
                )
            )

        result[area_display] = cards

    return result


def _generate_group_cards_by_area(
    groups: dict[str, Any],
    serial: str,
) -> dict[str, list[dict]]:
    """Generate output group cards grouped by area.

    Args:
        groups: Dict of group_id -> group object.
        serial: Device serial number.

    Returns:
        Dict mapping area display name to list of card dicts.
    """
    grouped: dict[str, list] = defaultdict(list)

    for group_id, group in groups.items():
        area = getattr(group, "area", None) or "other"
        out_type = getattr(group, "output_type", None)
        if out_type in (NONE, None):
            continue
        grouped[area].append((group_id, group))

    result: dict[str, list[dict]] = {}
    sorted_areas = sorted(grouped.keys(), key=lambda a: (a == "other", a))

    for area in sorted_areas:
        group_list = grouped[area]
        area_display = area.replace("_", " ").title() if area != "other" else "Other"
        cards: list[dict] = [
            heading_card(f"👥 {area_display}", style="title"),
        ]

        group_list.sort(key=lambda x: getattr(x[1], "name", None) or x[0])

        cards.append(heading_card("👥 Groups", style="subtitle"))

        for group_id, group in group_list:
            out_type = getattr(group, "output_type", SWITCH)
            ha_entity_type = _OUTPUT_TYPE_TO_HA_ENTITY.get(out_type, "switch")
            entity_id = f"{ha_entity_type}.{_ha_slugify(f'{serial}_{group_id}')}"
            name = getattr(group, "name", None) or group_id
            icon = _GROUP_TYPE_ICON.get(out_type, "mdi:toggle-switch-outline")
            cards.append(
                tile_card(
                    entity=entity_id,
                    name=name,
                    icon=icon,
                    state_content=["state", "last_changed"],
                )
            )

        result[area_display] = cards

    return result


def _generate_alarm_cards_by_area(
    alarm_panels: list,
    serial: str,
) -> dict[str, list[dict]]:
    """Generate alarm panel cards grouped by area.

    Args:
        alarm_panels: List of BoneIOAlarmPanel objects.
        serial: Device serial number.

    Returns:
        Dict mapping area display name to list of card dicts.
    """
    grouped: dict[str, list] = defaultdict(list)

    for panel in alarm_panels:
        area = getattr(panel, "area", None) or "other"
        grouped[area].append(panel)

    result: dict[str, list[dict]] = {}
    sorted_areas = sorted(grouped.keys(), key=lambda a: (a == "other", a))

    for area in sorted_areas:
        panels = grouped[area]
        area_display = area.replace("_", " ").title() if area != "other" else "Other"
        cards: list[dict] = [
            heading_card(f"🚨 {area_display}", style="title"),
        ]

        cards.append(heading_card("🚨 Alarm", style="subtitle"))

        for panel in panels:
            entity_id = f"alarm_control_panel.{_ha_slugify(f'{serial}_{panel.id}')}"
            name = getattr(panel, "name", panel.id)
            cards.append(
                tile_card(
                    entity=entity_id,
                    name=name,
                    icon="mdi:shield-home",
                    state_content=["state"],
                )
            )

        result[area_display] = cards

    return result


def _generate_gate_cards_by_area(
    gate_covers: list,
    serial: str,
) -> dict[str, list[dict]]:
    """Generate gate/door cover cards grouped by area.

    Args:
        gate_covers: List of BoneIOGateCover objects.
        serial: Device serial number.

    Returns:
        Dict mapping area display name to list of card dicts.
    """
    grouped: dict[str, list] = defaultdict(list)

    for gate in gate_covers:
        area = getattr(gate, "area", None) or "other"
        grouped[area].append(gate)

    result: dict[str, list[dict]] = {}
    sorted_areas = sorted(grouped.keys(), key=lambda a: (a == "other", a))

    for area in sorted_areas:
        gates = grouped[area]
        area_display = area.replace("_", " ").title() if area != "other" else "Other"
        cards: list[dict] = [
            heading_card(f"🚪 {area_display}", style="title"),
        ]

        cards.append(heading_card("🚪 Gates", style="subtitle"))

        for gate in gates:
            entity_id = f"cover.{_ha_slugify(f'{serial}_{gate.id}')}"
            name = getattr(gate, "name", gate.id)
            cards.append(
                tile_card(
                    entity=entity_id,
                    name=name,
                    icon="mdi:gate",
                    state_content=["state"],
                    features=[{"type": "cover-open-close"}],
                )
            )

        result[area_display] = cards

    return result


def _generate_modbus_cards(
    coordinators: dict[str, Any],
    serial: str,
) -> list[dict]:
    """Generate modbus sensor cards (per device, not per area).

    Dispatches to category-specific card templates (HVAC, energy meters, etc.)
    via generate_cards_for_device(). Each modbus device gets its own section
    with semantically grouped entities and proper MDI icons.

    Args:
        coordinators: Dict of device_id -> ModbusCoordinator.
        serial: Device serial number.

    Returns:
        List of section dicts (area, yaml, entity_count, breakdown).
    """
    result_sections: list[dict] = []

    for device_id, coord in coordinators.items():
        device_name = getattr(coord, "_name", device_id)
        model = getattr(coord, "_model", "")

        # Build device_info from coordinator attributes
        device_info = {
            "model": model,
            "name": device_name,
            "device_id": device_id,
            "manufacturer": getattr(coord, "manufacturer", "boneIO"),
            "category": getattr(coord, "category", "other"),
        }

        # Try to get category from the device JSON db
        db = getattr(coord, "_db", {})
        if isinstance(db, dict):
            device_info["category"] = db.get("category", device_info["category"])
            device_info["manufacturer"] = db.get(
                "manufacturer", device_info["manufacturer"]
            )

        cards = generate_cards_for_device(
            device_id=device_id,
            entities_list=coord.get_all_entities(),
            serial=serial,
            device_info=device_info,
        )

        entity_count = sum(
            1 for c in cards if c.get("type") not in ("heading", None)
        )

        if entity_count > 0:
            result_sections.append(
                {
                    "area": f"📡 {device_name}",
                    "yaml": cards_to_yaml(cards),
                    "entity_count": entity_count,
                    "breakdown": {f"📡 {model or 'Modbus'}": entity_count},
                }
            )

    return result_sections


def _merge_sections(
    *section_dicts: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """Merge multiple area->cards dicts, combining cards for same area.

    Args:
        section_dicts: Variable number of area->cards dicts.

    Returns:
        Merged dict where same-area cards are concatenated.
    """
    merged: dict[str, list[dict]] = {}
    for section_dict in section_dicts:
        for area, cards in section_dict.items():
            if area in merged:
                # Skip duplicate area heading, append only entity cards
                merged[area].extend(cards[1:] if cards else [])
            else:
                merged[area] = list(cards)
    return merged


# ─── API endpoints ────────────────────────────────────────────────────────


@router.get("/meta")
async def dashboard_meta(manager: Manager = Depends(get_manager)):
    """Return metadata for the dashboard wizard.

    Provides counts of exportable entities per type and per area,
    so the wizard UI can show which options are available.

    Returns:
        Dict with 'types' (entity type counts, entity lists) and 'areas'.
    """
    try:
        all_outputs = manager.outputs.get_all_outputs()
        all_covers = manager.covers.get_all_covers()
        all_groups = manager.outputs.get_all_output_groups()
        irrigation_controllers = manager.irrigation.controllers if hasattr(manager, "irrigation") else {}
        irrigation_ids = _get_irrigation_output_ids(manager)

        # Build entity lists per type
        output_entities: list[dict] = []
        for oid, o in all_outputs.items():
            if oid in irrigation_ids:
                continue
            out_type = getattr(o, "output_type", None)
            if out_type in (NONE, COVER, None):
                continue
            output_entities.append(
                {
                    "id": oid,
                    "name": getattr(o, "name", None) or oid,
                    "area": getattr(o, "area", None) or "other",
                    "sub_type": out_type or "",
                }
            )

        cover_entities: list[dict] = []
        for cid, c in all_covers.items():
            cover_entities.append(
                {
                    "id": cid,
                    "name": getattr(c, "name", None) or cid,
                    "area": getattr(c, "area", None) or "other",
                }
            )

        group_entities: list[dict] = []
        for gid, g in all_groups.items():
            out_type = getattr(g, "output_type", None)
            if out_type in (NONE, None):
                continue
            group_entities.append(
                {
                    "id": gid,
                    "name": getattr(g, "name", None) or gid,
                    "area": getattr(g, "area", None) or "other",
                }
            )

        irrigation_entities: list[dict] = []
        for ctrl_id, ctrl in irrigation_controllers.items():
            zones = getattr(ctrl, "zones", [])
            irrigation_entities.append(
                {
                    "id": ctrl_id,
                    "name": getattr(ctrl, "name", ctrl_id),
                    "zones": len(zones),
                }
            )

        # Alarm panels
        alarm_panels = manager.templates.alarm_manager.items if hasattr(manager, "templates") else []
        alarm_entities: list[dict] = []
        for panel in alarm_panels:
            alarm_entities.append(
                {
                    "id": panel.id,
                    "name": getattr(panel, "name", panel.id),
                    "area": getattr(panel, "area", None) or "other",
                }
            )

        # Gate covers (bramy, furtki, drzwi)
        gate_covers = manager.templates.gate_manager.items if hasattr(manager, "templates") else []
        gate_entities: list[dict] = []
        for gate in gate_covers:
            gate_entities.append(
                {
                    "id": gate.id,
                    "name": getattr(gate, "name", gate.id),
                    "area": getattr(gate, "area", None) or "other",
                }
            )

        # Modbus devices
        modbus_coordinators = (
            manager.modbus.get_all_coordinators()
            if hasattr(manager, "modbus") and hasattr(manager.modbus, "get_all_coordinators")
            else {}
        )
        modbus_entities: list[dict] = []
        for dev_id, coord in modbus_coordinators.items():
            sensor_count = sum(len(d) for d in coord.get_all_entities())
            modbus_entities.append(
                {
                    "id": dev_id,
                    "name": getattr(coord, "_name", dev_id),
                    "sensors": sensor_count,
                }
            )

        # Per-area counts
        area_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for e in output_entities:
            area_counts[e["area"]]["outputs"] += 1
        for e in cover_entities:
            area_counts[e["area"]]["covers"] += 1
        for e in group_entities:
            area_counts[e["area"]]["groups"] += 1
        for e in alarm_entities:
            area_counts[e["area"]]["alarms"] += 1
        for e in gate_entities:
            area_counts[e["area"]]["gates"] += 1

        # Build areas list
        areas = []
        for area_id in sorted(area_counts.keys(), key=lambda a: (a == "other", a)):
            areas.append(
                {
                    "id": area_id,
                    "counts": dict(area_counts[area_id]),
                }
            )

        return {
            "types": {
                "outputs": {
                    "count": len(output_entities),
                    "enabled": len(output_entities) > 0,
                    "entities": output_entities,
                },
                "covers": {
                    "count": len(cover_entities),
                    "enabled": len(cover_entities) > 0,
                    "entities": cover_entities,
                },
                "groups": {
                    "count": len(group_entities),
                    "enabled": len(group_entities) > 0,
                    "entities": group_entities,
                },
                "irrigation": {
                    "count": len(irrigation_entities),
                    "enabled": len(irrigation_entities) > 0,
                    "entities": irrigation_entities,
                },
                "alarms": {
                    "count": len(alarm_entities),
                    "enabled": len(alarm_entities) > 0,
                    "entities": alarm_entities,
                },
                "gates": {
                    "count": len(gate_entities),
                    "enabled": len(gate_entities) > 0,
                    "entities": gate_entities,
                },
                "modbus": {
                    "count": len(modbus_entities),
                    "enabled": len(modbus_entities) > 0,
                    "entities": modbus_entities,
                },
            },
            "areas": areas,
        }
    except Exception:
        _LOGGER.exception("Error in dashboard_meta")
        raise


@router.get("/generate")
async def dashboard_generate(
    manager: Manager = Depends(get_manager),
    types: str = Query(
        default="outputs",
        description="Comma-separated entity types: outputs,covers,groups,irrigation,alarms,gates,modbus",
    ),
    area: str | None = Query(default=None, description="Area filter, null = all areas"),
    exclude_ids: str | None = Query(default=None, description="Comma-separated entity IDs to exclude"),
):
    """Generate HA Sections dashboard YAML per area.

    Returns a list of area sections, each with its own YAML snippet
    ready for individual copy-to-clipboard.

    Args:
        types: Comma-separated list of entity types to include.
        area: Optional area filter. None = all areas.
        exclude_ids: Optional comma-separated list of entity IDs to exclude.

    Returns:
        Dict with 'sections' list (per-area YAML blocks) and 'summary'.
    """
    serial = manager.config_helper.serial_number
    selected_types = [t.strip() for t in types.split(",")]
    user_excluded = {e.strip() for e in exclude_ids.split(",")} if exclude_ids else set()

    all_area_sections: list[dict[str, list[dict]]] = []
    summary: dict[str, int] = {}

    # Collect irrigation output IDs to exclude from general output export
    irrigation_ids = _get_irrigation_output_ids(manager)
    combined_exclude = irrigation_ids | user_excluded

    if "outputs" in selected_types:
        all_outputs = manager.outputs.get_all_outputs()
        sections = _generate_output_cards_by_area(
            all_outputs,
            serial,
            exclude_ids=combined_exclude,
        )
        all_area_sections.append(sections)
        summary["outputs"] = sum(
            1
            for oid, o in all_outputs.items()
            if oid not in combined_exclude and getattr(o, "output_type", None) not in (NONE, COVER, None)
        )

    if "covers" in selected_types:
        all_covers = manager.covers.get_all_covers()
        # Filter user-excluded covers
        filtered_covers = {k: v for k, v in all_covers.items() if k not in user_excluded}
        sections = _generate_cover_cards_by_area(filtered_covers, serial)
        all_area_sections.append(sections)
        summary["covers"] = len(filtered_covers)

    if "groups" in selected_types:
        all_groups = manager.outputs.get_all_output_groups()
        filtered_groups = {k: v for k, v in all_groups.items() if k not in user_excluded}
        sections = _generate_group_cards_by_area(filtered_groups, serial)
        all_area_sections.append(sections)
        summary["groups"] = len(filtered_groups)

    if "alarms" in selected_types and hasattr(manager, "templates"):
        all_alarms = [p for p in manager.templates.alarm_manager.items if p.id not in user_excluded]
        if all_alarms:
            sections = _generate_alarm_cards_by_area(all_alarms, serial)
            all_area_sections.append(sections)
            summary["alarms"] = len(all_alarms)

    if "gates" in selected_types and hasattr(manager, "templates"):
        all_gates = [g for g in manager.templates.gate_manager.items if g.id not in user_excluded]
        if all_gates:
            sections = _generate_gate_cards_by_area(all_gates, serial)
            all_area_sections.append(sections)
            summary["gates"] = len(all_gates)

    # Merge area-based sections
    merged = _merge_sections(*all_area_sections) if all_area_sections else {}

    # Filter by area if specified (supports comma-separated list)
    if area:
        area_ids = {a.strip().lower() for a in area.split(",")}
        filtered: dict[str, list[dict]] = {}
        for area_name, cards in merged.items():
            area_key = area_name.lower().replace(" ", "_")
            if area_key in area_ids or area_name.lower() in area_ids:
                filtered[area_name] = cards
        merged = filtered

    # Build per-area response sections with breakdown
    result_sections: list[dict] = []
    for area_name, cards in merged.items():
        # Count entities by type from heading subtitles
        breakdown: dict[str, int] = {}
        current_type: str | None = None
        for card in cards:
            if card.get("type") == "heading":
                hs = card.get("heading_style", "")
                heading_text = card.get("heading", "")
                if hs == "subtitle":
                    current_type = heading_text
                elif hs == "title":
                    current_type = None
            elif card.get("type") == "tile" and current_type:
                breakdown[current_type] = breakdown.get(current_type, 0) + 1

        # If no subtitle-based breakdown (e.g. covers), count all tiles
        if not breakdown:
            tile_count = sum(1 for c in cards if c.get("type") == "tile")
            if tile_count > 0:
                # Detect cover vs other from entity_id
                entity = cards[-1].get("entity", "") if cards else ""
                if entity.startswith("cover."):
                    breakdown["🪟 Covers"] = tile_count
                else:
                    breakdown["entities"] = tile_count

        entity_count = sum(1 for c in cards if c.get("type") != "heading")
        area_yaml = cards_to_yaml(cards)
        result_sections.append(
            {
                "area": area_name,
                "yaml": area_yaml,
                "entity_count": entity_count,
                "breakdown": breakdown,
            }
        )

    # Add irrigation sections (per controller, not per area)
    if "irrigation" in selected_types and hasattr(manager, "irrigation"):
        from boneio.webui.routes.irrigation import _generate_irrigation_dashboard_cards

        controllers = manager.irrigation.controllers
        summary["irrigation"] = len(controllers)
        for ctrl in controllers.values():
            irr_cards = _generate_irrigation_dashboard_cards(ctrl, serial)
            ctrl_name = getattr(ctrl, "name", ctrl.id)
            entity_count = sum(1 for c in irr_cards if c.get("type") != "heading")
            zones = getattr(ctrl, "zones", [])
            breakdown = {"🌿 Zones": len(zones)} if zones else {"🌿 Irrigation": entity_count}
            result_sections.append(
                {
                    "area": f"🌿 {ctrl_name}",
                    "yaml": cards_to_yaml(irr_cards),
                    "entity_count": entity_count,
                    "breakdown": breakdown,
                }
            )

    # Add modbus device sections (per device, not per area)
    if "modbus" in selected_types and hasattr(manager, "modbus"):
        all_coordinators = (
            manager.modbus.get_all_coordinators() if hasattr(manager.modbus, "get_all_coordinators") else {}
        )
        filtered_coords = {k: v for k, v in all_coordinators.items() if k not in user_excluded}
        modbus_sections = _generate_modbus_cards(filtered_coords, serial)
        result_sections.extend(modbus_sections)
        summary["modbus"] = len(filtered_coords)

    if not result_sections:
        return {
            "sections": [],
            "summary": {},
        }

    return {
        "sections": result_sections,
        "summary": summary,
    }
