"""Certificates for MQTT over TLS.

``/client`` is boneIO's own connection to a broker: the CA it checks the broker
against and an optional client certificate. The files are stored here; the
paths go into ``mqtt.tls`` through the ordinary section save, so the panel's
form and a hand-edited ``mqtt.yaml`` mean the same thing.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from boneio.core.messaging import mqtt_tls

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
