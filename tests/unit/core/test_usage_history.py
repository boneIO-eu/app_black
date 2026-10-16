"""Usage history: off by default, counts only changes, forgets when turned off.

It records when somebody is at home, so what matters most is what it does
not do: nothing while off, nothing finer than an hour, nothing kept after
it is switched off - and a summary a model can read in a few hundred tokens.
"""

from __future__ import annotations

import json
import os
import stat
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from boneio.core.auth.api_keys import KeyScope
from boneio.core.manager import usage_history as module
from boneio.core.manager.usage_history import UsageHistory
from boneio.webui.middleware import policy


def output(entity, state, kind="light"):
    return SimpleNamespace(event_type="output", entity_id=entity,
                           state=SimpleNamespace(name=entity.title(), state=state, type=kind))


def cover(entity, operation):
    return SimpleNamespace(event_type="cover", entity_id=entity,
                           state=SimpleNamespace(name=entity.title(), current_operation=operation))


def click(entity, click_type):
    return SimpleNamespace(event_type="input", entity_id=entity, click_type=click_type,
                           state=SimpleNamespace(name=entity.title()))


@pytest.fixture
def history(tmp_path):
    return UsageHistory(MagicMock(), tmp_path / module.FILENAME)


def test_off_by_default_records_nothing(history):
    history.configure(None)
    history._on_event(output("out_01", "ON"))
    history.persist()
    assert history.summary() == {"enabled": False}
    assert not history._path.exists()


def test_it_counts_changes_by_hour_and_the_time_spent_on(history, monkeypatch):
    history.configure({"enabled": True, "days": 30})
    clock = [1000.0, 1600.0]  # on, then off ten minutes later
    monkeypatch.setattr(history, "_now_s", lambda: clock.pop(0) if len(clock) > 1 else clock[0])
    for event in (output("out_01", "ON"), output("out_01", "ON"),  # the second is a republish
                  output("out_01", "OFF"), output("relay", "ON", kind="cover"),
                  cover("salon", "opening"), cover("salon", "opening"), cover("salon", "idle"),
                  click("in_03", "single"), click("in_03", "pressed")):
        history._on_event(event)
    summary = history.summary(days=1)
    entities = {e["id"]: e for e in summary["entities"]}
    assert set(entities) == {"out_01", "salon", "in_03"}  # a cover's relay is the cover's
    part = "weekend" if date.today().weekday() >= 5 else "weekday"
    assert entities["out_01"]["on"][part]["count"] == 1
    assert entities["out_01"]["average_on_minutes"] == 10.0
    assert entities["salon"]["open"][part]["count"] == 1
    assert entities["in_03"]["single"][part]["busiest_hours"] == [datetime.now().hour]
    assert "pressed" not in entities["in_03"]


def test_it_keeps_its_days_in_a_private_file_and_drops_old_ones(history):
    history.configure({"enabled": True, "days": 7})
    old = (date.today() - timedelta(days=10)).isoformat()
    history._data[old] = {"output:x": {"on": {"8": 1}}}
    history._on_event(output("out_01", "ON"))
    history.persist()
    saved = json.loads(history._path.read_text())
    assert old not in saved["days"] and date.today().isoformat() in saved["days"]
    assert stat.S_IMODE(os.stat(history._path).st_mode) == 0o600


def test_turning_it_off_forgets_everything(history):
    history.configure({"enabled": True})
    history._on_event(output("out_01", "ON"))
    history.persist()
    assert history._path.exists()
    history.configure({"enabled": False})
    assert not history._path.exists()
    history._on_event(output("out_01", "OFF"))
    assert history.summary() == {"enabled": False}


@pytest.mark.parametrize(
    ("scope", "method", "path", "allowed"),
    [
        (KeyScope.READ, "GET", "/api/usage-summary", False),
        (KeyScope.PROPOSE, "GET", "/api/usage-summary", True),
        (KeyScope.WRITE, "GET", "/api/usage-summary", True),
        # Switching the collection on is a person's decision.
        (KeyScope.WRITE, "PUT", "/api/config/usage_history", False),
        (KeyScope.PROPOSE, "POST", "/api/config/usage_history/proposals", True),
    ],
)
def test_who_reads_the_summary_and_who_switches_it_on(scope, method, path, allowed):
    assert policy.key_allows(scope, method, path) is allowed


def test_a_read_only_account_does_not_see_it():
    assert policy.required_role("GET", "/api/usage-summary").value == "admin"
