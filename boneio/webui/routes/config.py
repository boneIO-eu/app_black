"""Configuration routes for BoneIO Web UI.

This file re-exports everything from the sub-modules for backward compatibility.
The actual implementation is split into:
- config_core.py (state, cache, GET/PUT config)
- config_backups.py (backups management)
- config_files.py (file editor)
- config_actions.py (quick actions and validation)
- config_discovery.py (HA discovery, interlock groups, Loxone)
"""

from __future__ import annotations

# Re-export core state and variables
from boneio.webui.routes.config_core import (
    _checksum_cache,
    _config_cache,
    _do_cache_rebuild,
    _get_app_state,
    _get_config_mtime,
    _get_config_yaml_files,
    _recompute_config_checksum,
    _schedule_debounced_cache_rebuild,
    get_config_checksum,
    get_manager,
    get_parsed_config,
    invalidate_config_cache,
    reload_configuration,
    router,
    set_app_state,
    set_websocket_manager,
    update_section_content,
)

# Import backup routes to register them on the router and re-export helpers
from boneio.webui.routes.config_backups import (
    _add_backup_metadata_to_tar,
    _apply_serial_override_from_tar,
    _inspect_tar_fileobj,
    create_config_backup,
    delete_config_backup,
    download_config,
    download_config_backup,
    inspect_backup_file,
    inspect_backup_path,
    list_config_backups,
    restore_config,
    restore_config_backup,
)

# Import files routes to register them on the router
from boneio.webui.routes.config_files import (
    get_file_content,
    list_files,
    update_file_content,
)

# Import action routes to register them on the router
from boneio.webui.routes.config_actions import (
    add_quick_action,
    validate_device_type_change,
)

# Import discovery routes to register them on the router
from boneio.webui.routes.config_discovery import (
    get_interlock_groups,
    get_lox_commands,
    get_lox_template,
    remove_ha_discovery,
    resend_ha_discovery,
)

__all__ = [
    "router",
    "set_app_state",
    "set_websocket_manager",
    "_get_app_state",
    "get_manager",
    "_get_config_yaml_files",
    "_recompute_config_checksum",
    "invalidate_config_cache",
    "_do_cache_rebuild",
    "_get_config_mtime",
    "get_parsed_config",
    "update_section_content",
    "reload_configuration",
    "get_config_checksum",
    "remove_ha_discovery",
    "resend_ha_discovery",
    "download_config",
    "restore_config",
    "get_interlock_groups",
    "list_files",
    "get_file_content",
    "update_file_content",
    "validate_device_type_change",
    "list_config_backups",
    "restore_config_backup",
    "create_config_backup",
    "download_config_backup",
    "delete_config_backup",
    "get_lox_template",
    "get_lox_commands",
    "add_quick_action",
    "inspect_backup_file",
    "inspect_backup_path",
    "_config_cache",
    "_checksum_cache",
]
