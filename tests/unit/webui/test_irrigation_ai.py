"""Tests for irrigation AI wizard API endpoints."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


def _has_fastapi() -> bool:
    """Check if fastapi and the irrigation router are importable."""
    try:
        import fastapi  # noqa: F401
        from fastapi.testclient import TestClient  # noqa: F401
        from boneio.webui.routes.irrigation import router  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(
    not _has_fastapi(),
    reason="fastapi not installed in test environment",
)


# ─── Helpers ────────────────────────────────────────────────────────────────

class FakeOutput:
    """Minimal output mock."""
    def __init__(self, id: str, name: str, output_type: str = "switch"):
        self.id = id
        self.name = name
        self._output_type = output_type

    @property
    def output_type(self):
        return self._output_type


class FakeZone:
    """Minimal zone mock with valve."""
    def __init__(self, id: str, name: str, valve_id: str):
        self.id = id
        self.name = name
        self.valve = MagicMock(id=valve_id)
        self.run_duration = 600  # seconds
        self.run_every_n = 1
        self.enabled = True


class FakeWaterSource:
    """Minimal water source mock."""
    def __init__(self, id: str, name: str, output_ids: list[str]):
        self.id = id
        self.name = name
        self.output_ids = output_ids
        self.outputs = [MagicMock(id=oid) for oid in output_ids]


class FakeController:
    """Minimal irrigation controller mock."""
    def __init__(self, id: str, name: str, zones=None, water_sources=None, schedule=None):
        self.id = id
        self.name = name
        self.zones = zones or []
        self.water_sources = water_sources or []
        self._schedule = schedule or []
        self.state = MagicMock(value="IDLE")
        self._multiplier = 1.0
        self._repeat = 0
        self._auto_advance = True
        self._reverse = False
        self._standby = False
        self._skip_next_run = False
        self._pause_timeout_s = 1800
        self._active_zone_idx = None
        self._active_zone_remaining_s = None
        self._run_start_utc = None
        self.active_water_source = None


def create_test_app(manager):
    """Create a FastAPI test app with mocked manager."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from boneio.webui.routes.irrigation import router, get_manager

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_manager] = lambda: manager
    return TestClient(app)


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def mock_outputs():
    """Create test outputs."""
    return {
        "out_01": FakeOutput("out_01", "OUT 01", "switch"),
        "out_02": FakeOutput("out_02", "OUT 02", "switch"),
        "out_03": FakeOutput("out_03", "Pompa deszczówka", "valve"),
        "out_04": FakeOutput("out_04", "Zawór trawnik 1", "valve"),
        "out_05": FakeOutput("out_05", "Zawór trawnik 2", "valve"),
    }


@pytest.fixture
def mock_manager(mock_outputs):
    """Create a mock manager with outputs and no controllers."""
    manager = MagicMock()
    manager.outputs.get_all_outputs.return_value = mock_outputs
    manager.irrigation._controllers = {}
    manager._device_name = "boneIO Black Compact"
    return manager


@pytest.fixture
def mock_manager_with_controller(mock_outputs):
    """Create a mock manager with outputs and an existing controller."""
    manager = MagicMock()
    manager.outputs.get_all_outputs.return_value = mock_outputs
    manager._device_name = "boneIO Black Compact"

    ctrl = FakeController(
        id="garden",
        name="Ogród",
        zones=[FakeZone("lawn_1", "Trawnik 1", "out_04")],
        water_sources=[FakeWaterSource("rainwater", "Deszczówka", ["out_03"])],
        schedule=[{"time": "06:00", "days": "daily"}],
    )
    manager.irrigation._controllers = {"garden": ctrl}
    return manager


# ─── Tests: AI Context ─────────────────────────────────────────────────────

class TestAiContext:
    """Tests for GET /api/irrigation/ai-context."""

    def test_returns_all_outputs(self, mock_manager, mock_outputs):
        """All outputs should appear in the context."""
        client = create_test_app(mock_manager)
        resp = client.get("/api/irrigation/ai-context")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["available_outputs"]) == len(mock_outputs)

    def test_marks_unused_outputs_available(self, mock_manager):
        """Outputs not used by irrigation should be marked as available."""
        client = create_test_app(mock_manager)
        resp = client.get("/api/irrigation/ai-context")
        data = resp.json()
        for out in data["available_outputs"]:
            assert out["in_use"] is False

    def test_marks_used_outputs(self, mock_manager_with_controller):
        """Outputs used by irrigation should be marked in_use with used_by."""
        client = create_test_app(mock_manager_with_controller)
        resp = client.get("/api/irrigation/ai-context")
        data = resp.json()
        out_map = {o["id"]: o for o in data["available_outputs"]}

        assert out_map["out_04"]["in_use"] is True
        assert "irrigation:garden:zone:lawn_1" in out_map["out_04"]["used_by"]

        assert out_map["out_03"]["in_use"] is True
        assert "irrigation:garden:source:rainwater" in out_map["out_03"]["used_by"]

        # Unused outputs should still be available
        assert out_map["out_01"]["in_use"] is False

    def test_includes_existing_controllers(self, mock_manager_with_controller):
        """Existing controllers should appear in context."""
        client = create_test_app(mock_manager_with_controller)
        resp = client.get("/api/irrigation/ai-context")
        data = resp.json()
        assert len(data["existing_controllers"]) == 1
        ctrl = data["existing_controllers"][0]
        assert ctrl["id"] == "garden"
        assert ctrl["name"] == "Ogród"
        assert len(ctrl["zones"]) == 1
        assert len(ctrl["water_sources"]) == 1

    def test_schema_summary_present(self, mock_manager):
        """Schema summary should be present and have expected keys."""
        client = create_test_app(mock_manager)
        resp = client.get("/api/irrigation/ai-context")
        data = resp.json()
        assert "schema_summary" in data
        assert "controller_fields" in data["schema_summary"]
        assert "zone_fields" in data["schema_summary"]
        assert "water_source_fields" in data["schema_summary"]

    def test_device_name(self, mock_manager):
        """Device name should come from manager."""
        client = create_test_app(mock_manager)
        resp = client.get("/api/irrigation/ai-context")
        data = resp.json()
        assert data["device_name"] == "boneIO Black Compact"


# ─── Tests: Import ──────────────────────────────────────────────────────────

class TestImport:
    """Tests for POST /api/irrigation/import."""

    def test_import_valid_config(self, mock_manager):
        """Valid import should return OK with controller IDs."""
        client = create_test_app(mock_manager)
        payload = {
            "controllers": [{
                "id": "new_ctrl",
                "name": "New Controller",
                "auto_advance": True,
                "schedule": [{"time": "06:00", "days": "daily"}],
                "zones": [{
                    "id": "zone_a",
                    "name": "Zone A",
                    "valve": "out_01",
                    "run_duration": 10,
                    "run_every_n": 1,
                }],
                "water_sources": [{
                    "id": "main_water",
                    "name": "City Water",
                    "outputs": ["out_02"],
                }],
            }],
        }
        resp = client.post("/api/irrigation/import", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "new_ctrl" in data["controllers"]
        assert len(data["conflicts"]) == 0

    def test_import_invalid_valve_id(self, mock_manager):
        """Import with unknown valve ID should fail with 400."""
        client = create_test_app(mock_manager)
        payload = {
            "controllers": [{
                "id": "bad_ctrl",
                "name": "Bad",
                "zones": [{"id": "z1", "name": "Z1", "valve": "nonexistent_output", "run_duration": 5}],
            }],
        }
        resp = client.post("/api/irrigation/import", json=payload)
        assert resp.status_code == 400

    def test_import_invalid_water_source_output(self, mock_manager):
        """Import with unknown water source output should fail."""
        client = create_test_app(mock_manager)
        payload = {
            "controllers": [{
                "id": "bad_ctrl",
                "name": "Bad",
                "zones": [{"id": "z1", "name": "Z1", "valve": "out_01", "run_duration": 5}],
                "water_sources": [{"id": "ws1", "name": "WS1", "outputs": ["bad_output"]}],
            }],
        }
        resp = client.post("/api/irrigation/import", json=payload)
        assert resp.status_code == 400

    def test_import_empty_controllers(self, mock_manager):
        """Import with no controllers should fail."""
        client = create_test_app(mock_manager)
        resp = client.post("/api/irrigation/import", json={"controllers": []})
        assert resp.status_code == 400

    def test_import_detects_conflicts(self, mock_manager_with_controller):
        """Import should detect conflicting controller IDs."""
        client = create_test_app(mock_manager_with_controller)
        payload = {
            "controllers": [{
                "id": "garden",
                "name": "Garden Updated",
                "zones": [{"id": "z1", "name": "Z1", "valve": "out_01", "run_duration": 10}],
            }],
        }
        resp = client.post("/api/irrigation/import", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "garden" in data["conflicts"]

    def test_import_config_format(self, mock_manager):
        """Import should return properly formatted config for YAML."""
        client = create_test_app(mock_manager)
        payload = {
            "controllers": [{
                "id": "test_ctrl",
                "name": "Test",
                "zones": [{"id": "z1", "name": "Z1", "valve": "out_01", "run_duration": 15, "run_every_n": 2}],
                "water_sources": [{"id": "ws1", "name": "WS1", "outputs": ["out_02"]}],
            }],
        }
        resp = client.post("/api/irrigation/import", json=payload)
        data = resp.json()
        cfg = data["config"][0]
        assert cfg["id"] == "test_ctrl"
        # run_duration should be formatted as "15min"
        assert cfg["zones"][0]["run_duration"] == "15min"
        # run_every_n > 1 should be included
        assert cfg["zones"][0]["run_every_n"] == 2
