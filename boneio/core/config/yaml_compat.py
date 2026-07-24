"""PyYAML backend selection.

PyYAML ships two implementations: a pure-Python parser/emitter and a much
faster one backed by the C library ``libyaml`` (``CSafeLoader`` /
``CSafeDumper``). The C backend is roughly 10x faster at parsing and 5x
faster at emitting, which matters a lot on the BeagleBone Black where the
pure-Python parser needs several seconds for the boneIO schema.

This module exposes ``FastSafeLoader`` / ``FastSafeDumper`` which resolve to
the C implementation when available and fall back to the pure-Python one
otherwise. It intentionally imports nothing besides ``yaml`` so it can also
be used by standalone tooling (e.g. the schema converter run in CI).
"""

from __future__ import annotations

import logging

try:
    from yaml import CSafeDumper as FastSafeDumper
    from yaml import CSafeLoader as FastSafeLoader

    HAS_LIBYAML = True
except ImportError:  # pragma: no cover - depends on the installed PyYAML build
    from yaml import SafeDumper as FastSafeDumper  # type: ignore[assignment]
    from yaml import SafeLoader as FastSafeLoader  # type: ignore[assignment]

    HAS_LIBYAML = False

_LOGGER = logging.getLogger(__name__)


def log_yaml_backend() -> None:
    """Log which PyYAML backend is in use.

    Call this once during startup so slow installations (PyYAML built
    without libyaml) can be spotted in the logs.
    """
    if HAS_LIBYAML:
        _LOGGER.debug("Using libyaml (C) PyYAML backend")
        return
    _LOGGER.warning(
        "PyYAML was built without libyaml — YAML parsing will be ~10x slower. "
        "Install libyaml-dev and reinstall PyYAML to speed up config handling."
    )
