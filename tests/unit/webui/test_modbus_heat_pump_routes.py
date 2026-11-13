"""The panel's heat pump routes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from boneio.core.auth.models import Role  # noqa: E402
from boneio.modbus.coordinator import ModbusWriteFailed, ModbusWriteRejected  # noqa: E402
from boneio.webui.middleware import policy  # noqa: E402
from boneio.webui.routes import modbus as route  # noqa: E402


def _coordinator(heat_pump):
    entities = {"t_flow": SimpleNamespace(id="hp_tflow"), "heater": SimpleNamespace(id="hp_heater")}
    return SimpleNamespace(
        definition=SimpleNamespace(heat_pump=heat_pump),
        heat_pump_state=lambda: {"mode": "heat"},
        set_heat_pump=AsyncMock(),
        _role_entity=lambda role, ref: entities.get(ref),
    )


@pytest.fixture
def pump():
    spec = SimpleNamespace(scheme="lg_therma", roles={"flow": "t_flow", "backup_heater": ["heater", "gone"]})
    return _coordinator(spec)


@pytest.fixture
def client(pump):
    manager = SimpleNamespace(
        modbus=SimpleNamespace(get_all_coordinators=lambda: {"hp": pump, "meter": _coordinator(None)})
    )
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_manager] = lambda: manager
    return TestClient(app)


def test_heat_pump_endpoint_404_without_section(client):
    assert client.get("/api/modbus/meter/heat_pump").status_code == 404
    assert client.get("/api/modbus/nope/heat_pump").status_code == 404
    assert client.post("/api/modbus/meter/heat_pump/mode", json={"value": "off"}).status_code == 404


def test_heat_pump_endpoint_lists_roles_as_entity_ids(client):
    body = client.get("/api/modbus/HP/heat_pump").json()
    assert body["scheme"] == "lg_therma"
    assert body["modes"] == ["off", "heat", "cool", "auto"]
    assert body["roles"] == {"flow": "hp_tflow", "backup_heater": ["hp_heater", None]}
    assert body["state"] == {"mode": "heat"}


def test_mode_post_goes_to_the_coordinator(client, pump):
    assert client.post("/api/modbus/hp/heat_pump/mode", json={"value": "cool"}).status_code == 200
    pump.set_heat_pump.assert_awaited_once_with("mode", "cool")


def test_mode_post_rejected_on_read_only_returns_400(client, pump):
    pump.set_heat_pump.side_effect = ModbusWriteRejected("read only")
    assert client.post("/api/modbus/hp/heat_pump/mode", json={"value": "cool"}).status_code == 400


def test_failed_bus_write_returns_502(client, pump):
    pump.set_heat_pump.side_effect = ModbusWriteFailed("bus")
    assert client.post("/api/modbus/hp/heat_pump/mode", json={"value": "cool"}).status_code == 502


def test_unknown_field_and_missing_value_return_400(client, pump):
    assert client.post("/api/modbus/hp/heat_pump/power", json={"value": 1}).status_code == 400
    assert client.post("/api/modbus/hp/heat_pump/mode", json={}).status_code == 400
    pump.set_heat_pump.assert_not_awaited()


def test_viewer_cannot_post_mode():
    path = "/api/modbus/hp/heat_pump/mode"
    assert not policy.role_allows(Role.VIEWER, "POST", path)
    assert policy.role_allows(Role.ADMIN, "POST", path)
    assert policy.role_allows(Role.VIEWER, "GET", "/api/modbus/hp/heat_pump")


async def test_a_derived_entity_names_the_register_whose_visibility_it_inherits():
    entities = {e["decoded_name"]: e for e in (await route.get_model_entities("lg-therma-v-r290"))["entities"]}

    assert entities["emergencystop"]["source"] == "emergencystopstate"
    assert entities["emergencystop"]["hidden"]
    assert entities["heatingcooling"]["source"] == "heatingcoolingstate"
    assert "source" not in entities["heatingsetpoint"]
