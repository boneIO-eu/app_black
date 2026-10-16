"""The usage summary an AI assistant suggests automations from.

Admin and API keys from the Propose scope up (policy.py): it says when
somebody is at home. Empty, with the reason, while the history is off.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from boneio.webui.routes import config_core

router = APIRouter(prefix="/api", tags=["usage"])


@router.get("/usage-summary")
async def usage_summary(days: int = Query(14, ge=1, le=90)):
    """Hourly usage of outputs, covers and inputs over the last ``days``."""
    history = getattr(config_core._get_app_state().manager, "usage_history", None)
    summary = history.summary(days) if history else {"enabled": False}
    if not summary.get("enabled"):
        summary["detail"] = (
            "Usage history is off. An administrator can turn it on in the usage_history "
            "section of the settings; it starts counting from then."
        )
    return summary
