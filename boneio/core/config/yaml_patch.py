"""Narrow, comment-preserving edits to config.yaml.

The panel writes single settings into a file people also edit by hand, full of
comments and ``!secret`` references. Round-tripping it through a YAML parser
would lose both, so edits are made on lines — the same reason
:func:`boneio.core.config.yaml_util.update_yaml_field` works that way.

That function can only change a field in a section that already exists. This
adds the missing half: creating the section first, and quoting the value so it
survives the trip back through the parser.
"""

from __future__ import annotations

import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

#: Two spaces per level, matching the rest of the file and update_yaml_field.
INDENT = "  "


class YamlPatchError(Exception):
    """Raised when the file cannot be edited safely."""


def quote_scalar(value: str) -> str:
    """Render a string so YAML reads it back unchanged.

    Always double-quoted, which matters more than it looks: CSP keywords carry
    their own single quotes, and ``frame_ancestors: 'self'`` parses as the bare
    word ``self`` — a host name, not the keyword. The directive would then
    silently mean something else.

    Args:
        value: The string to write.

    Returns:
        A double-quoted YAML scalar.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _line_key(line: str) -> tuple[str, int, str] | None:
    """Split a line into (key, indent, remainder), or None if it is not a key.

    Args:
        line: One line of the file.

    Returns:
        Tuple of key, indent width and whatever followed the colon.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or ":" not in stripped:
        return None
    key, _, rest = stripped.partition(":")
    if not key or key.startswith("-"):
        return None
    return key.strip(), len(line) - len(line.lstrip()), rest.strip()


def ensure_section(config_file: str | Path, path: tuple[str, ...]) -> bool:
    """Make sure a nested mapping exists, creating the missing levels.

    Args:
        config_file: Path to config.yaml.
        path: Section path, outermost first, e.g. ``("web", "security")``.

    Returns:
        True if the file was changed, False if the section was already there.

    Raises:
        YamlPatchError: If a level exists but is not an editable mapping —
            most importantly ``web: !include web.yaml``, where writing here
            would put the setting in a file nothing reads.
    """
    if not path:
        raise YamlPatchError("No section path given.")

    file_path = Path(config_file)
    lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)

    depth = 0
    parent_indent = -1
    insert_at = len(lines)

    for index, line in enumerate(lines):
        parsed = _line_key(line)
        if parsed is None:
            continue
        key, indent, rest = parsed

        if depth and indent <= parent_indent:
            # Left the section we were inside without finding the next level.
            insert_at = index
            break

        if depth < len(path) and key == path[depth] and indent == depth * len(INDENT):
            if rest and not rest.startswith("#"):
                raise YamlPatchError(
                    f"'{'.'.join(path[: depth + 1])}' is not a plain section in "
                    f"config.yaml (it reads '{rest}'). Edit that file directly."
                )
            depth += 1
            parent_indent = indent
            insert_at = index + 1
            if depth == len(path):
                return False

    missing = path[depth:]
    block = "".join(
        f"{INDENT * (depth + offset)}{key}:\n" for offset, key in enumerate(missing)
    )
    lines.insert(insert_at, block)
    file_path.write_text("".join(lines), encoding="utf-8")
    _LOGGER.info("Created section '%s' in %s", ".".join(path), file_path)
    return True
