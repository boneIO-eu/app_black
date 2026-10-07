"""Security posture endpoint.

Admin only, and deliberately so: a list of what is still unlocked on this
controller is a shopping list for anyone who should not have it. The policy
module enforces that; this route does not repeat the check.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import socket
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from boneio.core.config.write_lock import CONFIG_WRITE_LOCK
from boneio.core.config.yaml_patch import (
    YamlPatchError,
    has_section,
    remove_section,
    set_block_list,
)
from boneio.core.config.yaml_util import load_yaml_file
from boneio.core import containers, system_ops
from boneio.core.security import certificate as certs, framing
from boneio.core.security.certificate import device_addresses
from boneio.core.system.monitor import get_network_info
from boneio.core.security.posture import Posture, evaluate
from boneio.webui.bind import DEFAULT_PROXY_PORT, proxy_is_serving_cached
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


#: Parsed config.yaml, keyed by what the file looked like when it was read:
#: ``(mtime, size, read_at, data)``.
_config_cache: tuple[float, int, float, dict] | None = None

#: Ceiling on how stale a cached parse may be, in seconds.
#:
#: The mtime check already catches an edit to config.yaml itself. This bounds
#: the one case it cannot see: a value the posture reads living in a file
#: pulled in by ``!include`` or ``!secret``, which can change while
#: config.yaml does not. Short enough that nobody notices, long enough to
#: collapse the burst of requests one page load makes.
_CONFIG_CACHE_TTL = 5.0


def _load_config() -> dict:
    """Read config.yaml, reusing the last parse when the file has not changed.

    Loaded through the normal loader so ``!secret`` is resolved: a shipped
    default moved into secrets.yaml is still a shipped default.

    The parse is the expensive part — measured at ~230 ms on a BeagleBone, and
    it is pure Python, so it costs that again on every caller. Three components
    ask for the posture when the security page opens, and each used to pay it.

    Returns:
        The parsed configuration, or an empty dict when it cannot be read.
    """
    global _config_cache

    path = _app_state.yaml_config_file
    try:
        stat = os.stat(path)
        signature = (stat.st_mtime, stat.st_size)
    except OSError:
        signature = None

    if _config_cache is not None and signature is not None:
        mtime, size, read_at, data = _config_cache
        fresh = time.monotonic() - read_at < _CONFIG_CACHE_TTL
        if fresh and (mtime, size) == signature:
            return data

    try:
        loaded = load_yaml_file(path)
        config = loaded if isinstance(loaded, dict) else {}
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not read configuration for the security check: %s", err)
        return {}

    if signature is not None:
        _config_cache = (signature[0], signature[1], time.monotonic(), config)
    return config


def _invalidate_config_cache() -> None:
    """Forget the cached parse.

    Called after this module writes config.yaml: the filesystem timestamp has
    a resolution, and a write that lands inside the same tick as the read
    before it would otherwise look unchanged.
    """
    global _config_cache
    _config_cache = None


def _proxy_serving(config: dict) -> bool | None:
    """Whether the reverse proxy is answering for this panel.

    Only asked when the answer changes what the panel says — a device already
    behind the proxy is being served by it by definition, and probing there
    would spend an HTTPS round trip to learn nothing.

    Returns:
        True or False, or None when it was not asked.
    """
    web = config.get("web") if isinstance(config.get("web"), dict) else {}
    if web.get("expose") == "proxy":
        return None

    port = web.get("proxy_port")
    if not isinstance(port, int):
        port = DEFAULT_PROXY_PORT
    serving, _ = proxy_is_serving_cached(port)
    return serving


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
    cloud_error: str | None = None

    try:
        helper = getattr(_app_state, "config_helper", None)
        cloud_reg = getattr(helper, "_cloud_reg", None) if helper else None
        if cloud_reg is not None:
            cloud_active = bool(cloud_reg.is_cloud_config_active())
            # Why it is not working, so the check can say it instead of
            # telling somebody to switch on what is already on.
            cloud_error = cloud_reg.last_error or None
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not read cloud state for the security check: %s", err)

    service_password, os_update = _system_states()

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
        proxy_serving=_proxy_serving(config),
        custom_certificate=certs.installed() is not None,
        cloud_error=cloud_error,
        service_password=service_password,
        os_update=os_update,
    )


class _Refreshing:
    """A slow system read, kept warm.

    Each of these is a sudo call into boneio-system: 1.8 s for the OS update
    state and 2.3 s for the SSH login state on a BeagleBone, the latter mostly
    a deliberately slow yescrypt check against the shipped password. Asked on
    every page load that is the whole wait.

    So within ``ttl`` the last answer is simply returned. Past it, the last
    answer is still returned and a refresh starts in the background, one at a
    time, so a page open never waits on a value it already had. Only the very
    first read waits, and :func:`warm_system_state` does that one at startup.
    """

    def __init__(self, name: str, read: Callable[[], object], ttl: float) -> None:
        self._name = name
        self._read = read
        self._ttl = ttl
        self._lock = threading.Lock()
        self._value: object = None
        self._at: float | None = None
        self._refreshing = False

    def get(self) -> object:
        with self._lock:
            at, value = self._at, self._value
        if at is None:
            return self._refresh()
        if time.monotonic() - at >= self._ttl:
            self.refresh_in_background()
        return value

    def refresh_in_background(self) -> None:
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True
        threading.Thread(target=self._refresh, name=f"refresh-{self._name}", daemon=True).start()

    def forget(self) -> None:
        """Drop the answer, so the next read asks again and waits for it."""
        with self._lock:
            self._at = None
            self._value = None

    @property
    def known(self) -> bool:
        with self._lock:
            return self._at is not None

    def _refresh(self) -> object:
        try:
            value = self._read()
        except Exception as err:  # noqa: BLE001 — the posture must never raise
            _LOGGER.warning("Could not read %s: %s", self._name, err)
            value = None
        with self._lock:
            self._value = value
            self._at = time.monotonic()
            self._refreshing = False
        return value


def _read_os_update_state() -> dict | None:
    """boneio-system's update report, or None on a helper that predates it."""
    if not system_ops.helper_supports("os-update-state"):
        return None
    result = system_ops.os_update_state()
    return result.json() if result.ok else None


#: A minute: someone who has just run passwd over SSH sees the check turn on
#: the refresh after next; a change made from the panel is seen at once.
_os_update = _Refreshing("the operating system update state", _read_os_update_state, 60.0)
_service_password = _Refreshing(
    "the SSH login state", lambda: system_ops.service_password_state(), 60.0
)


def _os_update_state() -> dict | None:
    """The OS update report, from the warm cache."""
    return _os_update.get()  # type: ignore[return-value]


def service_password_state() -> str | None:
    """How the boneio SSH login stands, from the warm cache.

    Shared by the posture and the SSH login card in Accounts, which used to
    ask the helper for it on every open.
    """
    return _service_password.get()  # type: ignore[return-value]


def forget_service_password_state() -> None:
    """Drop the cached SSH login state, after the panel has just changed it."""
    _service_password.forget()


def _system_states() -> tuple[str | None, dict | None]:
    """Both slow reads, side by side when both have to be waited for."""
    if _service_password.known or _os_update.known:
        return service_password_state(), _os_update_state()
    with ThreadPoolExecutor(max_workers=2) as pool:
        ssh = pool.submit(service_password_state)
        os_update = pool.submit(_os_update_state)
        return ssh.result(), os_update.result()


#: How long after the server starts the caches are filled. Both reads are sudo
#: calls, one a deliberately slow yescrypt, and on a single core they held the
#: first page back by over ten seconds when started together with the server.
WARM_DELAY_SECONDS = 30.0


def warm_system_state(delay: float = WARM_DELAY_SECONDS) -> None:
    """Fill both caches in the background, so the first page open does not wait.

    Only on a controller: where the helper is not installed (a development
    machine, the tests) there is nothing to ask.

    Args:
        delay: Seconds to leave the server alone first. A page that asks
            sooner just reads the value itself, as it would without a cache.
    """
    if not os.path.exists(system_ops.HELPER_PATH):
        return

    def warm() -> None:
        _service_password.refresh_in_background()
        _os_update.refresh_in_background()

    timer = threading.Timer(delay, warm)
    timer.daemon = True
    timer.start()


@router.get("/posture")
def get_posture():
    """Report every security check and a summary of the failures.

    Deliberately a plain ``def``. ``current_posture`` reads and parses
    config.yaml, and an ``async def`` would do that on the event loop, where
    it stalls every other request — including the WebSocket that carries
    relay state — for its whole duration. Starlette runs a ``def`` endpoint
    in its threadpool instead.

    This does not make concurrent postures faster: the work is parsing, which
    is CPU-bound Python, so the GIL serialises it either way. Measured on a
    BeagleBone, four overlapping requests took the same ~1.2 s before and
    after. What it does change is who waits — in the same batch /api/config
    came back 330 ms sooner, because it no longer sat behind the posture
    rather than beside it. The parse cost itself is addressed by the cache in
    :func:`_load_config`.

    Safe to run off the loop: this only reads — config.yaml, the user store
    and the cloud flag — and writes nothing.

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
def get_frame_ancestors():
    """Report which sites may embed this panel.

    A plain ``def`` for the same reason as :func:`get_posture` — it parses
    config.yaml, and the security page asks for both at once.

    Note that the PUT below stays ``async def`` on purpose: it *writes*
    config.yaml, and being pinned to the event loop is what keeps it from
    overlapping with a read that would then see a half-written file.

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
        # A thread: this waits for any other config save to finish first.
        await asyncio.to_thread(
            set_block_list, config_file, ("web", "security"), "frame_ancestors", tokens
        )
    except YamlPatchError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except OSError as err:
        raise HTTPException(status_code=500, detail=str(err)) from err

    _invalidate_config_cache()

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


# ------------------------------------------------- the pre-1.6 login block


def _remove_legacy_auth_block(path: Path) -> Path | None:
    """Check, copy and edit config.yaml as one step, under the config lock.

    A save landing between the copy and the edit would be missing from the
    copy, and one landing between the check and the edit could be undone.

    Returns:
        Where the copy went, or None if there was no block to remove.

    Raises:
        HTTPException: If the file cannot be read, copied or edited.
    """
    with CONFIG_WRITE_LOCK:
        # Asked before anything is written. A second call used to copy the
        # already-cleaned file over the backup made by the first — destroying the
        # only remaining copy of the block — and then delete it as unneeded.
        try:
            if not has_section(path, ("web", "auth")):
                return None
        except OSError as err:
            raise HTTPException(
                status_code=500, detail=f"Could not read the configuration: {err}"
            ) from err

        backup = path.with_name(f"{path.name}.pre-1.6-auth.bak")
        try:
            shutil.copy2(path, backup)
        except OSError as err:
            # Without the copy this is an irreversible edit to a file we do not
            # own, so the edit does not happen.
            raise HTTPException(
                status_code=500, detail=f"Could not write a copy first: {err}"
            ) from err

        try:
            removed = remove_section(path, ("web", "auth"))
        except YamlPatchError as err:
            raise HTTPException(status_code=409, detail=str(err)) from err
        except OSError as err:
            raise HTTPException(status_code=500, detail=str(err)) from err

        if not removed:  # pragma: no cover - has_section already answered this
            return None
        return backup


@router.delete("/legacy-auth")
async def remove_legacy_auth():
    """Take the pre-1.6 ``web.auth`` block out of config.yaml.

    Startup copies that account into the hashed store and deliberately leaves
    the file alone — rewriting somebody's configuration during an upgrade is
    not a surprise to spring on a controller in a cabinet. The consequence is
    a password sitting in plain text in a block nothing reads, in the file and
    in every backup taken since, until somebody removes it on purpose. This is
    that purpose, asked for by an administrator who can see what it will do.

    A copy of the file is written first, next to it. The block can carry
    comments and the removal takes the ones directly above it, so an owner who
    wanted them has somewhere to look.

    Returns:
        What happened, and where the copy went.

    Raises:
        HTTPException: If no configuration is loaded, or the file cannot be
            read or written.
    """
    config_file = getattr(_app_state, "yaml_config_file", None)
    if not config_file:
        raise HTTPException(status_code=503, detail="No configuration file is loaded.")

    path = Path(config_file)
    # A thread: this waits for any other config save to finish first.
    backup = await asyncio.to_thread(_remove_legacy_auth_block, path)
    if backup is None:
        return {"removed": False, "backup": None}

    _invalidate_config_cache()
    _LOGGER.warning(
        "Removed the pre-1.6 web.auth block from %s on an administrator's "
        "request. A copy of the previous file is at %s. If that password is "
        "used anywhere else, it should be changed there.",
        path,
        backup,
    )
    return {"removed": True, "backup": str(backup)}


# --------------------------------------------------------- the TLS certificate


def _reached_by() -> list[str]:
    """The names this device is likely to be opened by in a browser.

    Returns:
        Its hostname, its mDNS name and its address on the local network.
    """
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


@router.get("/certificate")
def get_certificate():
    """Describe the TLS certificate this device serves.

    Deliberately a plain ``def``: it reads and parses files.

    Returns:
        The custom certificate's details, or that there is none.
    """
    info = certs.installed()
    config = _load_config()
    web = config.get("web") if isinstance(config.get("web"), dict) else {}

    return {
        "custom": info is not None,
        "certificate": info.to_dict() if info else None,
        "reached_by": _reached_by(),
        "preferred_url": _preferred_url(web),
        # What Home Assistant was actually given, asked rather than described.
        "home_assistant_url": _home_assistant_url(),
        # Answers "is this device still answering in the clear on the LAN"
        # where somebody is already looking at how it is served, rather than
        # only as a finding that disappears once it is dealt with.
        "exposed_on_lan": web.get("expose") != "proxy",
        "root_ca_available": certs.root_ca() is not None,
    }


def _home_assistant_url() -> str:
    """The address Home Assistant shows for this device.

    Read from the live ConfigHelper rather than worked out here: cloud
    registration, a configured proxy port and the exposure setting each change
    it, and a second implementation of those rules is a second thing to be
    wrong.

    Returns:
        The URL, or an empty string when there is none to give.
    """
    helper = getattr(_app_state, "config_helper", None)
    if helper is None:
        return ""
    try:
        return helper.configuration_url or ""
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Could not read the configuration URL: %s", err)
        return ""


def _preferred_url(web: dict) -> str:
    """The address worth handing to a person, which is a name.

    An address is what everyone reaches a new controller by and the worst thing
    to write down: the next DHCP lease invalidates it, and a certificate naming
    it goes stale with it. The hostname does not move, mDNS resolves it on the
    local network, and the proxy issues a certificate matching it by itself.

    Args:
        web: The parsed ``web`` section.

    Returns:
        An https URL, or an empty string when the hostname is unknown.
    """
    try:
        hostname = socket.gethostname()
    except OSError:  # pragma: no cover - a host with no name
        return ""
    if not hostname:
        return ""

    # The same answer Home Assistant is given, for the same reason: this is
    # the one address that keeps working whichever way the panel is served.
    port = web.get("proxy_port")
    if not isinstance(port, int):
        port = DEFAULT_PROXY_PORT
    return f"https://{hostname}.local:{port}"


@router.post("/certificate")
async def upload_certificate(
    certificate: UploadFile = File(...),
    key: UploadFile = File(...),
):
    """Install a certificate and key for the proxy to serve.

    For an operator who does not want cloud registration: a company CA, or a
    Let's Encrypt certificate obtained on a machine that can actually answer
    the challenge. The device never talks to an ACME server itself — doing so
    from behind a router would mean making it reachable from the internet,
    which is a far larger hole than the browser warning it would close.

    Args:
        certificate: The certificate, or preferably the full chain, as PEM.
        key: Its unencrypted private key, as PEM.

    Returns:
        What was installed, including any address it does not cover.

    Raises:
        HTTPException: If the material is unusable.
    """
    cert_pem = await certificate.read()
    key_pem = await key.read()

    try:
        info = certs.inspect(cert_pem, key_pem, reached_by=_reached_by())
    except certs.CertificateError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err

    try:
        certs.install(cert_pem, key_pem)
    except certs.CertificateError as err:
        raise HTTPException(status_code=500, detail=str(err)) from err

    restarted = await _restart_proxy()
    return {"certificate": info.to_dict(), "proxy_restarted": restarted}


@router.delete("/certificate")
async def delete_certificate():
    """Remove the custom certificate, returning the proxy to its own.

    Returns:
        Whether anything was removed.

    Raises:
        HTTPException: If the files cannot be removed.
    """
    try:
        removed = certs.remove()
    except certs.CertificateError as err:
        raise HTTPException(status_code=500, detail=str(err)) from err

    restarted = await _restart_proxy() if removed else False
    return {"removed": removed, "proxy_restarted": restarted}


async def _restart_proxy() -> bool:
    """Restart Caddy so it reads the certificate that is there now.

    The configuration is written by the container's start script (or, for the
    packaged Caddy, by the generator on its start), so a reload would re-read a
    file that has not changed. Only a restart regenerates it; the helper's verb
    does that in both modes.

    Returns:
        True when the restart succeeded.
    """
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, containers.restart_caddy)
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Could not restart the proxy: %s", err)
        return False
    if not result.ok:
        # The files are already in place, so the next restart picks them up.
        # Failing the request would suggest the upload did not happen.
        _LOGGER.error("The proxy did not restart: %s", result.stderr.strip())
    return result.ok


@router.get("/root-ca")
def download_root_ca():
    """Serve this device's own certificate authority.

    The cheapest route to a panel browsers accept: no domain, no DNS
    credentials, nothing reachable from outside. Install it once on the
    machines that open this panel.

    It is offered with the cost stated rather than as the obvious thing to do.
    A machine that trusts this authority will believe it about any name, not
    only this device's, and Caddy's internal CA sets no name constraints.

    Returns:
        The root certificate as a file download.

    Raises:
        HTTPException: If the proxy has not created one yet.
    """
    body = certs.root_ca()
    if body is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "This device has no certificate authority of its own yet. It "
                "is created the first time the proxy starts."
            ),
        )

    return Response(
        content=body,
        media_type="application/x-pem-file",
        headers={"Content-Disposition": 'attachment; filename="boneio-root-ca.crt"'},
    )
