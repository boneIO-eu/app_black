"""LM75 temp sensor."""
from adafruit_pct2075 import PCT2075

from boneio.const import LM75

from . import TempSensor


class LM75Sensor(TempSensor):
    """Represent LM75 sensor in BoneIO."""

    SensorClass = PCT2075
    DefaultName = LM75
