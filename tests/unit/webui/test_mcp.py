"""The MCP endpoint: tools an agent configures the controller with.

Each tool is allowed exactly when the key could call the route it stands for,
nothing reaches the tools without a key, and both eras of the protocol - with
and without the ``initialize`` handshake - get answers they recognise.
"""

from __future__ import annotations

import copy
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from boneio.core.auth.api_keys import ApiKeyStore, KeyScope
from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.webui import security_events
from boneio.webui.middleware.auth import (
    AuthMiddleware,
    issue_token,
    set_allow_anonymous,
    set_auth_config,
    set_jwt_secret,
    set_key_store,
    set_user_store,
)
from boneio.webui.routes import config_backups, config_core
from boneio.webui.routes import mcp as mcp_routes
from boneio.webui.routes import proposals as proposal_routes

SECRET = "test-secret-for-mcp-endpoint-tests-32-bytes"
BONEIO = {"config_version": 7, "name": "test", "version": 1.1, "device_type": "24x16A"}
OUTPUTS = [{"name": "OUT 01", "boneio_output": "OUT_01", "output_type": "switch"}]
MODERN = "2026-07-28"


@pytest.fixture
def device(tmp_path, monkeypatch):
    users = UserStore(tmp_path / USERS_FILENAME)
    users.load()
    users.add_user("pawel", "dobre-haslo", Role.ADMIN)
    keys = ApiKeyStore.beside(users)
    set_jwt_secret(SECRET)
    set_auth_config({})
    set_allow_anonymous(False)
    set_user_store(users)
    set_key_store(keys)

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
    proposal_routes._stores.clear()

    app = FastAPI()
    app.include_router(mcp_routes.router)
    app.add_middleware(AuthMiddleware)
    client = TestClient(app)
    client.keys, client.state, client.config_file = keys, state, config_file
    client.admin = issue_token(users.get_user("pawel"))
    client.events = []
    monkeypatch.setattr(security_events, "emit", lambda kind, **kw: client.events.append((kind, kw)))
    yield client
    config_core._config_cache["data"] = None
    config_core._config_cache["mtime"] = 0
    proposal_routes._stores.clear()
    set_user_store(None)
    set_key_store(None)


def _key(device, scope):
    return device.keys.create(f"agent-{scope}", "pawel", scope, 30)[1]


def _rpc(device, token, method, params=None, *, headers=None, msg_id=1):
    body = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if msg_id is not None:
        body["id"] = msg_id
    return device.post("/api/mcp", json=body,
                       headers={"Authorization": f"Bearer {token}", **(headers or {})})


def _call(device, token, tool, **args):
    reply = _rpc(device, token, "tools/call", {"name": tool, "arguments": args},
                 headers={"MCP-Protocol-Version": "2025-06-18"})
    assert reply.status_code == 200, reply.text
    return reply.json()


def _text(reply):
    return reply["result"]["content"][0]["text"]


# --------------------------------------------------------------- transport


def test_an_older_client_is_answered_in_the_version_it_asked_for(device):
    token = _key(device, KeyScope.READ)
    reply = _rpc(device, token, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
    assert reply.json()["result"]["protocolVersion"] == "2025-06-18"
    assert "mcp-session-id" not in reply.headers
    reply = _rpc(device, token, "initialize", {"protocolVersion": "2024-01-01"})
    assert reply.json()["result"]["protocolVersion"] == mcp_routes.LEGACY_VERSIONS[0]
    assert _rpc(device, token, "notifications/initialized", msg_id=None).status_code == 202


def _modern_headers(method, name=None, version=MODERN):
    headers = {"MCP-Protocol-Version": version, "Mcp-Method": method}
    if name:
        headers["Mcp-Name"] = name
    return headers


def _meta(version=MODERN):
    return {"_meta": {"io.modelcontextprotocol/protocolVersion": version}}


def test_a_modern_client_discovers_and_calls_without_a_handshake(device):
    token = _key(device, KeyScope.READ)
    found = _rpc(device, token, "server/discover", _meta(), headers=_modern_headers("server/discover"))
    assert found.json()["result"]["supportedVersions"] == [MODERN]
    assert found.json()["result"]["cacheScope"] == "public"
    listed = _rpc(device, token, "tools/list", _meta(), headers=_modern_headers("tools/list")).json()["result"]
    # Filtered by scope, so never to be shared between keys.
    assert (listed["cacheScope"], listed["ttlMs"]) == ("private", 300_000)
    called = _rpc(device, token, "tools/call",
                  {**_meta(), "name": "boneio_get_config", "arguments": {"section": "output"}},
                  headers=_modern_headers("tools/call", "=?base64?Ym9uZWlvX2dldF9jb25maWc=?="))
    assert called.json()["result"]["resultType"] == "complete"
    assert _text(called.json()) == "[]"


@pytest.mark.parametrize(
    ("headers", "params", "status", "code"),
    [
        (_modern_headers("tools/list", version="2025-06-18"), _meta(), 400, -32020),
        ({"MCP-Protocol-Version": MODERN}, _meta(), 400, -32020),
        (_modern_headers("tools/list", version="2099-01-01"), _meta("2099-01-01"), 400, -32022),
        (_modern_headers("tools/list"), {}, 400, -32020),
    ],
    ids=["version-mismatch", "no-method-header", "unknown-version", "header-without-meta"],
)
def test_a_modern_request_that_does_not_add_up_is_refused(device, headers, params, status, code):
    reply = _rpc(device, _key(device, KeyScope.READ), "tools/list", params, headers=headers)
    assert (reply.status_code, reply.json()["error"]["code"]) == (status, code)


def test_unknown_methods_batches_and_streams(device):
    token = _key(device, KeyScope.READ)
    modern = _rpc(device, token, "prompts/list", _meta(), headers=_modern_headers("prompts/list"))
    assert (modern.status_code, modern.json()["error"]["code"]) == (404, -32601)
    assert _rpc(device, token, "prompts/list").json()["error"]["code"] == -32601
    batch = device.post("/api/mcp", json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}],
                        headers={"Authorization": f"Bearer {token}"})
    assert batch.status_code == 400
    assert device.get("/api/mcp", headers={"Authorization": f"Bearer {token}"}).status_code == 405


# ------------------------------------------------------------------ access


def test_nothing_reaches_the_tools_without_a_key(device):
    assert _rpc(device, device.admin, "tools/list").status_code == 403
    set_allow_anonymous(True)
    try:
        anonymous = device.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert anonymous.status_code in (401, 403)
    finally:
        set_allow_anonymous(False)


@pytest.mark.parametrize(
    ("scope", "tools"),
    [
        (KeyScope.READ, {"boneio_list_sections", "boneio_get_config", "boneio_describe_schema",
                         "boneio_discover_devices"}),
        (KeyScope.PROPOSE, {"boneio_list_sections", "boneio_get_config", "boneio_describe_schema",
                            "boneio_discover_devices", "boneio_validate", "boneio_propose",
                            "boneio_proposal_status", "boneio_add_discovered_device",
                            "boneio_usage_summary"}),
        (KeyScope.WRITE, {t.name for t in mcp_routes.TOOLS}),
    ],
)
def test_a_key_is_offered_the_tools_of_its_scope(device, scope, tools):
    listed = _rpc(device, _key(device, scope), "tools/list").json()["result"]["tools"]
    assert {t["name"] for t in listed} == tools


def test_a_tool_outside_the_scope_is_unknown(device):
    assert _call(device, _key(device, KeyScope.READ), "boneio_validate",
                 section="output", data=OUTPUTS)["error"]["code"] == -32602
    assert _call(device, _key(device, KeyScope.PROPOSE), "boneio_save",
                 section="output", data=OUTPUTS)["error"]["code"] == -32602


@pytest.mark.parametrize("section", ["mqtt", "modbus", "remote_devices"])
def test_a_write_key_cannot_save_a_section_a_person_changes(device, section):
    reply = _call(device, _key(device, KeyScope.WRITE), "boneio_save", section=section, data={})
    assert reply["result"]["isError"] is True
    assert "OUT" not in device.config_file.read_text(encoding="utf-8")


# ------------------------------------------------------------------- tools


def test_validate_reports_errors_without_writing(device):
    reply = _call(device, _key(device, KeyScope.PROPOSE), "boneio_validate",
                  section="output", data=[{**OUTPUTS[0], "output_type": "banana"}])
    assert '"valid":false' in _text(reply) and "output_type" in _text(reply)
    assert device.config_file.read_text(encoding="utf-8") == "output: []\n"


def test_a_proposal_waits_and_only_its_key_sees_how_it_stands(device):
    token = _key(device, KeyScope.PROPOSE)
    filed = _call(device, token, "boneio_propose", section="output", data=OUTPUTS, rationale="add OUT 01")
    assert filed["result"]["isError"] is False
    (pending,) = proposal_routes._store().list()
    assert [kind for kind, _ in device.events] == ["proposal_filed"]
    assert device.config_file.read_text(encoding="utf-8") == "output: []\n"
    assert '"status":"pending"' in _text(_call(device, token, "boneio_proposal_status", proposal_id=pending.id))
    other = _key(device, KeyScope.PROPOSE)
    assert '"not pending"' in _text(_call(device, other, "boneio_proposal_status", proposal_id=pending.id))


def test_an_invalid_proposal_comes_back_as_an_error_the_model_can_read(device):
    reply = _call(device, _key(device, KeyScope.PROPOSE), "boneio_propose",
                  section="output", data=[{**OUTPUTS[0], "output_type": "banana"}], rationale="x")
    assert reply["result"]["isError"] is True and "output[0].output_type" in _text(reply)


def test_a_write_key_saves_and_the_section_is_reloaded(device):
    reply = _call(device, _key(device, KeyScope.WRITE), "boneio_save", section="output", data=OUTPUTS)
    assert reply["result"]["isError"] is False
    assert "OUT 01" in device.config_file.read_text(encoding="utf-8")
    device.state.manager.reload_config.assert_awaited_once_with(reload_sections=["output"])
    # Saved without asking anyone: the owner hears of it in Home Assistant.
    ((kind, event),) = device.events
    assert kind == "config_saved_by_key" and event["username"] == "pawel" and "'output'" in event["where"]


def test_a_schema_is_served_without_titles_and_a_wrong_section_is_explained(device):
    token = _key(device, KeyScope.READ)
    schema = _text(_call(device, token, "boneio_describe_schema", section="output"))
    assert '"boneio_output"' in schema and '"title"' not in schema
    wrong = _call(device, token, "boneio_get_config", section="outputz")
    assert wrong["result"]["isError"] is True and "boneio_list_sections" in _text(wrong)


def test_sections_are_listed_with_what_a_key_may_do_with_them(device):
    listed = _text(_call(device, _key(device, KeyScope.READ), "boneio_list_sections"))
    assert '{"section":"mqtt","configured":false,"panel_only":true,"restart_required":true}' in listed
    assert '{"section":"output","configured":true,"entries":0}' in listed


def _backups(device):
    return sorted((device.config_file.parent / "backups").glob("config_backup_*.tar.gz"))


def test_a_save_by_key_leaves_one_restore_point_per_session(device):
    token = _key(device, KeyScope.WRITE)
    _call(device, token, "boneio_save", section="output", data=OUTPUTS)
    _call(device, token, "boneio_save", section="output", data=[{**OUTPUTS[0], "name": "Lamp"}])
    assert len(_backups(device)) == 1


def test_without_a_restore_point_a_key_saves_nothing(device, monkeypatch):
    monkeypatch.setattr(config_backups, "_create_backup", lambda: {"status": "error", "message": "disk full"})
    reply = _call(device, _key(device, KeyScope.WRITE), "boneio_save", section="output", data=OUTPUTS)
    assert reply["result"]["isError"] is True and "back up" in _text(reply)
    assert device.config_file.read_text(encoding="utf-8") == "output: []\n"


def test_a_read_key_sees_the_devices_around_the_controller(device, monkeypatch):
    from boneio.webui.routes import remote_devices

    remote = device.state.manager.remote_devices
    remote.autodiscovered_to_dict.return_value = {
        "blk_abc123": {"id": "blk_abc123", "name": "Garaż", "protocol": "mqtt", "device_type": "boneio_black",
                       "outputs": [{"id": "OUT_01", "name": "Brama"}], "covers": []},
    }
    remote.get_managed_by_devices.return_value = {}

    async def esphome(timeout):
        return {"devices": [{"name": "kuchnia", "host": "kuchnia.local", "ip": "192.168.1.30", "port": 6053}]}

    async def wled(timeout):
        raise HTTPException(status_code=400, detail="zeroconf not installed - mDNS discovery disabled")

    monkeypatch.setattr(remote_devices, "scan_esphome_network", esphome)
    monkeypatch.setattr(remote_devices, "scan_wled_network", wled)
    token = _key(device, KeyScope.READ)
    quiet = json.loads(_text(_call(device, token, "boneio_discover_devices")))
    assert quiet["boneio_over_mqtt"][0]["name"] == "Garaż" and quiet["boneio_over_mqtt"][0]["configured"] is False
    assert "esphome_on_network" not in quiet  # the network is scanned only when asked
    scanned = json.loads(_text(_call(device, token, "boneio_discover_devices", scan_network=True)))
    assert scanned["esphome_on_network"][0]["ip"] == "192.168.1.30"
    assert "zeroconf" in scanned["wled_on_network"]["error"]


# ------------------------------------------------- adding a discovered device

AGENT_REQUEST = type("Req", (), {"state": type("S", (), {"user": "pawel"})()})()

EXISTING = {"id": "garage", "name": "Garage", "protocol": "esphome_api", "device_type": "esphome",
            "esphome_api": {"host": "192.168.1.40", "port": 6053, "password": "s3cret"}}


@pytest.fixture
def neighbours(device, monkeypatch):
    """A device already configured with a password, and discovery that finds more."""
    from boneio.webui.routes import remote_devices

    config_core._config_cache["data"]["remote_devices"] = [copy.deepcopy(EXISTING)]
    device.config_file.write_text(
        "output: []\nremote_devices:\n  - id: garage\n    name: Garage\n    protocol: esphome_api\n"
        "    device_type: esphome\n    esphome_api:\n      host: 192.168.1.40\n      port: 6053\n"
        "      password: s3cret\n", encoding="utf-8")
    # As the running app holds it: what the last save wrote.
    device.state.manager.config_helper.get_config.side_effect = (
        lambda *a, **k: {"boneio": BONEIO, **yaml.safe_load(device.config_file.read_text(encoding="utf-8"))})
    boneio = MagicMock()
    boneio.to_dict.return_value = {"id": "blk_abc123", "name": "Shed", "protocol": "mqtt",
                                   "device_type": "boneio_black", "outputs": [{"id": "OUT_01", "name": "Lamp"}],
                                   "covers": []}
    device.state.manager.remote_devices.get_autodiscovered_device.side_effect = (
        lambda i: boneio if i == "blk_abc123" else None)

    async def wled(request):
        return {"name": "Shelf LEDs", "segments": [{"id": 0}]}

    async def esphome(request):
        raise HTTPException(status_code=502, detail="No ESPHome device answered at that address.")

    monkeypatch.setattr(remote_devices, "discover_wled", wled)
    monkeypatch.setattr(remote_devices, "discover_esphome", esphome)
    return device


def test_a_propose_key_files_a_discovered_controller_for_approval(neighbours):
    reply = _call(neighbours, _key(neighbours, KeyScope.PROPOSE), "boneio_add_discovered_device",
                  kind="boneio", device_id="blk_abc123")
    assert reply["result"]["isError"] is False, _text(reply)
    (pending,) = proposal_routes._store().list()
    added = pending.data[-1]
    assert added["id"] == "blk_abc123" and added["mqtt"]["outputs"] == [{"id": "OUT_01", "name": "Lamp"}]
    assert "blk_abc123" not in neighbours.config_file.read_text(encoding="utf-8")


def test_a_write_key_saves_a_wled_device_and_the_neighbours_password_survives(neighbours):
    reply = _call(neighbours, _key(neighbours, KeyScope.WRITE), "boneio_add_discovered_device",
                  kind="wled", host="192.168.1.50")
    assert reply["result"]["isError"] is False, _text(reply)
    stored = neighbours.config_file.read_text(encoding="utf-8")
    assert "shelf_leds" in stored and "192.168.1.50" in stored
    assert "s3cret" in stored and "***" not in stored


async def test_approving_a_proposed_device_puts_the_masked_password_back(neighbours):
    _call(neighbours, _key(neighbours, KeyScope.PROPOSE), "boneio_add_discovered_device",
          kind="wled", host="192.168.1.50")
    (pending,) = proposal_routes._store().list()
    assert pending.data[0]["esphome_api"]["password"] != "s3cret"  # what was filed is masked
    await proposal_routes.approve_proposal(pending.id, AGENT_REQUEST, None)
    stored = neighbours.config_file.read_text(encoding="utf-8")
    assert "s3cret" in stored and "192.168.1.50" in stored


@pytest.mark.parametrize(
    ("args", "says"),
    [
        ({"kind": "esphome", "host": "192.168.1.60"}, "encryption key"),
        ({"kind": "wled", "host": "192.168.1.40"}, "already configured"),
        ({"kind": "boneio", "device_id": "blk_nope"}, "No boneIO controller"),
    ],
)
def test_what_cannot_be_added_says_why(neighbours, args, says):
    reply = _call(neighbours, _key(neighbours, KeyScope.WRITE), "boneio_add_discovered_device", **args)
    assert reply["result"]["isError"] is True and says in _text(reply)


def test_a_read_key_cannot_add_a_device(neighbours):
    reply = _call(neighbours, _key(neighbours, KeyScope.READ), "boneio_add_discovered_device",
                  kind="wled", host="192.168.1.50")
    assert reply["error"]["code"] == -32602


def test_an_esphome_device_given_by_address_is_named_as_it_names_itself(neighbours, monkeypatch):
    from boneio.webui.routes import remote_devices

    async def esphome(request):
        return {"switches": [{"id": "relay_1", "name": "Relay 1", "key": 7, "icon": "mdi:x"}], "lights": [], "covers": []}

    async def scan(timeout):
        return {"devices": [{"name": "kitchen-relays", "host": "kitchen-relays.local", "ip": "192.168.1.70"}]}

    monkeypatch.setattr(remote_devices, "discover_esphome", esphome)
    monkeypatch.setattr(remote_devices, "scan_esphome_network", scan)
    token = _key(neighbours, KeyScope.WRITE)
    _call(neighbours, token, "boneio_add_discovered_device", kind="esphome", host="192.168.1.70")
    _call(neighbours, token, "boneio_add_discovered_device", kind="esphome", host="192.168.1.71")
    stored = neighbours.config_file.read_text(encoding="utf-8")
    assert "id: kitchen_relays" in stored and "id: esphome_192_168_1_71" in stored
    assert "icon" not in stored  # only what the schema holds is written
    assert "id: garage" in stored and "s3cret" in stored  # the neighbour already there stays
