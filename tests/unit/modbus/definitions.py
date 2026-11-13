"""Minimal device definitions for tests that build a coordinator by hand."""

from __future__ import annotations

from boneio.modbus.definition import DeviceDefinition


def definition(registers_base: list | None = None, **header) -> DeviceDefinition:
    """A valid definition with the required header fields filled in."""
    return DeviceDefinition.model_validate(
        {
            "model": "Test device",
            "manufacturer": "boneIO",
            "description": "Test device",
            "category": "other",
            "default_address": 1,
            "default_update_interval": "60s",
            "registers_base": registers_base or [],
            **header,
        }
    )
