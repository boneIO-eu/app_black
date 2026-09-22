"""Tests for the one endpoint the panel uses to flip a flag.

`POST /api/virtual_switch/{id}/toggle` is how the Outputs view and the
Virtual switches page change a mode. It had no tests: a rename of the manager
attribute or a change to the response shape would have shipped silently.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.webui.routes import outputs as outputs_routes


class FakeSwitch:
    def __init__(self, switch_id: str, state: str = "OFF") -> None:
        self.id = switch_id
        self.state = state
        self.toggles = 0

    @property
    def is_active(self) -> bool:
        return self.state == "ON"

    async def async_toggle(self, timestamp=None) -> None:
        self.toggles += 1
        self.state = "OFF" if self.state == "ON" else "ON"


class FakeSwitches:
    def __init__(self, switches: dict[str, FakeSwitch]) -> None:
        self._switches = switches

    def get(self, switch_id):
        return self._switches.get(switch_id)


@pytest.fixture
def switch() -> FakeSwitch:
    return FakeSwitch("presence_away")


@pytest.fixture
def client(switch) -> TestClient:
    class FakeManager:
        virtual_switches = FakeSwitches({switch.id: switch})

    app = FastAPI()
    app.include_router(outputs_routes.router)
    app.dependency_overrides[outputs_routes.get_manager] = lambda: FakeManager()
    return TestClient(app, raise_server_exceptions=False)


def test_toggling_flips_it_and_reports_the_new_state(client, switch):
    response = client.post("/api/virtual_switch/presence_away/toggle")
    assert response.status_code == 200
    assert response.json() == {"status": "ON"}
    assert switch.toggles == 1


def test_toggling_twice_comes_back(client, switch):
    client.post("/api/virtual_switch/presence_away/toggle")
    response = client.post("/api/virtual_switch/presence_away/toggle")
    assert response.json() == {"status": "OFF"}
    assert switch.toggles == 2


def test_an_unknown_switch_is_a_404_not_a_500(client):
    """The panel shows the detail, so it has to be a sentence, not a traceback."""
    response = client.post("/api/virtual_switch/nope/toggle")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_an_id_with_a_slash_in_it_does_not_reach_another_route(client):
    """Ids come from names now, and slugifying strips slashes — but the route
    must not depend on that having happened."""
    response = client.post("/api/virtual_switch/a%2Fb/toggle")
    assert response.status_code in (404, 405), response.status_code
