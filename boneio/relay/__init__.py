"""Relay module."""
from boneio.relay.gpio import GpioRelay
from boneio.relay.mcp import MCPRelay

__all__ = ["MCPRelay", "GpioRelay"]
