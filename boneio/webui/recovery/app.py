"""The recovery panel's HTTP application.

Deliberately not the regular app with pieces switched off. That one is built
around a running Manager - nearly every route reaches into it - and importing
it pulls in every router, every integration and the hardware layer. A
controller is in recovery precisely because some of that did not work, so the
panel that is meant to fix it depends on as little of it as possible.

What it does share with the regular app is everything that decides who gets
in: the account store, the token secret and format, the auth middleware with
its role policy, the CSRF check, the login rate limiter and the security
headers. Every ``/api/recovery`` route needs an admin (see
:mod:`boneio.webui.middleware.policy`), because between them they hand out
the configuration and the log.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from boneio.core.atomic_file import write_atomically
from boneio.core.auth.store import UserStore
from boneio.core.recovery import RecoveryReason, describe_config_error
from boneio.version import __version__
from boneio.webui.middleware.auth import (
    AuthMiddleware,
    create_token,
    set_allow_anonymous,
    set_jwt_secret,
    set_user_store,
)
from boneio.webui.middleware.csrf import CSRFMiddleware
from boneio.webui.rate_limit import ip_key, login_rate_limiter, user_key
from boneio.webui.security_headers import apply_security_headers

_LOGGER = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

#: Files the editor never opens, whatever their extension. The same list the
#: regular raw editor keeps out of reach.
PROTECTED_FILENAMES = frozenset({"secrets.yaml", "jwt_secret", "users.json", ".env"})

#: Directories under the config dir that hold no configuration of their own.
_SKIPPED_DIRS = frozenset({"backups", "__pycache__", "node_modules"})

#: The editor is for configuration, not for whatever else sits in the folder.
_EDITABLE_SUFFIXES = (".yaml", ".yml")

#: Enough for any real config.yaml; a limit so one request cannot fill the disk.
_MAX_FILE_BYTES = 2 * 1024 * 1024

_LISTING_LIMIT = 200

_BACKUP_GLOB = "config_backup_*.tar.gz"


class RecoveryState:
    """What the recovery routes share.

    Args:
        config_file: The config.yaml boneIO was started with.
        reason: Why the controller is in recovery.
        on_restart: Called to leave recovery.
        can_restart: Whether leaving recovery will bring the controller back
            by itself, i.e. whether something restarts the process.
    """

    def __init__(
        self,
        config_file: str,
        reason: RecoveryReason,
        on_restart: Any,
        can_restart: bool,
    ) -> None:
        self.config_file = str(Path(config_file).resolve())
        self.config_dir = Path(self.config_file).parent
        self.reason = reason
        self.on_restart = on_restart
        self.can_restart = can_restart
        self.last_activity = time.monotonic()
        self.retry_at: float | None = None
        self.validation_lock = asyncio.Lock()
        self.last_validation: dict[str, Any] | None = None

    def touch(self) -> None:
        """Note that somebody is working in the panel."""
        self.last_activity = time.monotonic()


def resolve_config_path(config_dir: Path, relative: str) -> Path:
    """Resolve a client-supplied path, keeping it inside the config dir.

    Args:
        config_dir: The directory config.yaml is in.
        relative: Path relative to it, as the client sent it.

    Returns:
        The resolved path.

    Raises:
        HTTPException: 403 for a path outside the directory or a protected
            file, 400 for a file that is not YAML.
    """
    root = config_dir.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or target == root:
        _LOGGER.warning("Recovery: refused path outside the config dir: %s", relative)
        raise HTTPException(status_code=403, detail="Access denied")
    if target.name in PROTECTED_FILENAMES:
        raise HTTPException(status_code=403, detail="Protected file")
    if not target.name.endswith(_EDITABLE_SUFFIXES):
        raise HTTPException(status_code=400, detail="Only YAML files can be edited here")
    return target


def list_config_files(config_dir: Path) -> list[dict[str, Any]]:
    """The YAML files the editor offers, config.yaml first.

    Args:
        config_dir: The directory config.yaml is in.

    Returns:
        ``{"path", "size"}`` for each, paths relative to the directory.
    """
    root = config_dir.resolve()
    found: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in _SKIPPED_DIRS)
        for name in sorted(filenames):
            if not name.endswith(_EDITABLE_SUFFIXES) or name in PROTECTED_FILENAMES:
                continue
            path = Path(dirpath) / name
            try:
                size = path.stat().st_size
            except OSError:
                continue
            found.append({"path": path.relative_to(root).as_posix(), "size": size})
            if len(found) >= _LISTING_LIMIT:
                return found
    found.sort(key=lambda f: (f["path"] != "config.yaml", "/" in f["path"], f["path"]))
    return found


def _collect_log_secrets(config_file: str) -> set[str]:
    """Secret values to take out of the log before it leaves the device.

    The regular panel reads them from the loaded configuration, which recovery
    does not have. secrets.yaml is read directly instead - every value in it
    is a secret by definition - and then whatever of the configuration still
    loads.
    """
    import yaml

    from boneio.core.config.secret_masking import collect_secrets

    found: set[str] = set()
    config_dir = Path(config_file).parent
    for secrets_file in config_dir.rglob("secrets.yaml"):
        try:
            data = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - best effort
            continue
        if isinstance(data, dict):
            found.update(str(v) for v in data.values() if isinstance(v, str | int) and str(v))
    from boneio.core.config.yaml_util import load_yaml_file

    # File by file rather than config.yaml alone: that one is broken, which is
    # why we are here, and the broker password usually sits in mqtt.yaml in
    # plain text - the file that still loads.
    for entry in list_config_files(config_dir):
        try:
            found |= collect_secrets(load_yaml_file(str(config_dir / entry["path"])))
        except Exception:  # noqa: BLE001 - best effort, per file
            continue
    return found


def _list_backups(config_dir: Path) -> list[dict[str, Any]]:
    backup_dir = config_dir / "backups"
    if not backup_dir.is_dir():
        return []
    backups = []
    for backup_file in sorted(backup_dir.glob(_BACKUP_GLOB), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            stat = backup_file.stat()
        except OSError:
            continue
        backups.append(
            {
                "filename": backup_file.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    return backups


def _snapshot_config(config_dir: Path) -> Path:
    """Archive the YAML as it is now, before a restore overwrites it.

    Named like every other backup, so the regular panel lists it and a restore
    that made things worse is itself one click from undone.
    """
    backup_dir = config_dir / "backups"
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot = backup_dir / f"config_backup_v{__version__}_{timestamp}.tar.gz"
    with tarfile.open(snapshot, mode="w:gz") as tar:
        for entry in list_config_files(config_dir):
            tar.add(str(config_dir / entry["path"]), arcname=entry["path"])
        for secrets_file in config_dir.rglob("secrets.yaml"):
            rel = secrets_file.relative_to(config_dir)
            if rel.parts[0] not in _SKIPPED_DIRS:
                tar.add(str(secrets_file), arcname=rel.as_posix())
    return snapshot


def _restore_backup(config_dir: Path, backup_file: Path) -> list[str]:
    """Write a backup's YAML files back into the config dir.

    Only regular YAML files, and only to paths that stay inside the
    directory: the archive is a file anyone with an admin login could have
    uploaded through the regular panel.
    """
    root = config_dir.resolve()
    restored: list[str] = []
    with tarfile.open(backup_file, mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.endswith(_EDITABLE_SUFFIXES):
                continue
            target = (root / member.name).resolve()
            if not target.is_relative_to(root) or target.name in {"users.json", "jwt_secret"}:
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source:
                data = source.read()
            if target.exists():
                write_atomically(target, data)
            else:
                target.write_bytes(data)
            restored.append(member.name)
    return restored


def build_app(
    state: RecoveryState,
    jwt_secret: str,
    user_store: UserStore,
    security: dict[str, Any] | None = None,
) -> FastAPI:
    """Build the recovery panel.

    Args:
        state: Shared recovery state.
        jwt_secret: Token secret, the same the regular panel signs with.
        user_store: The loaded account store.
        security: ``web.security`` from config.yaml, when it could be read.

    Returns:
        The ASGI application.
    """
    app = FastAPI(
        title="boneIO recovery",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.recovery = state

    set_jwt_secret(jwt_secret)
    set_user_store(user_store)
    # Never anonymous here, whatever config.yaml says: that setting lives in
    # the file we cannot trust, and recovery hands out the whole config.
    set_allow_anonymous(False)

    @app.post("/api/login")
    async def login(request: Request, username: str = Body(...), password: str = Body(...)):
        """Sign in against users.json, exactly as the regular panel does."""
        client = request.client.host if request.client else "unknown"
        keys = (ip_key(client), user_key(username))
        if not login_rate_limiter.check_all(*keys):
            retry_after = login_rate_limiter.retry_after(*keys)
            raise HTTPException(
                status_code=429,
                detail="Too many sign-in attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        user = await asyncio.to_thread(user_store.verify_credentials, username, password)
        if user is None:
            login_rate_limiter.record_failures(*keys)
            _LOGGER.warning("Recovery: failed login attempt for user: %s", username)
            raise HTTPException(status_code=401, detail="Invalid credentials")
        login_rate_limiter.reset(*keys)
        state.touch()
        token = create_token({"sub": user.username, "role": str(user.role)})
        return {"token": token, "role": str(user.role), "username": user.username}

    @app.get("/api/auth/required")
    async def auth_required():
        """Always: recovery never runs on a device without an account."""
        return {"required": True, "recovery": True}

    @app.get("/api/recovery/status")
    async def status():
        """Why the controller is here, and what leaving would do."""
        state.touch()
        retry_in = None
        if state.retry_at is not None:
            retry_in = max(0, round(state.retry_at - time.monotonic()))
        return {
            "version": __version__,
            "reason": state.reason.to_dict(),
            "config_dir": str(state.config_dir),
            "can_restart": state.can_restart,
            "retry_in": retry_in,
            "last_validation": state.last_validation,
        }

    @app.get("/api/recovery/files")
    async def files():
        """The YAML files that can be opened."""
        state.touch()
        return {"files": await asyncio.to_thread(list_config_files, state.config_dir)}

    @app.get("/api/recovery/file")
    async def read_file(path: str):
        """One file's content."""
        state.touch()
        target = resolve_config_path(state.config_dir, path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return {"path": path, "content": target.read_text(encoding="utf-8", errors="replace")}

    @app.put("/api/recovery/file")
    async def write_file(path: str = Body(...), content: str = Body(...)):
        """Save one file. Existing files only: this fixes a config, it does not grow one."""
        state.touch()
        target = resolve_config_path(state.config_dir, path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        if len(content.encode("utf-8")) > _MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail="File too large")
        await asyncio.to_thread(write_atomically, target, content)
        state.last_validation = None
        _LOGGER.info("Recovery: saved %s", path)
        return {"status": "success"}

    @app.post("/api/recovery/validate")
    async def validate():
        """Load the configuration the way startup does, and say what happened.

        Slow on a BeagleBone - the full validation is 20-30 s - so one at a
        time. A config that passes leaves a warm cache behind, which is what
        makes the restart that follows quick.
        """
        state.touch()
        if state.validation_lock.locked():
            raise HTTPException(status_code=409, detail="A validation is already running")
        async with state.validation_lock:
            from boneio.core.config.yaml_util import load_config_from_file

            started = time.monotonic()
            try:
                config = await asyncio.to_thread(load_config_from_file, config_file=state.config_file)
            except Exception as err:  # noqa: BLE001 - reporting it is the point
                result: dict[str, Any] = {
                    "valid": False,
                    "error": describe_config_error(err, state.config_file).to_dict(),
                }
            else:
                if config:
                    result = {"valid": True}
                else:
                    result = {
                        "valid": False,
                        "error": RecoveryReason(
                            kind="config", message="Config file is empty or missing", file=state.config_file
                        ).to_dict(),
                    }
            result["seconds"] = round(time.monotonic() - started, 1)
            state.last_validation = result
            state.touch()
            return result

    @app.get("/api/recovery/logs")
    async def logs(limit: int = 300):
        """The service log, secrets taken out, including the runs that failed."""
        from boneio.core.config.secret_masking import scrub_text
        from boneio.webui.services.logs import (
            get_standalone_logs,
            get_systemd_logs,
            is_running_as_service,
        )

        state.touch()
        limit = max(1, min(limit, 2000))
        entries: list = []
        source = "standalone"
        try:
            if is_running_as_service():
                entries, _ = await get_systemd_logs(limit)
                source = "systemd"
            if not entries:
                entries, _ = await asyncio.to_thread(get_standalone_logs, limit)
                source = "standalone"
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Recovery: could not read logs: %s", err)
        secrets = await asyncio.to_thread(_collect_log_secrets, state.config_file)
        return {
            "source": source,
            "logs": [
                {
                    "timestamp": e.timestamp,
                    "level": e.level,
                    "message": scrub_text(e.message, secrets) if secrets else e.message,
                }
                for e in entries
            ],
        }

    @app.get("/api/recovery/backups")
    async def backups():
        """Backups on disk, newest first."""
        state.touch()
        return {"backups": await asyncio.to_thread(_list_backups, state.config_dir)}

    @app.post("/api/recovery/backups/restore")
    async def restore(filename: str = Body(..., embed=True)):
        """Put a backup's YAML back, after archiving what is there now."""
        state.touch()
        backup_dir = (state.config_dir / "backups").resolve()
        backup_file = (backup_dir / filename).resolve()
        if backup_file.parent != backup_dir or not backup_file.match(_BACKUP_GLOB):
            raise HTTPException(status_code=400, detail="Invalid backup")
        if not backup_file.is_file():
            raise HTTPException(status_code=404, detail="Backup not found")
        try:
            snapshot = await asyncio.to_thread(_snapshot_config, state.config_dir)
            restored = await asyncio.to_thread(_restore_backup, state.config_dir, backup_file)
        except (OSError, tarfile.TarError) as err:
            _LOGGER.error("Recovery: restoring %s failed: %s", filename, err)
            raise HTTPException(status_code=500, detail=f"Restore failed: {err}") from err
        state.last_validation = None
        _LOGGER.info("Recovery: restored %d file(s) from %s (previous config in %s)", len(restored), filename, snapshot.name)
        return {"status": "success", "restored": restored, "snapshot": snapshot.name}

    @app.post("/api/recovery/restart")
    async def restart():
        """Leave recovery and start boneIO normally."""
        _LOGGER.info("Recovery: restart requested from the panel")
        asyncio.get_running_loop().call_later(0.3, state.on_restart)
        return {"status": "success"}

    @app.get("/{filename:path}")
    async def page(filename: str):
        """The recovery page and its two assets; anything else gets the page."""
        if filename in ("recovery.js", "recovery.css"):
            return FileResponse(STATIC_DIR / filename, headers={"Cache-Control": "no-store"})
        if filename.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not available in recovery mode"})
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})

    # Same order as the regular app: auth innermost, then CSRF, then headers.
    app.add_middleware(AuthMiddleware)
    app.add_middleware(CSRFMiddleware, allowed_origins=[])

    frame_ancestors = (security or {}).get("frame_ancestors")

    @app.middleware("http")
    async def security_headers_middleware(request, call_next):
        response = await call_next(request)
        apply_security_headers(request, response, frame_ancestors, False)
        return response

    return app
