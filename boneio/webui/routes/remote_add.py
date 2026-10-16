"""Adding a device the controller found, without typing it in.

``remote_devices`` holds passwords, so an API key may not write the section.
This route builds the one new entry itself, from what discovery reports, and
takes no secret: a boneIO controller announced over MQTT, a WLED device, or
an ESPHome device that answers without credentials. The section is then
saved as the panel saves it - every existing entry passes through with its
secrets masked and put back - or, for a key that may only propose, filed for
an administrator to approve.
"""

from __future__ import annotations

import asyncio
import copy
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from boneio.core.auth.api_keys import KeyScope
from boneio.core.config.models.remote_devices import EspCover, EspLight, EspSwitch
from boneio.core.config.yaml_util import validate_section
from boneio.webui.routes import config_core
from boneio.webui.routes import proposals as proposal_routes

router = APIRouter(prefix="/api/remote-devices", tags=["remote_devices"])

SECTION = "remote_devices"


class NewDevice(BaseModel):
    kind: Literal["boneio", "esphome", "wled"]
    #: A boneIO controller: its id, as discovery lists it.
    device_id: str | None = None
    #: An ESPHome or WLED device: where it answers.
    host: str | None = None
    port: int | None = None
    name: str | None = None
    rationale: str = ""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_") or "device"


def _only(model, entities: list) -> list[dict]:
    """Discovery reports more than the config holds; keep the schema's fields."""
    fields = set(model.model_fields)
    return [{k: v for k, v in e.items() if k in fields} for e in entities if isinstance(e, dict)]


async def _esphome_name(host: str) -> str:
    """What the device calls itself on mDNS; its address when it cannot be found."""
    from boneio.webui.routes import remote_devices

    try:
        scanned = (await remote_devices.scan_esphome_network(timeout=3.0)).get("devices", [])
    except HTTPException:
        scanned = []
    match = next((d for d in scanned if host in (d.get("ip"), d.get("host"))), None)
    if match and match.get("name"):
        return match["name"]
    return host.split(".")[0] if not host.replace(".", "").isdigit() else "esphome_" + host.replace(".", "_")


async def _entry(body: NewDevice) -> dict:
    if body.kind == "boneio":
        remote = getattr(config_core._get_app_state().manager, "remote_devices", None)
        device = remote.get_autodiscovered_device(body.device_id) if remote and body.device_id else None
        if device is None:
            raise HTTPException(status_code=404, detail="No boneIO controller with that id was discovered.")
        found = device.to_dict()
        return {
            "id": found["id"],
            "name": body.name or found.get("name") or found["id"],
            "protocol": "mqtt",
            "device_type": "boneio_black",
            "mqtt": {
                "outputs": [{"id": o["id"], "name": o.get("name") or o["id"]} for o in found.get("outputs") or []],
                "covers": [{"id": c["id"], "name": c.get("name") or c["id"]} for c in found.get("covers") or []],
            },
        }

    if not body.host:
        raise HTTPException(status_code=422, detail="Give the device's host, as discovery listed it.")
    from boneio.webui.routes import remote_devices

    if body.kind == "wled":
        port = body.port or 80
        info = await remote_devices.discover_wled(remote_devices.WLEDDiscoverRequest(host=body.host, port=port))
        return {
            "id": _slug(body.name or info.get("name") or body.host),
            "name": body.name or info.get("name") or body.host,
            "protocol": "wled",
            "device_type": "wled",
            "wled": {"host": body.host, "port": port},
        }

    port = body.port or 6053
    try:
        found = await remote_devices.discover_esphome(
            remote_devices.ESPHomeDiscoverRequest(host=body.host, port=port)
        )
    except HTTPException as err:
        if err.status_code == 502:
            raise HTTPException(
                status_code=422,
                detail="The ESPHome device did not answer without credentials. If it uses an API "
                "encryption key or password, add it in the panel, where the key can be typed in.",
            ) from err
        raise
    name = body.name or await _esphome_name(body.host)
    return {
        "id": _slug(name),
        "name": name,
        "protocol": "esphome_api",
        "device_type": "esphome",
        "esphome_api": {
            "host": body.host,
            "port": port,
            "switches": _only(EspSwitch, found.get("switches") or []),
            "lights": _only(EspLight, found.get("lights") or []),
            "covers": _only(EspCover, found.get("covers") or []),
        },
    }


@router.post("/add-discovered")
async def add_discovered_device(body: NewDevice, request: Request):
    """Add one discovered device to remote_devices; propose it, for a propose key."""
    # The section as the panel is shown it: passwords masked, put back on save.
    current = copy.deepcopy(await proposal_routes._current(SECTION) or [])
    entry = await _entry(body)
    if any(d.get("id") == entry["id"] for d in current):
        raise HTTPException(status_code=409, detail=f"A remote device with id '{entry['id']}' is already configured.")
    host = (entry.get("wled") or entry.get("esphome_api") or {}).get("host")
    if host and any(host == (d.get("wled") or d.get("esphome_api") or {}).get("host") for d in current):
        raise HTTPException(status_code=409, detail=f"A remote device at {host} is already configured.")

    data = [*current, entry]
    errors = await asyncio.to_thread(validate_section, SECTION, data, await config_core._stored_boneio())
    if errors:
        raise HTTPException(status_code=422, detail={"message": "The new device would not save", "errors": errors})

    key = getattr(request.state, "api_key", None)
    rationale = body.rationale or f"Add the discovered {body.kind} device '{entry['name']}'."
    if key is not None and key.scope is KeyScope.PROPOSE:
        made = await proposal_routes.file_proposal(SECTION, data, rationale, request)
        return {"added": entry, "proposal": made}
    result = await config_core.update_section_content(SECTION, data, request)
    if not result.get("restart_required"):
        await config_core.reload_configuration([SECTION])
    return {"added": entry, "saved": True}
