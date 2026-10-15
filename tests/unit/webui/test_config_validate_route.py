"""POST /api/config/{section}/validate: the save route's verdict, without the save.

A client that is not the panel's form — a script, an assistant — gets a section
wrong far more often than a form does. It must be able to ask whether a section
would be accepted, and read every reason it would not, before anything reaches
config.yaml.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.core.config.yaml_util import validate_section
from boneio.webui.routes import config_core

BONEIO = {"config_version": 7, "name": "test", "version": 1.1, "device_type": "24x16A"}
OUTPUTS = [
    {"name": "OUT 01", "boneio_output": "OUT_01", "output_type": "switch"},
    {"name": "OUT 02", "boneio_output": "OUT_02", "output_type": "light"},
]


class TestValidateSection:
    def test_a_valid_section_has_no_errors(self):
        assert validate_section("output", OUTPUTS, BONEIO) == []

    def test_each_error_names_the_field_it_is_about(self):
        bad = [dict(OUTPUTS[0]), {**OUTPUTS[1], "output_type": "banana"}]
        errors = validate_section("output", bad, BONEIO)
        assert len(errors) == 1
        assert errors[0].startswith("output[1].output_type: ")

    def test_nested_dict_errors_carry_the_whole_path(self):
        errors = validate_section("mqtt", {"host": 5, "port": "abc"}, BONEIO)
        assert sorted(errors) == [
            "mqtt.host: must be of string type",
            "mqtt.port: must be of integer type",
        ]

    def test_an_output_the_board_does_not_have_is_an_error_not_a_crash(self):
        errors = validate_section("output", [{"boneio_output": "OUT_99"}], BONEIO)
        assert len(errors) == 1 and "OUT_99" in errors[0]

    def test_a_section_the_schema_does_not_know_is_an_error(self):
        assert validate_section("outputz", [], BONEIO) == ["Unknown configuration section: 'outputz'"]

    def test_errors_in_the_stored_boneio_section_are_not_reported(self):
        boneio = {k: v for k, v in BONEIO.items() if k != "name"}
        assert validate_section("output", OUTPUTS, boneio) == []
        assert validate_section("boneio", boneio, None) == ["boneio.name: required field"]

    def test_the_input_is_left_as_it_was(self):
        data = [dict(o) for o in OUTPUTS]
        validate_section("output", data, BONEIO)
        assert data == OUTPUTS


@pytest.fixture
def device(tmp_path):
    """The config routes over a stored config, with reload watched."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("output: []\n", encoding="utf-8")

    state = MagicMock()
    state.yaml_config_file = str(config_file)
    state.manager.reload_config = AsyncMock(return_value={"status": "success"})
    state.manager.config_helper.get_section.return_value = []
    config_core.set_app_state(state)

    config_core._config_cache["data"] = {"boneio": BONEIO, "output": []}
    config_core._config_cache["mtime"] = float("inf")
    yield state
    config_core._config_cache["data"] = None
    config_core._config_cache["mtime"] = 0


@pytest.mark.asyncio
async def test_the_route_accepts_a_valid_section_and_writes_nothing(device):
    before = open(device.yaml_config_file, encoding="utf-8").read()

    result = await config_core.validate_section_content("output", OUTPUTS)

    assert result == {"valid": True, "errors": []}
    assert open(device.yaml_config_file, encoding="utf-8").read() == before
    device.manager.reload_config.assert_not_called()


@pytest.mark.asyncio
async def test_the_route_reports_schema_errors(device):
    result = await config_core.validate_section_content(
        "output", [{**OUTPUTS[0], "output_type": "banana"}]
    )
    assert result["valid"] is False
    assert result["errors"][0].startswith("output[0].output_type: ")


@pytest.mark.asyncio
async def test_the_route_runs_the_checks_the_save_runs(device):
    result = await config_core.validate_section_content(
        "lox_udp", {"enabled": True, "host": "not a host!"}
    )
    assert result["valid"] is False
    assert any("not a host!" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_the_save_refuses_what_validation_reports(device):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as err:
        await config_core.update_section_content(
            "lox_udp", {"enabled": True, "host": "not a host!"}
        )
    assert err.value.status_code == 422
    assert any("not a host!" in e for e in err.value.detail["errors"])
