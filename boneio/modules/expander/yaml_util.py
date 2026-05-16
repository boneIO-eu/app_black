"""Pure helpers for expander output handling in ``!include_files`` configurations.

These functions are stateless and side-effect free. They form the domain
layer of the expander module — file IO and FastAPI handling live in
``routes.py`` and the orchestration in ``boneio/core/config/yaml_util.py``
delegates here.
"""

from __future__ import annotations

EXPANDER_PREFIX = "EX_"


def is_expander_output(item: dict) -> bool:
    """Single source of truth for detecting expander outputs.

    Accepts a dict with ``id`` and/or ``boneio_output`` keys.
    """
    value = item.get("id") or item.get("boneio_output") or ""
    return str(value).startswith(EXPANDER_PREFIX)


def split_outputs_for_includes(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Partition outputs into ``(board_outputs, expander_outputs)``.

    Used by ``update_config_section`` when ``output:`` is declared via
    ``!include_files`` — board outputs go to the first file, expander
    outputs go to the remaining files.
    """
    board: list[dict] = []
    expander: list[dict] = []
    for item in items:
        if is_expander_output(item):
            expander.append(item)
        else:
            board.append(item)
    return board, expander


def dedup_outputs_prefer_named(items: list[dict]) -> list[dict]:
    """Deduplicate outputs by id/boneio_output, preferring user-edited entries.

    When the same output appears multiple times in a payload (legacy split-write
    bugs caused this), keep the entry that has a ``name`` field set — that's the
    user-edited one. Bare duplicates without ``name`` are stale.
    """
    seen: dict[str, dict] = {}
    for item in items:
        oid = item.get("id") or item.get("boneio_output")
        if not oid:
            continue
        existing = seen.get(oid)
        if existing is None:
            seen[oid] = item
        elif ("name" in item) and ("name" not in existing):
            seen[oid] = item
        elif ("name" in item) and ("name" in existing) and len(item) > len(existing):
            seen[oid] = item
    return list(seen.values())


def filter_out_expander(items: list[dict]) -> list[dict]:
    """Return a new list with all expander (EX_*) entries removed."""
    return [item for item in items if not is_expander_output(item)]
