"""Output components (relays, PWM, switches, lights)."""

from boneio.components.output.basic import BasicOutput
from boneio.components.output.buzzer import BuzzerOutput
from boneio.components.output.mcp import MCPOutput
from boneio.components.output.pca import PWMOutput
from boneio.components.output.pcf import PCFOutput

__all__ = [
    "BasicOutput",
    "BuzzerOutput",
    "MCPOutput",
    "PCFOutput",
    "PWMOutput",
]

