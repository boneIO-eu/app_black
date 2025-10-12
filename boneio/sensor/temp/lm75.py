"""LM75 temp sensor."""
from boneio.helper.i2c import PCT2075

from boneio.const import LM75

from . import TempSensor


class LM75Sensor(TempSensor):
    """Represent LM75 sensor in BoneIO."""

    SensorClass = PCT2075
    DefaultName = LM75
