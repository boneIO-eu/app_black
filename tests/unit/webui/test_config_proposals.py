"""Proposals: a change an agent may not save waits for an administrator.

What waits must be savable, approving it must not quietly undo what changed
since it was made, and a key must never reach the approval itself.
"""

from __future__ import annotations

import os
import stat
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from boneio.core.auth.api_keys import KeyScope
from boneio.core.config import proposals as proposals_module
from boneio.core.config.proposals import MAX_PENDING, ProposalError, ProposalStore
from boneio.webui.middleware import policy
from boneio.webui.routes import config_backups, config_core
from boneio.webui.routes import proposals as routes

BONEIO = {"config_version": 7, "name": "test", "version": 1.1, "device_type": "24x16A"}
OUTPUTS = [{"name": "OUT 01", "boneio_output": "OUT_01", "output_type": "switch"}]
AGENT = SimpleNamespace(state=SimpleNamespace(user="key:Claude (pawel)"))


class TestStore:
    def test_a_proposal_survives_a_restart_in_a_private_file(self, tmp_path):
        store = ProposalStore(tmp_path / "proposals.json")
        made = store.add("output", OUTPUTS, "  rename  ", "key:Claude (pawel)", "abc")
        assert stat.S_IMODE(os.stat(store.path).st_mode) == 0o600
        again = ProposalStore(store.path).get(made.id)
        assert again.data == OUTPUTS and again.rationale == "rename"

    def test_a_full_queue_refuses_more(self, tmp_path):
        store = ProposalStore(tmp_path / "proposals.json")
        for _ in range(MAX_PENDING):
            store.add("output", [], "", "a", "b")
        with pytest.raises(ProposalError):
            store.add("output", [], "", "a", "b")

    def test_an_old_proposal_expires(self, tmp_path, monkeypatch):
        store = ProposalStore(tmp_path / "proposals.json")
        store.add("output", [], "", "a", "b")
        later = proposals_module._now() + proposals_module.LIFETIME + timedelta(minutes=1)
        monkeypatch.setattr(proposals_module, "_now", lambda: later)
        assert store.list() == []
        assert ProposalStore(store.path).list() == []


@pytest.mark.parametrize(
    ("scope", "method", "path", "allowed"),
    [
        (KeyScope.READ, "POST", "/api/config/output/proposals", False),
        (KeyScope.PROPOSE, "POST", "/api/config/output/proposals", True),
        (KeyScope.WRITE, "POST", "/api/config/output/proposals", True),
        # Approving is a person's job, whatever the key.
        *[
            (scope, method, path, False)
            for scope in KeyScope
            for method, path in (
                ("GET", "/api/proposals"),
                ("POST", "/api/proposals/abcd1234/approve"),
                ("DELETE", "/api/proposals/abcd1234"),
                ("PUT", "/api/config/output/proposals"),
            )
        ],
    ],
)
def test_a_key_files_proposals_but_never_approves_them(scope, method, path, allowed):
    assert policy.key_allows(scope, method, path) is allowed


def test_only_an_admin_sees_the_queue():
    assert policy.required_role("GET", "/api/proposals").value == "admin"


@pytest.fixture
def device(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("output: []\n", encoding="utf-8")
    state = MagicMock()
    state.yaml_config_file = str(config_file)
    state.manager.reload_config = AsyncMock(return_value={"status": "success"})
    state.manager.config_helper.get_section.return_value = []
    state.manager.config_helper.serial_number = state.manager.config_helper.real_serial = "blk000001"
    monkeypatch.setattr(config_backups, "_last_restore_point", float("-inf"))
    config_core.set_app_state(state)
    config_core._config_cache["data"] = {"boneio": BONEIO, "output": []}
    config_core._config_cache["mtime"] = float("inf")
    routes._stores.clear()
    yield state
    config_core._config_cache["data"] = None
    config_core._config_cache["mtime"] = 0
    routes._stores.clear()


def _stored(device):
    with open(device.yaml_config_file, encoding="utf-8") as f:
        return f.read()


async def _propose(section="output", data=OUTPUTS, rationale="add OUT 01"):
    body = routes.NewProposal(data=data, rationale=rationale)
    return (await routes.propose_section(section, body, AGENT))["proposal"]


@pytest.mark.asyncio
async def test_a_valid_change_waits_with_its_diff_and_nothing_is_written(device):
    before = _stored(device)
    made = await _propose()
    assert _stored(device) == before
    assert (await routes.count_proposals()) == {"pending": 1}
    (entry,) = (await routes.list_proposals())["proposals"]
    assert entry["id"] == made["id"] and entry["author"] == "key:Claude (pawel)"
    assert "+- name: OUT 01" in entry["diff"] and entry["stale"] is False
    assert "data" not in entry and "base" not in entry


@pytest.mark.asyncio
async def test_an_invalid_change_is_refused_with_its_reasons(device):
    with pytest.raises(HTTPException) as err:
        await _propose(data=[{**OUTPUTS[0], "output_type": "banana"}])
    assert err.value.status_code == 422
    assert err.value.detail["errors"][0].startswith("output[0].output_type")
    assert (await routes.list_proposals())["proposals"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["mqtt", "remote_devices", "template", "web"])
async def test_a_section_holding_a_secret_cannot_be_proposed(device, section):
    with pytest.raises(HTTPException) as err:
        await _propose(section=section, data={})
    assert err.value.status_code == 403


@pytest.mark.asyncio
async def test_approving_saves_through_the_save_route_and_reloads(device):
    made = await _propose()
    await routes.approve_proposal(made["id"], AGENT, None)
    assert "OUT 01" in _stored(device)
    device.manager.reload_config.assert_awaited_once_with(reload_sections=["output"])
    # A way back to before the change.
    assert len(list((Path(device.yaml_config_file).parent / "backups").glob("config_backup_*"))) == 1
    assert (await routes.list_proposals())["proposals"] == []


@pytest.mark.asyncio
async def test_approving_a_stale_proposal_wants_it_said_twice(device):
    made = await _propose()
    config_core._config_cache["data"]["output"] = [{**OUTPUTS[0], "name": "Lamp"}]
    assert (await routes.list_proposals())["proposals"][0]["stale"] is True
    with pytest.raises(HTTPException) as err:
        await routes.approve_proposal(made["id"], AGENT, None)
    assert err.value.status_code == 409
    assert "OUT 01" not in _stored(device)
    await routes.approve_proposal(made["id"], AGENT, routes.Approval(force=True))
    assert "OUT 01" in _stored(device)


@pytest.mark.asyncio
async def test_rejecting_drops_it_unsaved(device):
    made = await _propose()
    await routes.reject_proposal(made["id"])
    assert (await routes.list_proposals())["proposals"] == []
    with pytest.raises(HTTPException) as err:
        await routes.approve_proposal(made["id"], AGENT, None)
    assert err.value.status_code == 404
    assert "OUT 01" not in _stored(device)


@pytest.mark.asyncio
async def test_a_reload_that_fails_leaves_it_saved_and_out_of_the_queue(device):
    made = await _propose()
    device.manager.reload_config.side_effect = RuntimeError("bus gone")
    with pytest.raises(HTTPException):
        await routes.approve_proposal(made["id"], AGENT, None)
    assert "OUT 01" in _stored(device)
    assert (await routes.list_proposals())["proposals"] == []


@pytest.mark.asyncio
async def test_a_section_applied_at_restart_is_not_reloaded(device):
    made = await _propose(section="modbus", data={"uart": "uart1"})
    result = await routes.approve_proposal(made["id"], AGENT, None)
    assert result["restart_required"] is True
    device.manager.reload_config.assert_not_awaited()
