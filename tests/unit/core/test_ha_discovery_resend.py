"""The HA discovery resend must publish what setup published.

``Manager.publish_discovery`` calls every sub-manager's
``send_ha_autodiscovery`` right after setup, and the result replaces the
cached payload that is replayed whenever Home Assistant comes back online.
The resend rebuilds each payload from the entity object, so anything setup
took from the config and did not keep on the entity is lost: without
``area`` HA moves the entity back under the main device, and without
``show_in_ha`` hidden entities appear in HA.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

mock_gpiod = MagicMock()
sys.modules.setdefault("gpiod", mock_gpiod)
sys.modules.setdefault("gpiod.line", mock_gpiod.line)

from boneio.components.input import GpioInputBinarySensor
from boneio.core.config.config_helper import ConfigHelper
from boneio.core.manager.inputs import InputManager
from boneio.core.manager.outputs import OutputManager
from boneio.core.manager.sensors import SensorManager


@pytest.fixture
def manager():
    config_helper = ConfigHelper(name="black", serial_override="blk0001")
    config_helper.set_areas([{"id": "salon", "name": "Salon"}])
    return SimpleNamespace(_config_helper=config_helper, publish_ha_discovery=MagicMock())


def _published(manager) -> dict[str, dict]:
    return {c.kwargs["id"]: c.kwargs["payload"] for c in manager.publish_ha_discovery.call_args_list}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_output_resend_keeps_group_area_and_skips_hidden_remote(manager):
    outputs = OutputManager.__new__(OutputManager)
    outputs._manager = manager
    outputs._outputs = {
        "remote_hidden": SimpleNamespace(
            output_type="switch", name="Remote", area=None, show_in_ha=False, adjustable_duration_enabled=False
        ),
    }
    member = SimpleNamespace(id="out1")
    outputs._configured_output_groups = {
        "grupa": SimpleNamespace(name="Grupa", output_type="switch", area="salon", group_members=[member]),
    }

    _run(outputs.send_ha_autodiscovery())
    published = _published(manager)

    assert set(published) == {"grupa"}
    assert published["grupa"]["device"]["name"] == "black - Salon"


def _binary_sensor(input_id: str, *, area: str | None, show_in_ha: bool) -> MagicMock:
    sensor = MagicMock(spec=GpioInputBinarySensor)
    sensor.id = input_id
    sensor.name = input_id
    sensor.device_class = "door"
    sensor.area = area
    sensor.show_in_ha = show_in_ha
    return sensor


def test_input_resend_keeps_area_and_skips_hidden(manager):
    inputs = InputManager.__new__(InputManager)
    inputs._manager = manager
    inputs._inputs = {
        "P9_11": _binary_sensor("drzwi", area="salon", show_in_ha=True),
        "P9_12": _binary_sensor("hidden", area=None, show_in_ha=False),
    }

    _run(inputs.send_ha_autodiscovery())
    published = _published(manager)

    assert set(published) == {"drzwi"}
    assert published["drzwi"]["device"]["name"] == "black - Salon"


def test_sensor_resend_keeps_area_and_skips_hidden(manager):
    sensors = SensorManager.__new__(SensorManager)
    sensors._manager = manager
    sensors._temp_sensors = []
    sensors._ina219_sensors = []
    sensors._ina226_sensors = []
    sensors._system_sensors = []
    sensors._virtual_energy_sensors = []
    sensors._dallas_sensors = [
        SimpleNamespace(id="ds_salon", name="Salon temp", unit_of_measurement="°C", area="salon", show_in_ha=True),
        SimpleNamespace(id="ds_hidden", name="Hidden", unit_of_measurement="°C", area=None, show_in_ha=False),
    ]
    sensors._adc_sensors = [
        SimpleNamespace(id="adc_salon", name="Salon adc", area="salon", show_in_ha=True),
        SimpleNamespace(id="adc_hidden", name="Hidden adc", area=None, show_in_ha=False),
    ]

    _run(sensors.send_ha_autodiscovery())
    published = _published(manager)

    assert set(published) == {"ds_salon", "adc_salon"}
    assert published["ds_salon"]["device"]["name"] == "black - Salon"
    assert published["adc_salon"]["device"]["name"] == "black - Salon"
