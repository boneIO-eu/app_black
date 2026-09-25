"""The web API's answer to an alarm code: 403 when wrong, 429 while locked.

Drives the route function with a real alarm panel, so the throttling it
reports is the panel's own (see tests/unit/core/test_alarm_panel.py).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from boneio.components.template.alarm_panel import (
    ARMED_AWAY,
    CODE_MAX_FAILURES,
    DISARMED,
    AlarmPinCode,
    BoneIOAlarmPanel,
)
from boneio.webui.routes.templates import alarm_command

PIN_OK = "1234"
PIN_BAD = "9999"


def make_manager() -> tuple[MagicMock, BoneIOAlarmPanel]:
    panel = BoneIOAlarmPanel(
        id="dom",
        name="Dom",
        message_bus=MagicMock(),
        event_bus=MagicMock(),
        topic_prefix="boneio",
        zones=[],
        outputs=[],
        codes=[AlarmPinCode("Paweł", PIN_OK)],
        allow_frontend_control=True,
        arming_time_s=0,
    )
    manager = MagicMock()
    manager.templates.alarm_manager.get.return_value = panel
    return manager, panel


async def test_right_code_disarms():
    manager, panel = make_manager()
    await alarm_command("dom", {"command": "ARM_AWAY"}, manager)
    result = await alarm_command("dom", {"command": "DISARM", "code": PIN_OK}, manager)
    assert result == {"status": "ok", "state": DISARMED}


async def test_wrong_code_is_403_not_ok():
    manager, panel = make_manager()
    await alarm_command("dom", {"command": "ARM_AWAY"}, manager)
    with pytest.raises(HTTPException) as err:
        await alarm_command("dom", {"command": "DISARM", "code": PIN_BAD}, manager)
    assert err.value.status_code == 403
    assert err.value.detail == {"reason": "invalid_code"}
    assert panel.state == ARMED_AWAY


async def test_missing_code_is_403():
    manager, _ = make_manager()
    await alarm_command("dom", {"command": "ARM_AWAY"}, manager)
    with pytest.raises(HTTPException) as err:
        await alarm_command("dom", {"command": "DISARM"}, manager)
    assert err.value.status_code == 403
    assert err.value.detail == {"reason": "code_required"}


async def test_lockout_is_429_with_retry_after():
    manager, _ = make_manager()
    await alarm_command("dom", {"command": "ARM_AWAY"}, manager)
    for _ in range(CODE_MAX_FAILURES - 1):
        with pytest.raises(HTTPException):
            await alarm_command("dom", {"command": "DISARM", "code": PIN_BAD}, manager)
    with pytest.raises(HTTPException) as err:
        await alarm_command("dom", {"command": "DISARM", "code": PIN_BAD}, manager)
    assert err.value.status_code == 429
    assert err.value.detail["reason"] == "locked"
    assert err.value.detail["retry_after"] == 30
    assert err.value.headers == {"Retry-After": "30"}
