"""Certificates for MQTT over TLS.

``/client`` is boneIO's own connection to a broker: the CA it checks the broker
against and an optional client certificate. The files are stored here; the
paths go into ``mqtt.tls`` through the ordinary section save, so the panel's
form and a hand-edited ``mqtt.yaml`` mean the same thing.

``/broker`` is the broker installed on this controller. Its files are root's,
so everything that changes them goes through ``boneio-system``; these routes
check what they can first, so a refusal comes back as a sentence rather than
as a broker that did not start.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import socket

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

from boneio.core import system_ops
from boneio.core.messaging import broker_tls, mqtt_tls
from boneio.core.security.certificate import device_addresses

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mqtt-tls", tags=["mqtt"])

_app_state = None


def set_app_state(app_state) -> None:
    """Give the routes the application state.

    Args:
        app_state: ``app.state``, carrying the manager and the config path.
    """
    global _app_state
    _app_state = app_state


def _config_dir() -> Path:
    path = getattr(_app_state, "yaml_config_file", None)
    if not path:
        raise HTTPException(status_code=503, detail="The configuration is not loaded yet.")
    return Path(os.path.abspath(path)).parent


def _mqtt_bus():
    """The running MQTT client, or None when MQTT is off."""
    manager = getattr(_app_state, "manager", None)
    bus = getattr(manager, "_message_bus", None)
    for candidate in getattr(bus, "buses", [bus]):
        if hasattr(candidate, "reload_credentials"):
            return candidate
    return None


async def _reconnect_if_in_use() -> None:
    """Have the client pick up a replaced file it already uses.

    A no-op unless the running configuration names that file: the reload
    compares the section and the files' identity, and reconnects only when
    one of them changed.
    """
    manager = getattr(_app_state, "manager", None)
    if manager is None:
        return
    try:
        await manager.reload_config(reload_sections=["mqtt"])
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Stored the certificate but could not reconnect: %s", err)


@router.get("/client")
def get_client_tls():
    """What is stored for boneIO's own connection, and how it is going.

    Deliberately a plain ``def``: it reads and parses files.

    Returns:
        The stored CA and client certificate, and the running client's state.
    """
    bus = _mqtt_bus()
    return {
        "files": mqtt_tls.stored(_config_dir()),
        "tls_error": getattr(bus, "tls_error", None) if bus is not None else None,
        "connected": bool(getattr(bus, "state", False)) if bus is not None else False,
        # The running connection's transport, which differs from the form
        # until the page is saved.
        "tls_in_use": bool(getattr(bus, "tls_in_use", False)) if bus is not None else False,
    }


@router.post("/client/ca")
async def upload_client_ca(certificate: UploadFile = File(...)):
    """Store the CA boneIO checks the broker's certificate against.

    Args:
        certificate: One or more certificates in PEM.

    Returns:
        What was stored, with the path to put in ``mqtt.tls.ca_certs``.

    Raises:
        HTTPException: 422 if it cannot serve as a CA.
    """
    pem = await certificate.read()
    try:
        info = await asyncio.to_thread(mqtt_tls.store_ca, pem, _config_dir())
    except mqtt_tls.MqttTlsError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    await _reconnect_if_in_use()
    return {"stored": info.to_dict()}


@router.post("/client/certificate")
async def upload_client_certificate(
    certificate: UploadFile = File(...),
    key: UploadFile = File(...),
):
    """Store a client certificate and its key, for brokers that require one.

    Args:
        certificate: The certificate in PEM, optionally with its chain.
        key: Its unencrypted private key in PEM.

    Returns:
        What was stored, with the paths for ``certfile`` and ``keyfile``.

    Raises:
        HTTPException: 422 if the pair cannot be used together.
    """
    cert_pem = await certificate.read()
    key_pem = await key.read()
    try:
        info = await asyncio.to_thread(mqtt_tls.store_client, cert_pem, key_pem, _config_dir())
    except mqtt_tls.MqttTlsError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    await _reconnect_if_in_use()
    stored = info.to_dict()
    stored["key_path"] = f"{mqtt_tls.CERT_DIR_NAME}/{mqtt_tls.CLIENT_KEY_FILE}"
    return {"stored": stored}


@router.delete("/client/{kind}")
async def delete_client_file(kind: str):
    """Remove the stored CA (``ca``) or client certificate (``client``).

    The configuration is left alone: a section still pointing at the file
    then fails loudly at the next connection, which is the honest outcome.

    Args:
        kind: ``ca`` or ``client``.

    Returns:
        Whether anything was removed.

    Raises:
        HTTPException: 404 for an unknown kind, 500 if removal fails.
    """
    if kind not in ("ca", "client"):
        raise HTTPException(status_code=404, detail="Unknown certificate.")
    try:
        removed = mqtt_tls.remove(kind, _config_dir())
    except mqtt_tls.MqttTlsError as err:
        raise HTTPException(status_code=500, detail=str(err)) from err
    return {"removed": removed}


# ------------------------------------------------------------ the broker here

#: Hosts that reach the broker over loopback, where ``required`` keeps 1883.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", ""})


class BrokerModeRequest(BaseModel):
    """Which TLS mode the broker should be in."""

    mode: str


def _reached_by() -> list[str]:
    """The names and addresses clients are likely to reach this device by."""
    from boneio.core.system.monitor import get_network_info

    hostname = None
    try:
        hostname = socket.gethostname()
    except OSError:  # pragma: no cover - a host with no name
        pass
    address = None
    try:
        address = (get_network_info() or {}).get("ip")
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Could not read this device's address: %s", err)
    return device_addresses(hostname, address)


def _app_connection() -> dict:
    """How boneIO itself reaches a broker, as far as ``required`` cares.

    Returns:
        The host and port, whether that is this device's broker, and whether
        ``required`` would cut boneIO off from it: plain MQTT to one of this
        device's own addresses other than loopback.
    """
    from boneio.webui.routes.update import is_local_broker_host

    helper = getattr(_app_state, "config_helper", None)
    mqtt: dict = {}
    try:
        config = helper.get_config() if helper is not None else {}
        if isinstance(config, dict) and isinstance(config.get("mqtt"), dict):
            mqtt = config["mqtt"]
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Could not read the MQTT configuration: %s", err)
    host = str(mqtt.get("host") or "")
    local = bool(mqtt) and is_local_broker_host(host)
    loopback = host.strip().lower().strip("[]") in _LOOPBACK_HOSTS
    tls_on = mqtt_tls.tls_enabled(mqtt.get("tls"))
    return {
        "host": host,
        "port": mqtt.get("port"),
        "uses_local_broker": local,
        "tls": tls_on,
        "blocks_required": local and not loopback and not tls_on,
    }


def _helper_json(result: system_ops.Result) -> dict | None:
    return result.json() if result.ok else None


def _refused(result: system_ops.Result, fallback: str) -> HTTPException:
    """Turn a helper refusal into a 409 carrying its own sentence."""
    lines = [line for line in result.stderr.splitlines() if line.strip()]
    message = lines[-1] if lines else fallback
    # The helper logs "REFUSED: <reason>"; the reason is what people need.
    if "REFUSED:" in message:
        message = message.split("REFUSED:", 1)[1].strip()
    return HTTPException(status_code=409, detail=message)


def _require_helper() -> None:
    if not system_ops.helper_supports("mqtt-tls-mode"):
        raise HTTPException(
            status_code=409,
            detail=(
                "The system helper on this controller does not manage the "
                "broker's TLS yet. Apply the pending system migrations first."
            ),
        )


@router.get("/broker")
def get_broker_tls():
    """The broker's TLS mode, its certificate, and what a change would affect.

    Deliberately a plain ``def``: it asks the helper through sudo and parses
    files.

    Returns:
        ``supported`` is False on a controller whose helper predates this;
        the rest describes the broker and boneIO's own connection to it.
    """
    reached_by = _reached_by()
    supported = system_ops.helper_supports("mqtt-tls-mode")
    state = _helper_json(system_ops.mqtt_tls_state()) if supported else None
    info = broker_tls.installed(reached_by)
    return {
        "supported": supported,
        "mode": (state or {}).get("mode"),
        "active": (state or {}).get("active"),
        "has_certificate": bool((state or {}).get("certificate")),
        "certificate": info.to_dict() if info else None,
        "tls_port": (state or {}).get("tls_port", 8883),
        "reached_by": reached_by,
        "app": _app_connection(),
    }


async def _install(bundle: str) -> None:
    _require_helper()
    result = await asyncio.to_thread(system_ops.mqtt_tls_cert, bundle)
    if not result.ok:
        raise _refused(result, "The broker did not accept the certificate.")


@router.post("/broker/certificate")
async def upload_broker_certificate(
    certificate: UploadFile = File(...),
    key: UploadFile = File(...),
    ca: UploadFile | None = File(None),
):
    """Install the owner's certificate for the broker.

    Args:
        certificate: The broker's certificate in PEM, optionally with its chain.
        key: Its unencrypted private key.
        ca: The CA that signed it, so the panel can hand it to clients.

    Returns:
        What was installed.

    Raises:
        HTTPException: 422 for unusable material, 409 if the helper refused
            or the broker did not come back (it is then on its old files).
    """
    cert_pem = await certificate.read()
    key_pem = await key.read()
    ca_pem = await ca.read() if ca is not None else None
    try:
        bundle, info = broker_tls.prepare_upload(cert_pem, key_pem, ca_pem or None, _reached_by())
    except broker_tls.BrokerTlsError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    await _install(bundle)
    return {"certificate": info.to_dict()}


@router.post("/broker/generate")
async def generate_broker_certificate():
    """Make a certificate here, signed by a one-off CA whose key is discarded.

    Returns:
        What was installed. The CA is at the end of the chain, to download.
    """
    reached_by = _reached_by()
    bundle = await asyncio.to_thread(broker_tls.generated_bundle, reached_by)
    await _install(bundle)
    info = broker_tls.installed(reached_by)
    return {"certificate": info.to_dict() if info else None}


@router.put("/broker/mode")
async def set_broker_mode(request: BrokerModeRequest):
    """Switch the broker between plain, TLS beside plain, and TLS only.

    ``required`` is refused while boneIO itself connects to this broker in
    plain text by one of its network addresses: it would lose its own broker
    the moment the change applied.

    Raises:
        HTTPException: 422 for an unknown mode, 409 when refused.
    """
    if request.mode not in system_ops.MQTT_TLS_MODES:
        raise HTTPException(status_code=422, detail=f"Unknown mode {request.mode!r}.")
    _require_helper()
    if request.mode == "required" and _app_connection()["blocks_required"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "boneIO connects to this broker in plain text by a network "
                "address, which TLS-only mode closes. Point its MQTT host at "
                "localhost, or turn TLS on for its own connection, first."
            ),
        )
    result = await asyncio.to_thread(system_ops.mqtt_tls_mode, request.mode)
    if not result.ok:
        raise _refused(result, "The broker did not accept the change.")
    return {"mode": request.mode}


@router.delete("/broker/certificate")
async def delete_broker_certificate():
    """Remove the broker's certificate. Refused by the helper while TLS is on."""
    _require_helper()
    result = await asyncio.to_thread(system_ops.mqtt_tls_cert_remove)
    if not result.ok:
        raise _refused(result, "The certificate could not be removed.")
    return {"removed": True}


@router.get("/broker/ca")
def download_broker_ca():
    """The CA clients should trust for this broker, as a file.

    Only a chain that ends in a self-signed CA has one to give: a certificate
    from a public CA needs nothing, and one from an owner's CA without the CA
    uploaded leaves the owner holding it.

    Raises:
        HTTPException: 404 when there is none to give.
    """
    pem = broker_tls.installed_ca()
    if pem is None:
        raise HTTPException(status_code=404, detail="The broker's chain carries no CA to download.")
    return Response(
        content=pem,
        media_type="application/x-pem-file",
        headers={"Content-Disposition": 'attachment; filename="boneio-mqtt-ca.crt"'},
    )
