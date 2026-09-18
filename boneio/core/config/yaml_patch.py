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
import re
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


#: Tokens matching this are written bare, so the file reads the way someone
#: would type it. Deliberately narrow: it starts with a letter, so `*` — which
#: YAML reads as an alias reference and rejects outright — never qualifies, and
#: it admits no whitespace, so the `": "` that would turn an entry into a
#: mapping cannot occur.
_PLAIN_ITEM = re.compile(r"^[A-Za-z][A-Za-z0-9._:/@%+~=&?-]*$")

#: Words YAML reads as something other than a string, so an entry spelling one
#: of them must be quoted or it stops being text. `none` is deliberately absent
#: — YAML's null is `null` or `~`, and `none` is the CSP keyword, which would
#: look wrong quoted beside a bare `self`.
_YAML_WORDS = frozenset({"true", "false", "yes", "no", "on", "off", "null"})


def item_scalar(value: str) -> str:
    """Render a list entry, quoting only when YAML would read it wrongly.

    The list form exists so config.yaml reads as someone would write it, which
    quoting every entry undoes. Anything that is not plainly a word or an
    address is still quoted.

    Args:
        value: The entry to write.

    Returns:
        A bare or double-quoted YAML scalar.
    """
    if _PLAIN_ITEM.match(value) and value.lower() not in _YAML_WORDS:
        return value
    return quote_scalar(value)


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


def set_block_list(
    config_file: str | Path, path: tuple[str, ...], field: str, items: list[str]
) -> None:
    """Replace a field with a block list, creating the section if needed.

    ``update_yaml_field`` writes ``key: value`` on one line, which cannot
    express the shape config.yaml should hold for something people edit::

        security:
          frame_ancestors:
            - self
            - https://homeassistant.local:8123

    Anything already stored under the field — a scalar, or an older list — is
    replaced whole. Everything around it, comments included, is untouched.

    Args:
        config_file: Path to config.yaml.
        path: Section path, outermost first, e.g. ``("web", "security")``.
        field: Field name to write.
        items: List entries, written as double-quoted scalars.

    Raises:
        YamlPatchError: If the section cannot be created — see
            :func:`ensure_section`.
    """
    ensure_section(config_file, path)

    file_path = Path(config_file)
    lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)

    field_indent = len(path) * len(INDENT)
    block = f"{INDENT * len(path)}{field}:\n" + "".join(
        f"{INDENT * (len(path) + 1)}- {item_scalar(item)}\n" for item in items
    )

    depth = 0
    parent_indent = -1
    start = None
    end = None

    for index, line in enumerate(lines):
        parsed = _line_key(line)

        if start is not None:
            # Inside the old value: its own entries are indented past the
            # field, and anything at or left of it belongs to someone else.
            stripped = line.strip()
            indent = len(line) - len(line.lstrip())
            if stripped and indent <= field_indent:
                end = index
                break
            continue

        if parsed is None:
            continue
        key, indent, rest = parsed

        if depth == len(path) and key == field and indent == field_indent:
            start = index
            continue

        if depth and indent <= parent_indent:
            break

        if depth < len(path) and key == path[depth] and indent == depth * len(INDENT):
            depth += 1
            parent_indent = indent
            del rest

    if start is None:
        # ensure_section guarantees the section exists, so the field is simply
        # new: it goes at the top of the section, where a reader looks first.
        insert_at = _section_body_start(lines, path)
        lines.insert(insert_at, block)
    else:
        lines[start : (end if end is not None else len(lines))] = [block]

    file_path.write_text("".join(lines), encoding="utf-8")
    _LOGGER.info("Wrote %s.%s (%d entries)", ".".join(path), field, len(items))


def _section_body_start(lines: list[str], path: tuple[str, ...]) -> int:
    """The index just after a section's own header line.

    Args:
        lines: File lines.
        path: Section path, outermost first.

    Returns:
        Index at which the section's contents begin.
    """
    depth = 0
    for index, line in enumerate(lines):
        parsed = _line_key(line)
        if parsed is None:
            continue
        key, indent, _ = parsed
        if key == path[depth] and indent == depth * len(INDENT):
            depth += 1
            if depth == len(path):
                return index + 1
    return len(lines)


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
            # Back up over the blank lines that separated it from what follows,
            # so the new block joins the section rather than being stranded
            # past its own whitespace.
            insert_at = index
            while insert_at > 0 and not lines[insert_at - 1].strip():
                insert_at -= 1
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


def _find_section_line(lines: list[str], path: tuple[str, ...]) -> int | None:
    """Index of the line declaring a nested key, or None if it is not there.

    Args:
        lines: File lines.
        path: Section path, outermost first.

    Returns:
        The index of the key's own line, or None.
    """
    depth = 0
    for index, line in enumerate(lines):
        parsed = _line_key(line)
        if parsed is None:
            continue
        key, indent, _ = parsed
        if depth and indent <= (depth - 1) * len(INDENT):
            return None
        if key == path[depth] and indent == depth * len(INDENT):
            depth += 1
            if depth == len(path):
                return index
    return None


def has_section(config_file: str | Path, path: tuple[str, ...]) -> bool:
    """Whether a nested key is present in the file.

    Separate from :func:`remove_section` so a caller can find out before doing
    anything irreversible — such as writing a backup copy over the one it made
    the last time it was asked.

    Args:
        config_file: Path to config.yaml.
        path: Section path, outermost first.

    Returns:
        True when the key is there.

    Raises:
        YamlPatchError: If the path is empty.
    """
    if not path:
        raise YamlPatchError("No section path given.")
    lines = Path(config_file).read_text(encoding="utf-8").splitlines(keepends=True)
    return _find_section_line(lines, path) is not None


def remove_section(config_file: str | Path, path: tuple[str, ...]) -> bool:
    """Delete a nested mapping key and everything under it.

    Written for one job: taking the pre-1.6 ``web.auth`` block out of a
    configuration after its account has been migrated into the hashed store.
    Nothing reads it any more, and it still holds the owner's password in
    plain text — in the file, and in every backup and diagnostic bundle made
    since.

    Line-based rather than a parse-and-dump, for the usual reason: the file
    belongs to the owner, and round-tripping it through a YAML library would
    return their comments, ordering and ``!include`` directives as something
    they did not write.

    Comment lines immediately above the key are removed with it. They describe
    the block, and leaving them behind stranded over an unrelated setting is
    worse than taking one comment too many.

    Args:
        config_file: Path to config.yaml.
        path: Section path, outermost first, e.g. ``("web", "auth")``.

    Returns:
        True if something was removed, False if the key was not there.

    Raises:
        YamlPatchError: If the path is empty.
    """
    if not path:
        raise YamlPatchError("No section path given.")

    file_path = Path(config_file)
    lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)

    start = _find_section_line(lines, path)
    if start is None:
        return False
    key_indent = len(lines[start]) - len(lines[start].lstrip())

    # Everything indented under the key belongs to it, blank lines included
    # while more indented content follows.
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if not line.strip():
            following = next(
                (i for i in range(end + 1, len(lines)) if lines[i].strip()), None
            )
            if following is None:
                break
            next_indent = len(lines[following]) - len(lines[following].lstrip())
            if next_indent <= key_indent:
                break
            end += 1
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= key_indent:
            break
        end += 1

    # Take the comment block sitting directly on top of it.
    while start > 0:
        above = lines[start - 1].strip()
        if above.startswith("#"):
            start -= 1
            continue
        break

    del lines[start:end]
    file_path.write_text("".join(lines), encoding="utf-8")
    return True
