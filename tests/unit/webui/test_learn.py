"""Learning mode: waiting for a press, and showing an output by switching it.

The press wait is how an agent learns which button is which and checks a saved
change; showing an output switches real relays, so what it refuses matters as
much as what it does.
"""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from boneio.core.auth.api_keys import KeyScope
from boneio.models import InputState, OutputState
from boneio.models.events import InputEvent, OutputEvent
from boneio.webui.middleware import policy
from boneio.webui.routes import config_core, learn


class FakeOutput:
    def __init__(self, id, output_type="light", state="OFF", interlock=None, momentary=None):
        self.id = self.name = id
        self.output_type, self.state, self.area = output_type, state, "Łazienka"
        self._interlock_groups = interlock or []
        self._momentary_turn_on = SimpleNamespace(as_timedelta=timedelta(seconds=momentary)) if momentary else None
        self.calls = []

    async def async_turn_on(self):
        self.calls.append("on")
        self.state = "ON"
        return True

    async def async_turn_off(self):
        self.calls.append("off")
        self.state = "OFF"


@pytest.fixture
def outputs(monkeypatch):
    found: dict[str, FakeOutput] = {}
    state = MagicMock()
    state.manager.outputs.get_output = found.get
    state.manager.outputs.get_all_outputs = lambda: found
    config_core.set_app_state(state)
    learn._recent.clear()
    monkeypatch.setattr(learn, "SETTLE_SECONDS", 0.2)
    yield found
    learn._recent.clear()
    config_core.set_app_state(None)


def _press(input_id="in_01", click="single", publish_only=False):
    state = InputState(name=input_id, state=click or "", type="input", pin="P8_7",
                       timestamp=time.time(), boneio_input="IN_01")
    return InputEvent(entity_id=input_id, click_type=click, state=state, publish_only=publish_only)


def _switched(output_id, state="ON"):
    return OutputEvent(entity_id=output_id, state=OutputState(id=output_id, name=output_id, state=state,
                                                              type="light", expander_id=None, pin=None))


# --------------------------------------------------------------- the wait


async def test_a_press_answers_with_the_input_and_what_it_switched(outputs):
    async def press_later():
        await asyncio.sleep(0.05)
        learn._record(_press(click=None))  # a resend after reload: nobody pressed
        learn._record(_press("bs_01", "pressed", publish_only=True))  # re-announced to HA
        learn._record(_press())
        learn._record(_switched("out_05"))

    asyncio.get_running_loop().create_task(press_later())
    reply = await learn.wait_for_press(since=None, timeout=2)
    assert reply["pressed"] is True
    assert [(i["id"], i["clicks"], i["section"]) for i in reply["inputs"]] == [("in_01", ["single"], "event")]
    assert [o["id"] for o in reply["outputs_switched"]] == ["out_05"]


async def test_no_press_ends_with_a_cursor_to_continue_from(outputs):
    learn._record(_press())  # pressed before the cursor: already answered
    since = time.time()
    reply = await learn.wait_for_press(since=since, timeout=1)
    assert reply["pressed"] is False and reply["cursor"] >= since


# ------------------------------------------------------- showing an output


@pytest.mark.parametrize("output, allow_switch, refused", [
    (FakeOutput("l"), False, False),
    (FakeOutput("s", "switch"), False, True),  # could be a pump: ask first
    (FakeOutput("s", "switch"), True, False),
    (FakeOutput("g", "switch", momentary=0.5), True, True),  # a gate pulse does something
    (FakeOutput("c", "cover"), True, True),
    (FakeOutput("v", "valve"), True, True),
    (FakeOutput("n", "none"), True, True),
    (FakeOutput("i", interlock=["blind"]), True, True),
])
def test_only_harmless_outputs_are_switched(output, allow_switch, refused):
    assert (learn.identify_refusal(output, allow_switch) is not None) is refused


async def test_a_lamp_is_switched_and_put_back(outputs):
    outputs["on"] = lamp = FakeOutput("on", state="ON")
    reply = await learn.identify_output("on", learn.Identify(seconds=1))
    assert lamp.calls == ["off", "on"] and reply["restored"] is True


async def test_an_impulse_relay_gets_two_pulses(outputs):
    outputs["imp"] = lamp = FakeOutput("imp", momentary=0.2)
    await learn.identify_output("imp", learn.Identify(seconds=1))
    assert lamp.calls == ["on", "on"]


async def test_a_lamp_switched_by_someone_else_meanwhile_is_left_alone(outputs):
    outputs["l"] = lamp = FakeOutput("l")

    async def person():
        await asyncio.sleep(0.3)
        lamp.state = "OFF"

    asyncio.get_running_loop().create_task(person())
    reply = await learn.identify_output("l", learn.Identify(seconds=1))
    assert lamp.calls == ["on"] and reply["restored"] is False


async def test_a_refused_output_is_not_touched(outputs):
    outputs["c"] = cover = FakeOutput("c", "cover")
    with pytest.raises(HTTPException) as err:
        await learn.identify_output("c", learn.Identify())
    assert err.value.status_code == 409 and cover.calls == []


# ------------------------------------------------------------------ scopes


@pytest.mark.parametrize("scope, method, path, allowed", [
    (KeyScope.READ, "GET", "/api/learn/outputs", True),
    (KeyScope.READ, "GET", "/api/learn/press", False),  # live presses say who is home
    (KeyScope.PROPOSE, "GET", "/api/learn/press", True),
    (KeyScope.PROPOSE, "POST", "/api/learn/outputs/x/identify", False),
    (KeyScope.WRITE, "POST", "/api/learn/outputs/x/identify", True),
    (KeyScope.WRITE, "POST", "/api/outputs/x/turn_on", False),  # still no general switching
])
def test_keys_reach_learning_by_scope(scope, method, path, allowed):
    assert policy.key_allows(scope, method, path) is allowed
