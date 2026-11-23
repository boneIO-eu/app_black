"""Migration v8: Remove what never ran and the section models refuse.

Cerberus loaded these; the section models that check config.yaml from 1.7
do not. Each one did nothing at runtime, so removing it changes nothing the
controller does:

- an action with no ``action``, or without a field its type needs (Cerberus'
  ``required_if`` only checked fields that were present);
- ``pin`` on an input that names a ``boneio_input`` — the board mapping
  writes its own pin over it;
- a Modbus ``update_interval`` under a second, which the coordinator never
  honoured, raised to ``1s``.

Before:
    event:
      - boneio_input: in_01
        pin: P8_37
        actions:
          single:
            - action: output
            - boneio_output: out_01
After:
    event:
      - boneio_input: in_01
        actions:
          single: []

Anything else the models refuse is left for the recovery panel: a fix that
needs a guess at what was meant is not a migration's to make. The files are
edited on lines, so comments and ``!secret`` survive; each changed file is
copied to ``backups/<name>.pre-v8`` first, and an edit that does not read
back as intended is undone.
"""

from __future__ import annotations

import functools
import logging
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from boneio.core.atomic_file import write_atomically
from boneio.core.config.migrations import register_migration

_LOGGER = logging.getLogger(__name__)

_ACTION_SECTIONS = ("event", "binary_sensor", "remote_inputs", "virtual_switch", "schedule")
_INPUT_SECTIONS = ("event", "binary_sensor")
_DROP = object()


@functools.cache
def _action_adapter() -> Any:
    from pydantic import TypeAdapter

    from boneio.core.config.models.inputs import Action

    return TypeAdapter(Action)


def _dead_action(action: Any) -> bool:
    """An action the model refuses only for a field of its own it lacks.

    A gap deeper down — a condition without its ``type`` — is not one: the
    action itself ran, so the recovery panel reports it instead.
    """
    from pydantic import ValidationError

    if not isinstance(action, dict):
        return False
    try:
        _action_adapter().validate_python(action)
    except ValidationError as err:
        # (type tag, field) is a field of the action itself.
        return all(e["type"] == "union_tag_not_found" or (e["type"] == "missing" and len(e["loc"]) == 2)
                   for e in err.errors())
    return False


def _under_a_second(value: Any) -> bool:
    from boneio.core.config.coerce import positive_time_period

    try:
        return positive_time_period(value if isinstance(value, (int, float)) else str(value)).total_seconds < 1
    except Exception:  # noqa: BLE001 - not a period at all: the model reports it
        return False


def _fixes(doc: dict) -> list[tuple[tuple, Any]]:
    """What to change, as (path from the document root, new value or _DROP).

    A list whose every item goes becomes ``[]`` rather than losing its key.
    """
    fixes: list[tuple[tuple, Any]] = []
    for section in _ACTION_SECTIONS:
        for i, item in enumerate(doc.get(section) or []):
            actions = item.get("actions") if isinstance(item, dict) else None
            lists = (
                [((k,), v) for k, v in actions.items()] if isinstance(actions, dict)
                else [((), actions)] if isinstance(actions, list) else []
            )
            for key, entries in lists:
                if not isinstance(entries, list):
                    continue
                dead = [j for j, action in enumerate(entries) if _dead_action(action)]
                at = (section, i, "actions", *key)
                if dead and len(dead) == len(entries):
                    fixes.append((at, []))
                else:
                    fixes += [((*at, j), _DROP) for j in dead]
    for section in _INPUT_SECTIONS:
        for i, item in enumerate(doc.get(section) or []):
            if isinstance(item, dict) and item.get("boneio_input") and "pin" in item:
                fixes.append(((section, i, "pin"), _DROP))
    for i, device in enumerate(doc.get("modbus_devices") or []):
        if isinstance(device, dict) and "update_interval" in device and _under_a_second(device["update_interval"]):
            fixes.append((("modbus_devices", i, "update_interval"), "1s"))
    return fixes


def _apply(doc: dict, fixes: list[tuple[tuple, Any]]) -> None:
    # From the last index down, so a drop does not move what is still to come.
    for path, value in sorted(fixes, key=lambda f: [(isinstance(p, str), p) for p in f[0]], reverse=True):
        parent = doc
        for part in path[:-1]:
            parent = parent[part]
        if value is _DROP:
            del parent[path[-1]]
        else:
            parent[path[-1]] = value


@register_migration(
    version=8,
    name="Remove dead actions, pins the board overrides, sub-second Modbus intervals",
    migrate_file=lambda config_file: _persist(config_file),
)
def migrate_v8_dead_entries(doc: dict) -> dict:
    """Make the in-memory config what the files will hold after _persist."""
    fixes = _fixes(doc)
    for path, value in fixes:
        _LOGGER.warning(
            "Config migration v8: %s %s",
            ".".join(map(str, path)),
            "removed (it did nothing)" if value is _DROP else f"set to {value!r}",
        )
    _apply(doc, fixes)
    return doc


# --------------------------------------------------------------- the files


def _node_at(root: yaml.Node, path: tuple) -> tuple[yaml.Node | None, yaml.Node | None]:
    """The node at ``path`` and, when it is a mapping value, its key node."""
    node, key_node = root, None
    for part in path:
        if isinstance(node, yaml.MappingNode) and isinstance(part, str):
            pair = next(((k, v) for k, v in node.value if k.value == part), None)
            if pair is None:
                return None, None
            key_node, node = pair
        elif isinstance(node, yaml.SequenceNode) and isinstance(part, int) and part < len(node.value):
            key_node, node = None, node.value[part]
        else:
            return None, None
        if node.tag.startswith("!"):  # an !include deeper down: not followed
            return None, None
    return node, key_node


def _end_line(lines: list[str], mark: yaml.Mark) -> int:
    """First line after a node: its end mark's line, unless the node ends inside it."""
    if mark.line >= len(lines) or not lines[mark.line][: mark.column].strip():
        return mark.line
    return mark.line + 1


def _block(lines: list[str], start: int, end: int) -> tuple[int, int]:
    """Comment and blank lines at the end belong to what follows, not to this."""
    while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    return start, end


def _change(lines: list[str], node: yaml.Node, key: yaml.Node | None, value: Any) -> tuple[int, int, list[str]] | None:
    """One fix as lines[start:end] = replacement, or None when it cannot be made safely."""
    if value is _DROP and key is None:  # a list item
        if not re.fullmatch(r"\s*-\s*", lines[node.start_mark.line][: node.start_mark.column]):
            return None
        start, end = _block(lines, node.start_mark.line, _end_line(lines, node.end_mark))
        return start, end, []
    if value is _DROP:  # a key of a mapping, written on its own line(s)
        start, end = _block(lines, key.start_mark.line, _end_line(lines, node.end_mark))
        before = lines[start][: key.start_mark.column]
        if "-" not in before:
            return start, end, []
        # It held the item's dash: the next line of the item takes it.
        if end >= len(lines) or len(lines[end]) - len(lines[end].lstrip()) != key.start_mark.column:
            return None
        return start, end + 1, [before + lines[end].lstrip()]
    if isinstance(node, yaml.ScalarNode) and node.start_mark.line == node.end_mark.line:
        row = lines[node.start_mark.line]
        return node.start_mark.line, node.start_mark.line + 1, [
            row[: node.start_mark.column] + str(value) + row[node.end_mark.column:]
        ]
    if value == [] and key is not None and isinstance(node, yaml.SequenceNode) and not node.flow_style:
        _, end = _block(lines, node.start_mark.line, _end_line(lines, node.end_mark))
        row = lines[key.start_mark.line]
        if key.start_mark.line != node.start_mark.line - 1 and lines[node.start_mark.line - 1].strip():
            return None  # something between the key and its list
        return key.start_mark.line, end, [re.sub(r"^(\s*(?:-\s+)?[^#\s][^#]*?:)", r"\1 []", row, count=1)]
    return None


def _persist(config_file: str) -> None:
    from boneio.core.config.yaml_util import load_yaml_file

    main = Path(config_file)
    doc = load_yaml_file(str(main))
    fixes = _fixes(doc)
    if not fixes:
        return

    # Each section lives in config.yaml or, whole, in the file it !includes.
    roots: dict[str, tuple[Path, yaml.Node]] = {}
    main_root = yaml.compose(main.read_text(encoding="utf-8"), Loader=yaml.SafeLoader)
    for key, value in main_root.value if isinstance(main_root, yaml.MappingNode) else []:
        if value.tag == "!include" and (main.parent / value.value).is_file():
            path = main.parent / value.value
            roots[key.value] = (path, yaml.compose(path.read_text(encoding="utf-8"), Loader=yaml.SafeLoader))
        elif not value.tag.startswith("!"):
            roots[key.value] = (main, value)

    planned: dict[Path, list[tuple[tuple, yaml.Node, yaml.Node | None, Any]]] = {}
    for path, value in fixes:
        file, root = roots.get(path[0], (None, None))
        node, key = _node_at(root, path[1:]) if root is not None else (None, None)
        if node is None:
            _LOGGER.warning("Config migration v8: %s needs fixing by hand", ".".join(map(str, path)))
            continue
        planned.setdefault(file, []).append((path, node, key, value))

    originals: dict[Path, str] = {}
    applied: list[tuple[tuple, Any]] = []
    for file, file_fixes in planned.items():
        text = file.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        # Every range read off the file as it is, then applied bottom-up.
        changes = [_change(lines, node, key, value) for _, node, key, value in file_fixes]
        ranges = sorted((c[0], c[1]) for c in changes if c is not None)
        if None in changes or any(a[1] > b[0] for a, b in zip(ranges, ranges[1:])):
            _LOGGER.warning("Config migration v8: could not edit %s safely; it needs fixing by hand", file)
            continue
        for start, end, replacement in sorted(changes, reverse=True):  # type: ignore[type-var]
            lines[start:end] = replacement
        backup = main.parent / "backups" / f"{file.name}.pre-v8"
        backup.parent.mkdir(exist_ok=True)
        shutil.copy2(file, backup)
        write_atomically(file, "".join(lines))
        originals[file] = text
        applied += [(path, value) for path, _, _, value in file_fixes]

    _apply(doc, applied)
    if originals and load_yaml_file(str(main)) != doc:
        # The files do not read back as intended: put them back and let
        # start-up report what is wrong.
        for file, text in originals.items():
            write_atomically(file, text)
        _LOGGER.error("Config migration v8 did not apply cleanly; the files are as they were")
    elif originals:
        _LOGGER.warning("Config migration v8 changed %s (copies in backups/)", ", ".join(f.name for f in originals))
