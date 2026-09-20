"""Turning a name somebody typed into an identifier a machine can carry.

The identifier ends up in an MQTT topic, in Home Assistant's unique_id, in the
state file, and in whatever a condition or an action writes to refer to the
entity. So it has to be ASCII, lower case, and free of anything that means
something to a topic parser — while the name it came from is free text in
whatever language the house is run in.
"""

from __future__ import annotations

import re
import unicodedata

#: Letters that do not decompose under NFKD, so stripping combining marks
#: leaves them intact. Polish ``ł`` is the one that matters here; the rest of
#: the Polish set (ą ć ę ń ó ś ź ż) decomposes and needs no help.
_UNDECOMPOSABLE = {
    "ł": "l",
    "đ": "d",
    "ø": "o",
    "ß": "ss",
    "æ": "ae",
    "œ": "oe",
    "þ": "th",
}

_NOT_ALLOWED = re.compile(r"[^a-z0-9]+")


def slugify_id(name: str) -> str:
    """Make an identifier out of a display name.

    Folds accents, lowercases, and collapses everything that is not a letter
    or a digit into a single underscore.

    Args:
        name: The display name, in any language.

    Returns:
        The identifier, or ``""`` when the name has nothing usable in it —
        which the caller has to treat as "no id", not as a valid empty one.

    Examples:
        >>> slugify_id("Nie ma nas w domu")
        'nie_ma_nas_w_domu'
        >>> slugify_id("Wyjście główne")
        'wyjscie_glowne'
        >>> slugify_id("  Salon / Piętro 1  ")
        'salon_pietro_1'
    """
    text = name.strip().lower()
    for char, replacement in _UNDECOMPOSABLE.items():
        text = text.replace(char, replacement)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return _NOT_ALLOWED.sub("_", text).strip("_")


def resolve_id(entry: dict) -> str:
    """The identifier for one config entry: an explicit id, else its name.

    The precedence the rest of boneIO already uses (see the ADC sensors), made
    shareable. An explicit ``id`` exists so that the reference survives a
    rename: conditions, actions, the MQTT topic and the saved state all point
    at the id, so deriving it from a name means renaming breaks all four at
    once. Nobody has to set one, and almost nobody should.

    Args:
        entry: A config entry with ``id`` and/or ``name``.

    Returns:
        The identifier, or ``""`` when the entry has neither.
    """
    explicit = str(entry.get("id") or "").strip()
    if explicit:
        return explicit
    return slugify_id(str(entry.get("name") or ""))
