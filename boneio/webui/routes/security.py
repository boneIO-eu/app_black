"""Security posture endpoint.

Admin only, and deliberately so: a list of what is still unlocked on this
controller is a shopping list for anyone who should not have it. The policy
module enforces that; this route does not repeat the check.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from boneio.core.config.yaml_patch import YamlPatchError, set_block_list
from boneio.core.config.yaml_util import load_yaml_file
from boneio.core.security import framing
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


def _load_config() -> dict:
    """Read config.yaml.

    Loaded through the normal loader so ``!secret`` is resolved: a shipped
    default moved into secrets.yaml is still a shipped default.

    Returns:
        The parsed configuration, or an empty dict when it cannot be read.
    """
    try:
        loaded = load_yaml_file(_app_state.yaml_config_file)
        return loaded if isinstance(loaded, dict) else {}
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not read configuration for the security check: %s", err)
        return {}


def current_posture() -> Posture:
    """Evaluate this controller's security posture.

    Never raises: the panel, the post-update prompt and the Home Assistant
    sensor all call this, and a device that cannot answer is more useful
    saying so than failing.

    Returns:
        The evaluated posture.
    """
    config = _load_config()
    cloud_active = False

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


# ----------------------------------------------------------- framing policy


class FrameAncestorsRequest(BaseModel):
    """Who may embed this panel in a frame.

    Deliberately not a list of raw CSP sources. A trailing slash makes an
    origin invalid and a stray ``*`` widens the policy to everything, both of
    which fail silently in a way only a browser console reveals. The panel asks
    the two questions that matter and the tokens are composed here.
    """

    #: False writes ``*``: framing by anyone, chosen on purpose.
    restrict: bool = True
    #: Origins allowed alongside ``self`` — a Home Assistant server whose
    #: dashboard frames this device directly, rather than through the add-on's
    #: proxy.
    extra_origins: list[str] = Field(default_factory=list)


#: An origin and nothing else: scheme, host, optional port. No path, no query,
#: no wildcard, no whitespace — each of which either breaks the directive or
#: widens it further than the person asking realises.
_ORIGIN_RE = re.compile(
    r"^https?://"
    r"(?:\[[0-9A-Fa-f:]+\]|[A-Za-z0-9.-]+)"
    r"(?::\d{1,5})?$"
)


def _clean_origins(origins: list[str]) -> list[str]:
    """Validate and normalise the extra origins.

    Args:
        origins: Origins as typed by the administrator.

    Returns:
        Cleaned origins, in the order given, without duplicates.

    Raises:
        HTTPException: If any entry is not a bare origin.
    """
    cleaned: list[str] = []
    for raw in origins:
        origin = str(raw).strip().rstrip("/")
        if not origin:
            continue
        if not _ORIGIN_RE.match(origin):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"'{raw}' is not an address this can use. Give the server's "
                    "address only, like https://homeassistant.local:8123 — no "
                    "path and no wildcard."
                ),
            )
        if origin not in cleaned:
            cleaned.append(origin)
    return cleaned


def _describe(raw: object) -> dict:
    """Describe a stored frame_ancestors value in the terms the panel asks in.

    Args:
        raw: The configured value — a list, an older string, or None.

    Returns:
        Dictionary with the tokens, the two answers the card shows, and the
        directive as the browser will receive it.
    """
    tokens = framing.effective(raw)
    keywords = set(framing.DEFAULT_FRAME_ANCESTORS) | {framing.WILDCARD}
    return {
        "tokens": list(tokens),
        "restrict": not framing.is_unrestricted(tokens),
        "extra_origins": [t for t in tokens if t not in keywords],
        "value": framing.to_csp(tokens),
        "configured": bool(framing.normalize(raw)),
        "default": list(framing.DEFAULT_FRAME_ANCESTORS),
    }


@router.get("/frame-ancestors")
async def get_frame_ancestors():
    """Report which sites may embed this panel.

    Returns:
        The current setting, plus whether it came from config.yaml or the
        default.
    """
    config = _load_config()
    web = config.get("web") if isinstance(config.get("web"), dict) else {}
    security = web.get("security") if isinstance(web.get("security"), dict) else {}
    return _describe(security.get("frame_ancestors"))


@router.put("/frame-ancestors")
async def set_frame_ancestors(payload: FrameAncestorsRequest):
    """Write the framing policy into config.yaml.

    Args:
        payload: The administrator's answers.

    Returns:
        The stored setting, with a note that a restart is needed.

    Raises:
        HTTPException: If an origin is malformed or the file cannot be edited.
    """
    if payload.restrict:
        tokens = [*framing.DEFAULT_FRAME_ANCESTORS, *_clean_origins(payload.extra_origins)]
    else:
        # One token, and no origins: listing sites alongside * would suggest
        # they mean something.
        tokens = [framing.WILDCARD]

    config_file = getattr(_app_state, "yaml_config_file", None)
    if not config_file:
        raise HTTPException(status_code=503, detail="No configuration file is loaded.")

    try:
        set_block_list(config_file, ("web", "security"), "frame_ancestors", tokens)
    except YamlPatchError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except OSError as err:
        raise HTTPException(status_code=500, detail=str(err)) from err

    helper = getattr(_app_state, "config_helper", None)
    if helper is not None:
        try:
            # The header is built once, when the app starts.
            helper.set_restart_required("web")
        except Exception as err:  # noqa: BLE001
            # The file is already written. Reporting a failure here would say
            # the setting did not take when it did; the banner is the loss.
            _LOGGER.warning("Could not flag the restart banner: %s", err)

    _LOGGER.info("frame-ancestors set to %s", tokens)
    return {**_describe(tokens), "restart_required": True}
