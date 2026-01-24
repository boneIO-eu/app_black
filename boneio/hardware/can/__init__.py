"""CAN bus and CANopen communication module for boneIO."""

from boneio.hardware.can.client import CANopenClient
from boneio.hardware.can.node import BoneIOCANNode

__all__ = [
    "CANopenClient",
    "BoneIOCANNode",
]
