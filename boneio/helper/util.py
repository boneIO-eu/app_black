import json
import os
import unicodedata
from typing import Any, TypeVar
from collections.abc import Callable

CALLABLE_T = TypeVar("CALLABLE_T", bound=Callable[..., Any])
CALLBACK_TYPE = Callable[[], None]


def callback(func: CALLABLE_T) -> CALLABLE_T:
    """Annotation to mark method as safe to call from within the event loop."""
    setattr(func, "_boneio_callback", True)
    return func


def is_callback(func: Callable[..., Any]) -> bool:
    """Check if function is safe to be called in the event loop."""
    return getattr(func, "_boneio_callback", False) is True


def strip_accents(s):
    """Remove accents and spaces from a string."""
    return "".join(
        c
        for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn" and c != " "
    )


def sanitize_mqtt_topic(name: str) -> str:
    """
    Sanitize a string to be used as an MQTT topic:
    - Replace spaces with underscores
    - Remove Polish diacritics
    - Remove/replace forbidden characters (leave only a-z, A-Z, 0-9, '_', '-')
    Args:
        name (str): Input string
    Returns:
        str: Sanitized string
    """
    import re

    from .logger import _LOGGER

    original = name
    # Zamień spacje na podkreślenia
    name = name.replace(' ', '_')
    # Usuń polskie znaki
    name = strip_accents(name)
    # Zostaw tylko dozwolone znaki
    name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    _LOGGER.debug(f"Sanitized MQTT topic: '{original}' -> '{name}'")
    return name


def open_json(path: str, model: str) -> dict:
    """Open json file."""
    file = f"{os.path.join(path)}/{model}.json"
    with open(file) as db_file:
        datastore = json.load(db_file)
        return datastore

def find_key_by_value(d, value):
    for k, v in d.items():
        if v == value:
            return k
    return None