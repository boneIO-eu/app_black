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


def sanitize_string(s: str) -> str:
    import re
    s = strip_accents(s.replace(' ', '_'))
    s = re.sub(r'[^a-zA-Z0-9_-]', '', s)
    return s.lower()

def sanitize_mqtt_topic(name: str) -> str:
    """
    Sanitize a string to be used as an MQTT topic:
    - Replace spaces with underscores
    - Remove Polish diacritics
    - Remove/replace forbidden characters (leave only a-z, A-Z, 0-9, '_', '-')
    - Convert to lowercase for consistency
    Args:
        name (str): Input string
    Returns:
        str: Sanitized string (lowercase)
    """

    from .logger import _LOGGER

    original = name
    # Zamień spacje na podkreślenia
    name = sanitize_string(name)
    # Usuń polskie znaki
    _LOGGER.debug(f"Sanitized MQTT topic: '{original}' -> '{name}'")
    return name


def open_json(path: str, model: str) -> dict:
    """Open json file.
    
    Searches for {model}.json in the given path and its subdirectories.
    
    Args:
        path: Base directory path to search in
        model: Model name (filename without .json extension)
        
    Returns:
        Loaded JSON data as dictionary
        
    Raises:
        FileNotFoundError: If JSON file is not found
    """
    filename = f"{model}.json"
    
    # First try direct path (backward compatibility)
    direct_path = os.path.join(path, filename)
    if os.path.exists(direct_path):
        with open(direct_path) as db_file:
            return json.load(db_file)
    
    # Search in subdirectories (for new devices/ structure)
    for root, dirs, files in os.walk(path):
        if filename in files:
            file_path = os.path.join(root, filename)
            with open(file_path) as db_file:
                return json.load(db_file)
    
    # File not found
    raise FileNotFoundError(
        f"JSON file '{filename}' not found in '{path}' or its subdirectories"
    )

def find_key_by_value(d, value):
    for k, v in d.items():
        if v == value:
            return k
    return None