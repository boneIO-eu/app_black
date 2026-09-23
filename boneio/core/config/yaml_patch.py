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


#: A field that defers to secrets.yaml, with the name it defers under. The
#: trailing part is deliberately greedy about nothing: a reference is one word,
#: and anything else is a value that happens to start with the tag.
_SECRET_REFERENCE = re.compile(r"^!secret\s+(\S+)$")

#: A section kept in a file of its own.
_INCLUDE_REFERENCE = re.compile(r"^!include\s+(\S+)$")


def resolve_field(config_file: str | Path, path: tuple[str, ...]) -> tuple[Path, tuple[str, ...]]:
    """Follow a top-level ``!include`` to the file that really holds a field.

    Every shipped controller has ``mqtt: !include mqtt.yaml`` — that file is
    the per-device one, and the broker password is the thing it exists for. A
    line edit against config.yaml would find no ``mqtt:`` block to edit there
    and create one, which YAML then reads instead of the include: the password
    would be written twice, in two places, and the device would use neither the
    old one nor reliably the new.

    Only the outermost level is followed, because that is the only level the
    loader can put in another file.

    Args:
        config_file: Path to config.yaml.
        path: Field path, outermost first, e.g. ``("mqtt", "password")``.

    Returns:
        The file to edit, and the path within it. Inside an included file the
        contents *are* the section, so the first element is dropped.
    """
    file_path = Path(config_file)
    if len(path) < 2:
        return file_path, path

    lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    index = _find_section_line(lines, path[:1])
    if index is None:
        return file_path, path
    parsed = _line_key(lines[index])
    if parsed is None:
        return file_path, path
    match = _INCLUDE_REFERENCE.match(_strip_comment(parsed[2]))
    if match is None:
        return file_path, path
    # Same rule as BoneIOLoader.include: relative to the file that names it.
    return file_path.parent / match.group(1), path[1:]


def _strip_comment(rest: str) -> str:
    """Drop a trailing comment from a line's value.

    Only used on lines being *read* to find a ``!secret`` reference, where the
    value is one word, so the ``#`` cannot be part of it.

    Args:
        rest: Whatever followed the colon.

    Returns:
        The value, without a trailing comment.
    """
    return rest.split("#", 1)[0].strip()


def secret_reference(config_file: str | Path, path: tuple[str, ...]) -> str | None:
    """The name a field defers to in secrets.yaml, if it defers at all.

    ``mqtt.password: !secret mqtt_pass`` means the password lives in
    secrets.yaml — quite possibly because config.yaml is in somebody's git
    repository. Writing the new password over the reference would put it there
    too, so a caller changing such a field has to know.

    Args:
        config_file: Path to config.yaml.
        path: Field path, outermost first, e.g. ``("mqtt", "password")``.

    A section kept in a file of its own is followed first, so the answer is
    about the line the device actually reads.

    Returns:
        The secret's name, or None when the field holds a plain value or is
        not in the file.
    """
    file_path, path = resolve_field(config_file, path)
    if not file_path.is_file():
        return None
    lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    index = _find_section_line(lines, path)
    if index is None:
        return None
    parsed = _line_key(lines[index])
    if parsed is None:
        return None
    match = _SECRET_REFERENCE.match(_strip_comment(parsed[2]))
    return match.group(1) if match else None


def set_scalar(config_file: str | Path, path: tuple[str, ...], value: str) -> None:
    """Write a single value, creating the field if it is not there.

    ``update_yaml_field`` does nearly this, but writes the value unquoted and
    logs it — neither of which a password survives. Here the value is always a
    double-quoted scalar and never reaches the log.

    A section kept in a file of its own is followed first — every shipped
    controller keeps its mqtt section that way — so the value is written to
    the line the device actually reads.

    Args:
        config_file: Path to config.yaml.
        path: Field path, outermost first, e.g. ``("mqtt", "password")``.
        value: The value to store.

    Raises:
        YamlPatchError: If the section cannot be created — see
            :func:`ensure_section` — or if a section kept in its own file
            points at a file that is not there.
    """
    file_path, path = resolve_field(config_file, path)
    section, field = path[:-1], path[-1]
    if section:
        ensure_section(file_path, section)
    elif not file_path.is_file():
        # An include naming a file nothing created. Writing one here would
        # invent a section out of a typo.
        raise YamlPatchError(f"{file_path} does not exist.")

    lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    indent = INDENT * len(section)
    line = f"{indent}{field}: {quote_scalar(value)}\n"

    index = _find_section_line(lines, path)
    if index is not None:
        lines[index] = line
    elif section:
        lines.insert(_section_body_start(lines, section), line)
    else:
        # A file whose whole contents are the section: it has no header to
        # insert under, so the field goes at the end.
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(line)

    file_path.write_text("".join(lines), encoding="utf-8")
    # The value is the point of this function and stays out of the log.
    _LOGGER.info("Wrote %s in %s", ".".join(path), file_path.name)


def set_secret(secrets_file: str | Path, name: str, value: str) -> None:
    """Store a value in secrets.yaml, leaving every other secret alone.

    Args:
        secrets_file: Path to secrets.yaml.
        name: The secret's name.
        value: The value to store.

    Raises:
        YamlPatchError: If the file is missing. A reference pointing at a file
            that is not there is not something to paper over by creating one.
    """
    file_path = Path(secrets_file)
    if not file_path.is_file():
        raise YamlPatchError(f"{file_path} does not exist.")

    lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    line = f"{name}: {quote_scalar(value)}\n"

    for index, existing in enumerate(lines):
        parsed = _line_key(existing)
        if parsed is not None and parsed[0] == name and parsed[1] == 0:
            lines[index] = line
            break
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(line)

    file_path.write_text("".join(lines), encoding="utf-8")
    _LOGGER.info("Wrote the secret %s", name)
