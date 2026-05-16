"""HTTP endpoints for expansion board lifecycle.

Endpoints:
    POST /api/config/expander         — add an expansion board
    POST /api/config/expander/remove  — remove all expansion boards

Register via ``register_routes(app)`` from ``boneio/webui/app.py``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Body, FastAPI, HTTPException
from yaml import dump as yaml_dump

from boneio.core.config.yaml_util import (
    clear_config_cache,
    load_yaml_file,
    update_config_section,
)
from boneio.modules.expander.yaml_util import (
    EXPANDER_PREFIX,
    filter_out_expander,
)

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

# Expansion files follow the convention `expansion_board_output_<type>.yaml`.
_EXPANSION_FILE_PREFIX = "expansion_board_output_"

# Pattern that captures the include directive on the `output:` line.
# Group 1 contains the file list (space-separated for !include_files).
_OUTPUT_INCLUDE_PATTERN = re.compile(
    r"^output:\s*!include(?:_files)?\s+(.+?)$",
    re.MULTILINE,
)

router = APIRouter(prefix="/api/config", tags=["expander"])


def _get_app_state():
    """Lazy import to avoid circular dependency with webui.routes.config.

    The app-state singleton lives in the core config router; we reuse it to
    keep config-cache invalidation consistent across all config endpoints.
    """
    from boneio.webui.routes.config import _get_app_state as _impl
    return _impl()


def _invalidate_config_cache() -> None:
    """Lazy import for the same reason as ``_get_app_state``."""
    from boneio.webui.routes.config import invalidate_config_cache
    invalidate_config_cache()


def _hex_to_int(addr: str | int) -> int:
    """Convert an MCP address (``"0x21"`` or ``33``) to integer."""
    if isinstance(addr, str) and addr.startswith(("0x", "0X")):
        return int(addr, 16)
    return int(addr)


def _strip_expander_from_main_output(config_file: Path) -> None:
    """Remove stale EX_* entries from the inline ``output:`` section.

    Called before patching ``config.yaml`` includes so the existing
    expansion file isn't wiped by ``update_config_section``.
    """
    current_cfg = load_yaml_file(str(config_file))
    existing_outputs = current_cfg.get("output", [])
    if not isinstance(existing_outputs, list):
        return
    cleaned = filter_out_expander(existing_outputs)
    if len(cleaned) != len(existing_outputs):
        update_config_section(str(config_file), "output", cleaned)


def _patch_output_include(config_text: str, new_files: list[str]) -> str:
    """Replace the ``output:`` include directive with the given file list.

    - 0 files → ``output: []``
    - 1 file → ``output: !include <file>``
    - ≥2 files → ``output: !include_files <files...>``
    """
    if not new_files:
        new_line = "output: []"
    elif len(new_files) == 1:
        new_line = f"output: !include {new_files[0]}"
    else:
        new_line = f"output: !include_files {' '.join(new_files)}"
    return _OUTPUT_INCLUDE_PATTERN.sub(new_line, config_text, count=1)


@router.post("/expander")
async def add_expander(request: dict = Body(...)):
    """Add an expansion board.

    Atomically:
      1. Strips stale EX_* entries from inline output section.
      2. Creates ``expansion_board_output_{board_type}.yaml`` with given outputs.
      3. Patches ``config.yaml`` output directive to ``!include_files``.
      4. Adds ``expander_left`` / ``expander_right`` chips to ``mcp23017``.
      5. Marks the manager as requiring restart for the new hardware.
    """
    try:
        board_type: str = request["board_type"]
        outputs: list = request["outputs"]
    except KeyError as missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required field: {missing.args[0]}",
        ) from missing

    expander_left_addr: str = request.get("expander_left_address", "0x23")
    expander_right_addr: str = request.get("expander_right_address", "0x22")

    app_state = _get_app_state()
    config_file = Path(app_state.yaml_config_file)
    config_dir = config_file.parent

    expansion_filename = f"{_EXPANSION_FILE_PREFIX}{board_type}.yaml"
    expansion_path = config_dir / expansion_filename

    # 1. Strip any stale EX_* entries from main output BEFORE patching include
    _strip_expander_from_main_output(config_file)

    # 2. Patch config.yaml include: replace ALL old expansion files with the new one
    config_text = config_file.read_text(encoding="utf-8")
    include_match = _OUTPUT_INCLUDE_PATTERN.search(config_text)
    if include_match:
        existing_files = [
            f for f in include_match.group(1).strip().split()
            if not f.startswith(_EXPANSION_FILE_PREFIX)
        ]
        # Delete leftover expansion files from older configurations
        for old_path in config_dir.glob(f"{_EXPANSION_FILE_PREFIX}*.yaml"):
            if old_path.name != expansion_filename:
                try:
                    old_path.unlink()
                    _LOGGER.info("Removed stale expansion file: %s", old_path)
                except OSError:
                    pass
        new_files = existing_files + [expansion_filename]
        config_text = _patch_output_include(config_text, new_files)
        config_file.write_text(config_text, encoding="utf-8")
    # else: output is inline — leave config.yaml alone; expansion file still gets
    # created below, frontend can later trigger conversion.

    # 3. Write the expansion file with generated entries
    expansion_path.write_text(
        yaml_dump(outputs, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    # 4. Add expander chips to mcp23017
    current_cfg = load_yaml_file(str(config_file))
    mcp_list = [
        entry for entry in current_cfg.get("mcp23017", [])
        if entry.get("id") not in ("expander_left", "expander_right")
    ]
    mcp_list.append({"id": "expander_left",  "address": _hex_to_int(expander_left_addr)})
    mcp_list.append({"id": "expander_right", "address": _hex_to_int(expander_right_addr)})
    update_config_section(str(config_file), "mcp23017", mcp_list)

    # 5. Invalidate caches and mark restart-required
    clear_config_cache(str(config_file))
    _invalidate_config_cache()

    manager: Manager = app_state.manager
    manager.config_helper.set_restart_required("expander")

    return {"status": "success", "expansion_file": expansion_filename, "restart_required": True}


@router.post("/expander/remove")
async def remove_expander(_request: dict = Body(...)):
    """Remove all expansion boards.

    Atomically:
      1. Strips EX_* entries from inline output section.
      2. Removes ``expansion_board_output_*.yaml`` references from ``config.yaml``.
      3. Deletes every leftover expansion file on disk.
      4. Removes ``expander_left`` / ``expander_right`` from ``mcp23017``.
      5. Marks the manager as requiring restart.
    """
    app_state = _get_app_state()
    config_file = Path(app_state.yaml_config_file)
    config_dir = config_file.parent

    # 1. Strip EX_* entries from inline output FIRST (so update_config_section
    #    split-write doesn't get confused)
    _strip_expander_from_main_output(config_file)

    # 2. Patch config.yaml — drop all expansion file references
    config_text = config_file.read_text(encoding="utf-8")
    include_match = _OUTPUT_INCLUDE_PATTERN.search(config_text)
    if include_match:
        files = [
            f for f in include_match.group(1).strip().split()
            if not f.startswith(_EXPANSION_FILE_PREFIX)
        ]
        config_text = _patch_output_include(config_text, files)
        config_file.write_text(config_text, encoding="utf-8")

    # 3. Delete every leftover expansion file
    for old_path in config_dir.glob(f"{_EXPANSION_FILE_PREFIX}*.yaml"):
        try:
            old_path.unlink()
            _LOGGER.info("Removed expansion file: %s", old_path)
        except OSError:
            pass

    # 4. Remove expander chips from mcp23017
    current_cfg = load_yaml_file(str(config_file))
    mcp_list = [
        entry for entry in current_cfg.get("mcp23017", [])
        if entry.get("id") not in ("expander_left", "expander_right")
    ]
    update_config_section(str(config_file), "mcp23017", mcp_list)

    # 5. Invalidate caches and mark restart-required
    clear_config_cache(str(config_file))
    _invalidate_config_cache()

    manager: Manager = app_state.manager
    manager.config_helper.set_restart_required("expander")

    return {"status": "success", "restart_required": True}


def register_routes(app: FastAPI) -> None:
    """Register expander routes on the given FastAPI app.

    Call from ``boneio/webui/app.py`` after all upstream routers are included.
    """
    app.include_router(router)
