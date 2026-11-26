"""Learning mode: finding out which input is which button and which output is which lamp.

A person in the house says "I am going to press the button in the bathroom";
an AI agent waits here for the press, and to learn which output lights the
bathroom it switches candidates on for a moment while the person watches.

Two halves:

- What happened: one listener on the event bus keeps the last few minutes of
  presses and output changes in memory. A wait returns the presses after a
  point in time plus the outputs that switched right after them - which is
  also how a saved change is checked: press again, see the right output move.
  Nothing is stored on disk.
- Showing an output: switched to the other state for a few seconds and back.
  Only where that is harmless: a light, or a switch the person said may be
  switched; never a cover, valve, interlocked output or a pulse-driven switch
  (a gate, a bell), whose "on" is an action rather than a state.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from boneio.const import INPUT_SENSOR, LIGHT, OFF, ON, SWITCH
from boneio.webui.routes import config_core

router = APIRouter(prefix="/api/learn", tags=["learn"])

#: How long a press stays answerable, and how many events are kept at most.
KEEP_SECONDS = 300.0
_recent: deque[tuple[float, str, dict]] = deque(maxlen=200)
_waiters: set[asyncio.Future] = set()
#: After the first press, how long to keep listening: a double click, the
#: release of a binary sensor and the outputs the press switched all land in it.
SETTLE_SECONDS = 2.0
#: A relay pulsed for at most this long drives an impulse (bistable) relay:
#: each pulse flips the lamp, so showing it takes two pulses.
IMPULSE_MAX_SECONDS = 2.0
_identify_lock = asyncio.Lock()


def _manager():
    return config_core._get_app_state().manager


def _record(event: Any) -> None:
    """Event bus listener. Synchronous: the bus awaits it for every event."""
    now = time.time()
    if event.event_type == "input":
        # click_type None is a state resend after a reload, publish_only a
        # binary sensor state re-announced to Home Assistant: nobody pressed.
        if event.click_type is None or event.publish_only:
            return
        s = event.state
        _recent.append((now, "input", {
            "id": event.entity_id, "name": s.name, "click": event.click_type,
            "pin": s.pin, "boneio_input": s.boneio_input or None, "area": s.area,
            "section": _input_section(s.type, s.remote),
        }))
    elif event.event_type == "output":
        s = event.state
        _recent.append((now, "output", {"id": event.entity_id, "name": s.name, "state": s.state, "area": s.area}))
    else:
        return
    for waiter in _waiters:
        if not waiter.done():
            waiter.set_result(None)


def install() -> None:
    """Listen on the bus. Repeating it only replaces the same listeners."""
    bus = _manager().event_bus
    bus.add_event_listener(event_type="input", entity_id="", listener_id="learn_input", target=_record)
    bus.add_event_listener(event_type="output", entity_id="", listener_id="learn_output", target=_record)


def _input_section(input_type: str, remote: bool) -> str:
    if remote:
        return "remote_inputs"
    return "binary_sensor" if input_type == INPUT_SENSOR else "event"


def _presses(after: float, until: float = float("inf")) -> list[tuple[float, dict]]:
    return [(t, d) for t, kind, d in _recent if kind == "input" and after < t <= until]


def _summary(after: float) -> dict:
    """The presses after ``after``, by input, and what switched right after the first."""
    presses = _presses(after)
    first = presses[0][0]
    by_input: dict[str, dict] = {}
    for t, p in presses:
        entry = by_input.setdefault(p["id"], {**{k: v for k, v in p.items() if k != "click"},
                                               "clicks": [], "first_at": t})
        entry["clicks"].append(p["click"])
    switched = [
        {**d, "after_seconds": round(t - first, 2)}
        for t, kind, d in _recent
        if kind == "output" and first <= t <= first + SETTLE_SECONDS
    ]
    inputs = sorted(by_input.values(), key=lambda e: e["first_at"])
    for entry in inputs:
        entry["first_at"] = round(entry["first_at"], 3)
    return {"inputs": inputs, "outputs_switched": switched}


@router.get("/press")
async def wait_for_press(
    since: float | None = Query(None, description="Unix time; presses after it count. Default: 3 s ago."),
    timeout: float = Query(25.0, ge=1.0, le=55.0),
):
    """Wait for someone to press an input, then say which, and what it switched."""
    install()
    now = time.time()
    after = max(since if since is not None else now - 3.0, now - KEEP_SECONDS)
    deadline = time.monotonic() + timeout
    loop = asyncio.get_running_loop()
    while not _presses(after):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {"pressed": False, "cursor": round(time.time(), 3),
                    "detail": "Nothing was pressed. Call again with since=cursor to keep waiting."}
        waiter = loop.create_future()
        _waiters.add(waiter)
        try:
            await asyncio.wait_for(waiter, remaining)
        except TimeoutError:
            pass
        finally:
            _waiters.discard(waiter)
    first = _presses(after)[0][0]
    await asyncio.sleep(max(0.0, first + SETTLE_SECONDS - time.time()))
    return {"pressed": True, **_summary(after), "cursor": round(time.time(), 3)}


def _momentary_seconds(output: Any) -> float | None:
    if getattr(output, "_adjustable_duration_enabled", False):
        return float(output._adjustable_duration)
    period = getattr(output, "_momentary_turn_on", None)
    return period.as_timedelta.total_seconds() if period is not None else None


def identify_refusal(output: Any, allow_switch: bool) -> str | None:
    """Why this output must not be switched to show it, or None when it may."""
    kind = getattr(output, "output_type", None)
    if getattr(output, "_interlock_groups", None):
        return "it is in an interlock group (a motor or a pair that must never be on together)."
    if kind not in (LIGHT, SWITCH):
        return f"its type is '{kind}': only lights and switches are switched to show them."
    momentary = _momentary_seconds(output)
    if kind == SWITCH and momentary is not None:
        return "it is a switch that turns itself off: a pulse to a gate, a bell or a lock does something."
    if kind == SWITCH and not allow_switch:
        return ("it is a switch, which can drive a contactor, a pump or a heater. Ask the person "
                "whether it may be switched for a moment, then call again with allow_switch.")
    return None


def _output_entry(output: Any) -> dict:
    momentary = _momentary_seconds(output)
    return {
        "id": output.id,
        "name": output.name,
        "type": output.output_type,
        "area": getattr(output, "area", None),
        "state": output.state,
        "remote": getattr(output, "is_remote", False),
        "impulse_relay": momentary is not None and momentary <= IMPULSE_MAX_SECONDS,
        "identify": identify_refusal(output, allow_switch=True) or "allowed",
        "interlock_groups": list(getattr(output, "_interlock_groups", None) or []),
    }


@router.get("/outputs")
async def list_outputs():
    """Every output as it is now: state, area, and whether it may be shown by switching it."""
    install()
    return {"outputs": [_output_entry(o) for o in _manager().outputs.get_all_outputs().values()]}


@router.get("/inputs")
async def list_inputs():
    """Every input that reports presses, with the config section it is set up in."""
    from boneio.components.input.remote.base import RemoteInputBase

    install()
    return {"inputs": [
        {
            "id": i.id, "name": i.name, "pin": i.pin, "boneio_input": i.boneio_input or None,
            "area": getattr(i, "area", None),
            "section": _input_section(i.input_type, isinstance(i, RemoteInputBase)),
            "last_state": i.last_state,
            "last_press_at": round(i.last_press_timestamp, 3) if i.last_press_timestamp else None,
        }
        for i in _manager().inputs.get_inputs_list()
    ], "note": "An input that is not in the event or binary_sensor section does not report presses."}


class Identify(BaseModel):
    seconds: float = Field(3.0, ge=1.0, le=10.0, description="How long the output stays switched.")
    allow_switch: bool = Field(False, description="The person agreed a switch output may be switched.")


async def _turn(output: Any, state: str) -> bool:
    if state == ON:
        return await output.async_turn_on() is not False
    await output.async_turn_off()
    return True


@router.post("/outputs/{output_id}/identify")
async def identify_output(output_id: str, body: Identify | None = None):
    """Switch an output to the other state for a few seconds and back, so a person sees which it is."""
    body = body or Identify()
    install()
    output = _manager().outputs.get_output(output_id)
    if output is None:
        raise HTTPException(status_code=404, detail=f"No output '{output_id}'.")
    refusal = identify_refusal(output, body.allow_switch)
    if refusal:
        raise HTTPException(status_code=409, detail=f"Not switching '{output.name}': {refusal}")
    if _identify_lock.locked():
        raise HTTPException(status_code=409, detail="Another output is being shown; one at a time.")
    async with _identify_lock:
        momentary = _momentary_seconds(output)
        if momentary is not None and momentary <= IMPULSE_MAX_SECONDS:
            # An impulse relay: the lamp flips on each pulse, so pulse, wait, pulse back.
            if not await _turn(output, ON):
                raise HTTPException(status_code=409, detail="The controller refused to switch it on.")
            await asyncio.sleep(max(body.seconds, momentary + 0.5))
            await _turn(output, ON)
            return {"output": output.id, "name": output.name, "shown": "pulsed twice (impulse relay): "
                    "the lamp changed and changed back", "seconds": body.seconds}
        before = output.state
        shown = OFF if before == ON else ON
        if not await _turn(output, shown):
            raise HTTPException(status_code=409, detail="The controller refused to switch it on.")
        await asyncio.sleep(body.seconds)
        if output.state != shown:
            return {"output": output.id, "name": output.name, "restored": False,
                    "detail": f"Something else switched it to {output.state} meanwhile; left as it is."}
        await _turn(output, before)
        return {"output": output.id, "name": output.name, "restored": True,
                "shown": f"{shown} for {body.seconds:g} s, then back to {before}"}
