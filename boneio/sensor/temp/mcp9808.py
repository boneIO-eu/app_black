"""MCP9808 temp sensor."""

from . import TempSensor
from adafruit_mcp9808 import MCP9808
from boneio.const import MCP_TEMP_9808


class MCP9808Sensor(TempSensor):
    """Represent MCP9808 sensor in BoneIO."""

    SensorClass = MCP9808
    DefaultName = MCP_TEMP_9808
