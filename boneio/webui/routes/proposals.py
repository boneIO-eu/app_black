"""Config changes an agent proposes and an administrator approves.

A key in the ``propose`` scope files a section here instead of saving it;
it is checked as a save would check it, so what waits in the panel is
something that can be saved. Approving goes through the save route itself,
with every guard it has, and reloads the section as the panel would.

Sections holding a secret are refused: the save puts a stored secret back
wherever the mask comes back, so a proposal that kept a password masked and
changed the host beside it would, once approved, send the password there.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import difflib
import hashlib
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel

from boneio.core.config.proposals import PROPOSALS_FILENAME, ProposalError, ProposalStore
from boneio.core.config.sections import RESTART_REQUIRED_SECTIONS, secret_sections
from boneio.core.config.yaml_util import _strip_empty_strings_deep, validate_section
from boneio.core.utils.timeperiod import plain_time_periods
from boneio.webui import security_events
from boneio.webui.routes import config_core

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["proposals"])

_stores: dict[Path, ProposalStore] = {}


class NewProposal(BaseModel):
    data: dict | list
    rationale: str = ""


class Approval(BaseModel):
    #: Approve although the section changed since the proposal was made.
    force: bool = False


def _store() -> ProposalStore:
    path = Path(config_core._get_app_state().yaml_config_file).parent / PROPOSALS_FILENAME
    if path not in _stores:
        _stores[path] = ProposalStore(path)
    return _stores[path]


async def _current(section: str) -> Any:
    """The section as GET /api/config shows it to an administrator."""
    return (await config_core.get_parsed_config())["config"].get(section)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _yaml(value: Any) -> list[str]:
    if value is None:
        return []
    plain = json.loads(json.dumps(value, default=str))
    return yaml.safe_dump(plain, sort_keys=False, allow_unicode=True).splitlines()


def _diff(section: str, current: Any, proposed: Any) -> str:
    return "\n".join(
        difflib.unified_diff(_yaml(current), _yaml(proposed), f"{section} (now)", f"{section} (proposed)", lineterm="")
    )


@router.post("/config/{section}/proposals")
async def propose_section(section: str, body: NewProposal, request: Request):
    """File a change for an administrator to approve; refused if a save would be."""
    if not config_core._SECTION_NAME.match(section):
        raise HTTPException(status_code=404, detail=f"Not a configuration section: '{section}'")
    if section in secret_sections():
        raise HTTPException(
            status_code=403,
            detail=f"'{section}' holds secrets and is changed in the panel only.",
        )
    data = _strip_empty_strings_deep(plain_time_periods(body.data))
    errors = await config_core._section_errors(section, data)
    errors += await asyncio.to_thread(validate_section, section, data, await config_core._stored_boneio())
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": f"Invalid {section} configuration", "errors": errors},
        )
    author = getattr(request.state, "user", None) or ""
    key = getattr(request.state, "api_key", None)
    base = _digest(await _current(section))
    try:
        proposal = await asyncio.to_thread(
            _store().add, section, data, body.rationale, author, base, key.id if key else ""
        )
    except ProposalError as err:
        raise HTTPException(status_code=429, detail=str(err)) from err
    security_events.emit(
        "proposal_filed",
        username=key.owner if key else author,
        client=getattr(getattr(request, "client", None), "host", None),
        where=f"'{section}' from '{key.name if key else author}'",
    )
    return {"proposal": {"id": proposal.id, "section": section, "created_at": proposal.created_at}}


@router.get("/proposals")
async def list_proposals():
    """Pending proposals, each with a diff against the section as it is now."""
    proposals = await asyncio.to_thread(_store().list)
    config = (await config_core.get_parsed_config())["config"] if proposals else {}
    out = []
    for proposal in proposals:
        current = config.get(proposal.section)
        entry = asdict(proposal)
        del entry["data"], entry["base"], entry["key_id"]
        entry["diff"] = _diff(proposal.section, current, proposal.data)
        entry["stale"] = _digest(current) != proposal.base
        entry["restart_required"] = proposal.section in RESTART_REQUIRED_SECTIONS
        out.append(entry)
    return {"proposals": out}


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str, request: Request, body: Approval | None = Body(None)):
    """Save the proposed section, through the save route, and reload it."""
    store = _store()
    try:
        proposal = await asyncio.to_thread(store.get, proposal_id)
    except ProposalError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    if not (body and body.force) and _digest(await _current(proposal.section)) != proposal.base:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"'{proposal.section}' changed since this was proposed; "
                "approving it would undo those changes.",
                "stale": True,
            },
        )
    result = await config_core.update_section_content(proposal.section, copy.deepcopy(proposal.data))
    _LOGGER.info(
        "Proposal %s for '%s' from %s approved by %s",
        proposal.id, proposal.section, proposal.author, getattr(request.state, "user", None),
    )
    # Out of the queue once saved, before the reload: a reload that fails
    # leaves a saved section, and approving it again would save it twice.
    with contextlib.suppress(ProposalError):  # approved twice at once
        await asyncio.to_thread(store.remove, proposal.id)
    if not result.get("restart_required"):
        await config_core.reload_configuration([proposal.section])
    return result


@router.delete("/proposals/{proposal_id}")
async def reject_proposal(proposal_id: str):
    """Drop a proposal unsaved."""
    try:
        await asyncio.to_thread(_store().remove, proposal_id)
    except ProposalError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return {"rejected": proposal_id}
