"""Migration v2: Convert transition field from float to timeperiod string.

Before: transition: 2 (bare number, interpreted as seconds)
After:  transition: 2s (timeperiod string with unit)
"""

from __future__ import annotations

import logging
import re

from boneio.core.config.migrations import register_migration

_LOGGER = logging.getLogger(__name__)


def _persist_transition(config_file: str) -> None:
    """Replace bare-number transition values with timeperiod strings in YAML file.

    Matches lines like ``transition: 2`` or ``transition: 0.5`` and appends ``s``.

    Args:
        config_file: Path to the YAML config file.
    """
    with open(config_file, encoding="utf-8") as f:
        lines = f.readlines()

    updated = False
    updated_lines: list[str] = []
    transition_re = re.compile(r"^(\s*transition:\s*)(\d+(?:\.\d+)?)\s*$")

    for line in lines:
        m = transition_re.match(line)
        if m:
            num_val = float(m.group(2))
            if num_val == 0:
                # Remove transition: 0 entirely — not meaningful
                _LOGGER.info(
                    "Removing from config file: %s", line.rstrip(),
                )
                updated = True
                continue  # skip this line
            new_line = f"{m.group(1)}{m.group(2)}s\n"
            updated_lines.append(new_line)
            updated = True
            _LOGGER.info(
                "Replaced in config file: %s -> %s",
                line.rstrip(),
                new_line.rstrip(),
            )
        else:
            updated_lines.append(line)

    if updated:
        with open(config_file, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)


@register_migration(
    version=2,
    name="transition: float -> timeperiod string",
    migrate_file=_persist_transition,
)
def migrate(doc: dict) -> dict:
    """Convert transition fields from int/float to timeperiod strings.

    Walks through event and binary_sensor sections, finding action
    definitions with a bare numeric transition value and converting
    them to strings with an ``s`` suffix.

    Args:
        doc: Raw config dict.

    Returns:
        Migrated config dict.
    """
    for section_name in ("event", "binary_sensor"):
        for item in doc.get(section_name, []) or []:
            if not isinstance(item, dict):
                continue
            actions = item.get("actions")
            if not isinstance(actions, dict):
                continue
            for _click_type, action_list in actions.items():
                if not isinstance(action_list, list):
                    continue
                for action_def in action_list:
                    if not isinstance(action_def, dict):
                        continue
                    if "transition" in action_def:
                        val = action_def["transition"]
                        if isinstance(val, (int, float)):
                            if val == 0:
                                _LOGGER.info(
                                    "Removing transition: 0 from %s action (not meaningful)",
                                    section_name,
                                )
                                del action_def["transition"]
                            else:
                                new_val = f"{val}s"
                                _LOGGER.info(
                                    "Migrating transition: %s -> '%s' in %s action",
                                    val,
                                    new_val,
                                    section_name,
                                )
                                action_def["transition"] = new_val

    return doc
