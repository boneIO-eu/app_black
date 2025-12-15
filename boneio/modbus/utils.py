"""Modbus utility functions and constants."""
from __future__ import annotations


# Filter operations for sensor value processing
allowed_operations = {"multiply": lambda x, y: x * y if x else x}
