"""Template components — composite virtual entities.

Combines existing boneIO primitives (inputs, outputs, sensors) into
higher-level Home Assistant entities (climate, alarm_control_panel, cover, etc.).
"""

from boneio.components.template.alarm_panel import BoneIOAlarmPanel
from boneio.components.template.gate_cover import BoneIOGateCover
from boneio.components.template.thermostat import BoneIOThermostat
from boneio.components.template.timed_output import TimedOutput

__all__ = [
    "BoneIOThermostat",
    "BoneIOAlarmPanel",
    "BoneIOGateCover",
    "TimedOutput",
]
