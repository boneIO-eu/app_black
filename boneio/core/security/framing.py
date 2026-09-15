"""Who may embed the panel, as a list rather than a CSP string.

``frame-ancestors`` is written by hand in config.yaml, and its syntax punishes
that: the keyword is ``'self'`` *with* the quotes, because bare ``self`` is a
host name, and YAML strips single quotes on the way in. Getting it wrong
produces a directive that is still valid and means something else — visible
only in a browser console.

So the config holds a list of plain tokens and this module turns them into the
directive::

    web:
      security:
        frame_ancestors:
          - self
          - https://homeassistant.local:8123

A single string is still accepted, because that is what 1.6 wrote before this
and what anyone following the old documentation will have. It is split on
whitespace and the quotes are stripped, so both spellings land in the same
place.
"""

from __future__ import annotations

from typing import Any

#: Applied when config.yaml says nothing about framing. ``self`` alone is both
#: the secure answer and what the boneIO Black add-on for Home Assistant needs:
#: the add-on proxies each controller, so the framed page is served on Home
#: Assistant's own origin. See :mod:`boneio.webui.security_headers`.
DEFAULT_FRAME_ANCESTORS: tuple[str, ...] = ("self",)

#: Tokens that are keywords rather than addresses. CSP spells them quoted; the
#: config spells them plainly, and either is accepted on the way in.
_KEYWORDS = frozenset({"self", "none"})

#: Permits every site. Kept as its own token because it is the one value that
#: makes every other entry in the list meaningless.
WILDCARD = "*"


def normalize(raw: Any) -> tuple[str, ...]:
    """Read a configured value as a list of plain tokens.

    Args:
        raw: What config.yaml holds — a list, a whitespace-separated string,
            or None when the setting is absent.

    Returns:
        The tokens, in order, without duplicates. Empty when the setting is
        present but says nothing, which the caller treats as unconfigured.
    """
    if raw is None:
        return ()

    items: list[Any]
    if isinstance(raw, str):
        items = raw.split()
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        return ()

    tokens: list[str] = []
    for item in items:
        # Strip the quotes CSP wants, so a value copied from an old config or
        # from the header itself reads the same as one typed plainly.
        token = str(item).strip().strip("'\"").strip()
        if not token:
            continue
        lowered = token.lower()
        if lowered in _KEYWORDS:
            token = lowered
        if token not in tokens:
            tokens.append(token)
    return tuple(tokens)


def effective(raw: Any) -> tuple[str, ...]:
    """The tokens actually in force, falling back to the default.

    Args:
        raw: What config.yaml holds.

    Returns:
        The configured tokens, or :data:`DEFAULT_FRAME_ANCESTORS`.
    """
    return normalize(raw) or DEFAULT_FRAME_ANCESTORS


def to_csp(tokens: tuple[str, ...] | list[str]) -> str:
    """Render tokens as the value of a ``frame-ancestors`` directive.

    Args:
        tokens: Plain tokens, as :func:`normalize` produces.

    Returns:
        The directive value, with keywords quoted the way CSP requires.
    """
    return " ".join(f"'{t}'" if t in _KEYWORDS else t for t in tokens)


def is_unrestricted(tokens: tuple[str, ...] | list[str]) -> bool:
    """Whether these tokens let any site embed the panel.

    Args:
        tokens: Plain tokens.

    Returns:
        True if the wildcard is present, wherever it sits in the list.
    """
    return WILDCARD in tokens
