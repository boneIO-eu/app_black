"""Save-time checks on GPIO input fields, for the WebUI config routes.

Standalone module (no FastAPI / router dependencies) so it can be imported
in unit tests without triggering python-multipart or other optional deps.
"""

from __future__ import annotations

from typing import Any

from boneio.const import BOUNCE_TIME_MAX_MS
from boneio.core.utils.timeperiod import parse_time_to_ms


def bounce_time_ms(value: Any) -> int | None:
    """A bounce_time in milliseconds, whatever shape it arrives in.

    The panel posts a bare number of ms, a hand-written config holds
    ``"120ms"``, the running config a TimePeriod, and the JSON the panel was
    served a TimePeriod flattened to a dict — which an untouched row posts
    back as it got it.
    """
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        if value.get("_total_in_seconds") is not None:
            return int(float(value["_total_in_seconds"]) * 1000)
        if value.get("milliseconds") is not None:
            return int(float(value["milliseconds"]))
        return None
    return parse_time_to_ms(value, None)


def _entry_key(entry: dict) -> str:
    return str(entry.get("boneio_input") or entry.get("id") or entry.get("pin") or "").lower()


def validate_bounce_times(entries: list, stored: list | None) -> list[str]:
    """Errors for bounce times past the limit that this save introduces.

    A section is saved whole, so refusing every long value would lock the
    whole section for anyone whose config already had one. A value the same
    input already stored passes; a new or changed one does not. With nothing
    to compare against (``stored`` is None) nothing is refused.
    """
    if stored is None:
        return []
    already = {
        _entry_key(e): bounce_time_ms(e.get("bounce_time"))
        for e in stored
        if isinstance(e, dict)
    }
    errors: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ms = bounce_time_ms(entry.get("bounce_time"))
        if ms is None or ms <= BOUNCE_TIME_MAX_MS:
            continue
        key = _entry_key(entry)
        if already.get(key) == ms:
            continue
        errors.append(
            f"{key or entry.get('name') or '?'}: bounce_time {ms}ms is over "
            f"the {BOUNCE_TIME_MAX_MS}ms limit."
        )
    return errors


def has_long_bounce_time(entries: list) -> bool:
    """Whether any entry asks for more than the limit — the cheap check first."""
    return any(
        isinstance(e, dict) and (bounce_time_ms(e.get("bounce_time")) or 0) > BOUNCE_TIME_MAX_MS
        for e in entries
    )
