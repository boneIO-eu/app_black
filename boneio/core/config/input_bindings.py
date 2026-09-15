"""Generate default input bindings from a board's own output and cover config.

The first-run wizard offers to wire the physical inputs to whatever the board
actually has: relays, covers, or both. The board's output config is flashed at
assembly time and differs per model — a cover board's 32 pins are sixteen
up/down pairs with no plain relays at all — so nothing here invents hardware.
It reads what is configured and hands out the free inputs in order.

The planning is kept free of I/O so the allocation rules can be tested
directly; the route does the reading and writing.
"""

from __future__ import annotations

from typing import Any

# Bind inputs to relays, to covers, to both, or leave them alone.
INPUT_MODE_OUTPUTS = "outputs"
INPUT_MODE_COVERS = "covers"
INPUT_MODE_COVERS_AND_OUTPUTS = "covers_and_outputs"
INPUT_MODE_NONE = "none"

INPUT_MODES = (
    INPUT_MODE_OUTPUTS,
    INPUT_MODE_COVERS,
    INPUT_MODE_COVERS_AND_OUTPUTS,
    INPUT_MODE_NONE,
)

# A physical shutter switch is two buttons, and pressing the one that is
# already running should stop the cover rather than restart it — which is what
# TOGGLE_OPEN/TOGGLE_CLOSE do (see components/cover/cover.py).
COVER_ACTION_UP = "TOGGLE_OPEN"
COVER_ACTION_DOWN = "TOGGLE_CLOSE"


def resolve_cover_id(cover: dict[str, Any]) -> str:
    """Work out the id a cover will answer to.

    Mirrors CoverManager: an explicit id wins, otherwise it is derived from the
    two relays. The shipped cover configs carry no ids, so the derived form is
    the common case and actions must reference the same string.

    Args:
        cover: One entry of the ``cover`` config section.

    Returns:
        The cover's id.
    """
    explicit = cover.get("id")
    if explicit:
        return str(explicit)
    open_relay = str(cover.get("open_relay", ""))
    close_relay = str(cover.get("close_relay", ""))
    return f"cover_{open_relay}_{close_relay}".lower().replace(" ", "_")


def output_id(output: dict[str, Any]) -> str:
    """Work out the id an output will answer to.

    Mirrors OutputManager: an explicit id wins, otherwise ``boneio_output``.

    Args:
        output: One entry of the ``output`` config section.

    Returns:
        The output's id, or an empty string if the entry names neither.
    """
    return str(output.get("id") or output.get("boneio_output") or "")


def cover_relay_ids(covers: list[dict[str, Any]]) -> set[str]:
    """Collect the relays already driving a cover.

    Those pins are not free outputs: on a cover board every relay is half of a
    shutter, and binding a button straight to one would fight the cover logic.

    Args:
        covers: The ``cover`` config section.

    Returns:
        Lower-cased relay ids.
    """
    used: set[str] = set()
    for cover in covers:
        for key in ("open_relay", "close_relay"):
            relay = cover.get(key)
            if relay:
                used.add(str(relay).lower())
    return used


def _output_entry(input_id: str, target: str) -> dict[str, Any]:
    """One event entry whose single click toggles an output."""
    return {
        "name": input_id.upper(),
        "boneio_input": input_id,
        # Single click only: in practice almost every installation uses event
        # entities with one action, and double/long are left for the user.
        "actions": {"single": [{"action": "output", "boneio_output": target}]},
    }


def _cover_entry(input_id: str, target: str, action_cover: str) -> dict[str, Any]:
    """One event entry whose single click drives a cover one way."""
    return {
        "name": input_id.upper(),
        "boneio_input": input_id,
        "actions": {
            "single": [
                {"action": "cover", "boneio_cover": target, "action_cover": action_cover}
            ]
        },
    }


def plan_input_bindings(
    mode: str,
    available_inputs: list[str],
    taken_inputs: set[str],
    outputs: list[str],
    covers: list[str],
) -> list[dict[str, Any]]:
    """Hand out the free inputs to covers and/or outputs, in order.

    Args:
        mode: One of :data:`INPUT_MODES`.
        available_inputs: Every input the board has, in board order.
        taken_inputs: Inputs already spoken for elsewhere — binary sensors share
            the same pins as events, and duplicating one breaks both.
        outputs: Output ids to bind, in config order, cover relays excluded.
        covers: Cover ids to bind, in config order.

    Returns:
        Event entries, ready to become the ``event`` config section. Empty for
        ``none``, and short of the full list when the board runs out of inputs.

    Raises:
        ValueError: If ``mode`` is not recognised.
    """
    if mode not in INPUT_MODES:
        raise ValueError(f"Unknown input mode: {mode}")
    if mode == INPUT_MODE_NONE:
        return []

    lowered = {i.lower() for i in taken_inputs}
    free = iter([i for i in available_inputs if i.lower() not in lowered])

    entries: list[dict[str, Any]] = []

    if mode in (INPUT_MODE_COVERS, INPUT_MODE_COVERS_AND_OUTPUTS):
        for cover in covers:
            up = next(free, None)
            down = next(free, None)
            if up is None or down is None:
                # A cover with only an up button is worse than an unbound one,
                # so an odd input left over goes to the outputs pass instead.
                if up is not None:
                    free = iter([up])
                break
            entries.append(_cover_entry(up, cover, COVER_ACTION_UP))
            entries.append(_cover_entry(down, cover, COVER_ACTION_DOWN))

    if mode in (INPUT_MODE_OUTPUTS, INPUT_MODE_COVERS_AND_OUTPUTS):
        for output in outputs:
            candidate = next(free, None)
            if candidate is None:
                break
            entries.append(_output_entry(candidate, output))

    return entries


def board_input_ids(input_config: dict[str, Any]) -> list[str]:
    """Pull the input ids out of a board's input map.

    Args:
        input_config: Parsed ``boards/<version>/input.yaml``.

    Returns:
        Input ids in board order.
    """
    return list((input_config.get("input_mapping") or {}).keys())


def bindable_targets(config: dict[str, Any]) -> tuple[list[str], list[str]]:
    """What a given configuration offers to bind inputs to.

    Covers come from the ``cover`` section; outputs are the relays left once
    the ones already driving a cover are removed. On a cover board that leaves
    no outputs at all, which is correct — its pins are sixteen shutters, and a
    button bound straight to one would fight the cover logic that owns it.

    Args:
        config: The loaded configuration.

    Returns:
        ``(output_ids, cover_ids)`` in config order.
    """
    config = config or {}
    covers = [c for c in (config.get("cover") or []) if isinstance(c, dict)]
    cover_ids = [resolve_cover_id(c) for c in covers]
    used_relays = cover_relay_ids(covers)

    outputs = []
    for entry in config.get("output") or []:
        if not isinstance(entry, dict):
            continue
        oid = output_id(entry)
        if oid and oid.lower() not in used_relays:
            outputs.append(oid)
    return outputs, cover_ids


def taken_inputs(config: dict[str, Any]) -> set[str]:
    """Inputs already claimed by a binary sensor.

    Events and binary sensors share the physical pins — the shipped config
    puts two of them in binary_sensor.yaml — and duplicating one breaks both.

    Args:
        config: The loaded configuration.

    Returns:
        Lower-cased input ids.
    """
    claimed = set()
    for entry in (config or {}).get("binary_sensor") or []:
        if isinstance(entry, dict) and entry.get("boneio_input"):
            claimed.add(str(entry["boneio_input"]).lower())
    return claimed
