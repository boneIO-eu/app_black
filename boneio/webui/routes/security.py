"""Security posture endpoint.

Admin only, and deliberately so: a list of what is still unlocked on this
controller is a shopping list for anyone who should not have it. The policy
module enforces that; this route does not repeat the check.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from boneio.core.config.yaml_util import load_yaml_file
from boneio.core.security.posture import Posture, evaluate
from boneio.webui.middleware.auth import (
    get_user_store,
    is_anonymous_allowed,
    is_auth_required,
)

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/security", tags=["security"])

_app_state = None


def set_app_state(app_state) -> None:
    """Attach app state so the posture can read the live configuration.

    Args:
        app_state: The FastAPI application state.
    """
    global _app_state
    _app_state = app_state


def current_posture() -> Posture:
    """Evaluate this controller's security posture.

    Never raises: the panel, the post-update prompt and the Home Assistant
    sensor all call this, and a device that cannot answer is more useful
    saying so than failing.

    Returns:
        The evaluated posture.
    """
    config = None
    cloud_active = False

    try:
        # Loaded through the normal loader so !secret is resolved: a default
        # password moved into secrets.yaml is still the default password.
        loaded = load_yaml_file(_app_state.yaml_config_file)
        if isinstance(loaded, dict):
            config = loaded
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not read configuration for the security check: %s", err)

    try:
        helper = getattr(_app_state, "config_helper", None)
        cloud_reg = getattr(helper, "_cloud_reg", None) if helper else None
        if cloud_reg is not None:
            cloud_active = bool(cloud_reg.is_cloud_config_active())
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not read cloud state for the security check: %s", err)

    store = get_user_store()
    try:
        provisioned = bool(store and store.is_provisioned())
    except Exception:  # noqa: BLE001
        provisioned = True  # never claim a set-up device is unclaimed

    return evaluate(
        config,
        is_provisioned=provisioned,
        anonymous_allowed=is_anonymous_allowed(),
        auth_required=is_auth_required(),
        cloud_active=cloud_active,
    )


@router.get("/posture")
async def get_posture():
    """Report every security check and a summary of the failures.

    Returns:
        Dictionary with the checks and a per-severity summary.
    """
    return current_posture().to_dict()
