"""Serving the recovery panel, and leaving it again."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
import time
from typing import cast

from boneio.core.auth.jwt_secret import load_or_create_jwt_secret
from boneio.core.auth.store import UserStore, UserStoreError
from boneio.core.recovery import RecoveryReason, StartupFailures, WebSettings, read_web_settings

_LOGGER = logging.getLogger(__name__)

#: A crash loop can be something that fixes itself - a broker that was down, a
#: bus that came back. A controller left in recovery drives no outputs, so it
#: goes back to trying a normal start by itself once nobody has touched the
#: panel for this long. A config error is not retried: it cannot fix itself.
CRASH_RETRY_IDLE_SECONDS = 600

_RETRY_CHECK_SECONDS = 15

#: How long a controller that cannot serve the panel waits before systemd gets
#: to try a normal start again. Exiting at once would restart every
#: RestartSec (3 s), and with no panel to wait for there is nobody to give
#: the ten minutes above to. A minute keeps a transient cause - a bus udev
#: had not handed over yet on the first boot - down to one more attempt, and
#: a persistent one to a start and a traceback in the journal per cycle
#: rather than one every few seconds. Waiting here needs no change to the
#: systemd unit.
REFUSED_RETRY_SECONDS = 60


#: How often the notice is drawn again. SH1106 keeps its image by itself; this
#: is for the address, which on DHCP can arrive after recovery has started,
#: and for anything else that drew on the screen in the meantime.
_OLED_REFRESH_SECONDS = 60


def _show_on_oled(reason: RecoveryReason, settings: WebSettings) -> None:
    """Say on the display that the controller is in recovery, and where to look."""
    try:
        from boneio.hardware.display.early_oled import draw_recovery

        url = None
        try:
            from boneio.core.system import get_network_info

            url = settings.panel_url((get_network_info() or {}).get("ip"))
        except Exception:  # noqa: BLE001 - the address is a nicety
            pass
        what = "Config error" if reason.kind == "config" else "Crash occurred"
        draw_recovery(
            title="Recovery mode",
            message=f"{what}. Check web panel for more info{':' if url else '.'}",
            url=url,
        )
    except Exception:  # noqa: BLE001 - no display is no reason to fail
        _LOGGER.debug("OLED not available for the recovery notice")


async def _keep_oled_notice(reason: RecoveryReason, settings: WebSettings) -> None:
    """Redraw the notice for as long as recovery runs.

    Nothing in recovery blanks the screen - the sleep timer belongs to the
    regular display manager, which does not run here - so this keeps it lit
    and current rather than waking it.
    """
    while True:
        await asyncio.sleep(_OLED_REFRESH_SECONDS)
        await asyncio.to_thread(_show_on_oled, reason, settings)


def _is_service() -> bool:
    return bool(os.environ.get("INVOCATION_ID"))


def _retry_later(config_file: str, reason: RecoveryReason) -> int:
    """Recovery cannot run here: say why startup failed, then try again.

    Refusing used to end the process with exit code 1 and nothing else. With
    the crash count still at the threshold, systemd's next start came
    straight back here, refused again, and so on for good: a fresh controller
    whose bus udev had not handed over in time sat in that loop behind a
    black screen until somebody deleted startup_failures.json by hand.

    So the next start is made a normal one, as leaving recovery would, and
    the reason goes to the two places anybody can see it without the panel:
    the journal and the display.

    Args:
        config_file: The config.yaml boneIO was started with.
        reason: Why it could not start.

    Returns:
        The process exit code, 1: systemd starts boneIO again (Restart=always).
    """
    service = _is_service()
    where = f" ({reason.file}:{reason.line})" if reason.file and reason.line else ""
    retry = f"trying a normal start again in {REFUSED_RETRY_SECONDS} s" if service else "run boneIO again once it is fixed"
    _LOGGER.error(
        "boneIO could not start (%s): %s%s - %s.",
        "configuration error" if reason.kind == "config" else f"crash, {reason.failures} in a row",
        reason.message,
        where,
        retry,
    )

    try:
        from boneio.hardware.display.early_oled import draw_recovery, keep_on_exit

        note = f"Retrying in {REFUSED_RETRY_SECONDS} s. " if service else ""
        draw_recovery(
            title="Config error" if reason.kind == "config" else "Start failed",
            # The retry note first: draw_recovery keeps four lines and drops
            # the rest, and a long error must not push it off the screen.
            message=f"{note}{reason.message}",
        )
        keep_on_exit()
    except Exception:  # noqa: BLE001 - no display is no reason to fail
        _LOGGER.debug("OLED not available for the startup failure notice")

    # Before the wait, so a restart by hand in the meantime gets a normal
    # start too.
    StartupFailures(config_file).allow_one_retry()
    if service:
        time.sleep(REFUSED_RETRY_SECONDS)
    return 1


async def _serve(
    config_file: str,
    reason: RecoveryReason,
    settings: WebSettings,
    store: UserStore,
    jwt_secret: str,
) -> bool:
    """Run the panel until it is asked to leave or the process is stopped.

    Returns:
        True if the owner (or the crash-loop retry) asked for a normal start,
        False if the process was stopped.
    """
    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    from boneio.webui.bind import binds_for
    from boneio.webui.recovery.app import RecoveryState, build_app

    shutdown = asyncio.Event()
    leave = {"restart": False}

    def _restart() -> None:
        leave["restart"] = True
        shutdown.set()

    state = RecoveryState(
        config_file=config_file,
        reason=reason,
        on_restart=_restart,
        can_restart=True,
    )
    app = build_app(state, jwt_secret=jwt_secret, user_store=store, security=settings.security)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, shutdown.set)

    config = Config()
    # binds_for can wait several seconds for a Docker bridge; not on the loop.
    config.bind = await asyncio.to_thread(binds_for, settings.expose, settings.port)
    config.use_reloader = False
    config.graceful_timeout = 2.0
    config.accesslog = None
    error_logger = logging.getLogger("hypercorn.error")
    error_logger.handlers = []
    error_logger.propagate = True
    config.errorlog = error_logger

    async def _retry_when_idle() -> None:
        while not shutdown.is_set():
            state.retry_at = state.last_activity + CRASH_RETRY_IDLE_SECONDS
            if time.monotonic() >= state.retry_at:
                _LOGGER.warning(
                    "Recovery: nobody has used the panel for %d s, trying a normal start again",
                    CRASH_RETRY_IDLE_SECONDS,
                )
                _restart()
                return
            await asyncio.sleep(_RETRY_CHECK_SECONDS)

    retry_task = asyncio.create_task(_retry_when_idle()) if reason.kind == "crash" else None
    oled_task = asyncio.create_task(_keep_oled_notice(reason, settings))

    _LOGGER.warning(
        "RECOVERY MODE: boneIO did not start normally (%s). Outputs are not "
        "driven. The panel is on %s - sign in to see the error and fix it.",
        reason.kind,
        ", ".join(config.bind),
    )
    try:
        await serve(cast("object", app), config, shutdown_trigger=shutdown.wait)  # type: ignore[arg-type]
    finally:
        oled_task.cancel()
        if retry_task is not None:
            retry_task.cancel()
    return leave["restart"]


def run_recovery(config_file: str, reason: RecoveryReason) -> int:
    """Serve the recovery panel instead of starting boneIO.

    Returns without serving anything when the panel would not be safe or not
    wanted: a config without a ``web`` section, or a device that has no
    account to sign in with - recovery must not become a way to reach a
    controller's config that the regular panel would not give. The next start
    is then a normal one, after :data:`REFUSED_RETRY_SECONDS`, see
    :func:`_retry_later`.

    Args:
        config_file: The config.yaml boneIO was started with.
        reason: Why it could not start.

    Returns:
        The process exit code. When the owner leaves recovery on a machine
        that is not a systemd service, the process is replaced by a fresh
        boneIO instead of returning.
    """
    settings = read_web_settings(config_file)
    if not settings.enabled:
        _LOGGER.error("Recovery mode not started: config.yaml has no web section.")
        return _retry_later(config_file, reason)

    store = UserStore.for_config_file(config_file)
    try:
        store.load()
        provisioned = store.is_provisioned()
    except UserStoreError as err:
        _LOGGER.error("Recovery mode not started: the account store is unusable: %s", err)
        return _retry_later(config_file, reason)
    if not provisioned:
        _LOGGER.error(
            "Recovery mode not started: this device has no administrator account "
            "to sign in with. Fix config.yaml over SSH, or create an account "
            "with 'boneio accounts add'."
        )
        return _retry_later(config_file, reason)

    jwt_secret = load_or_create_jwt_secret(store.path.parent)
    _show_on_oled(reason, settings)

    try:
        restart = asyncio.run(_serve(config_file, reason, settings, store, jwt_secret))
    except Exception as err:  # noqa: BLE001 - recovery failing must not hide the original error
        _LOGGER.error("Recovery panel failed: %s", err, exc_info=True)
        # Not _retry_later(): this device has an account, so the next start
        # should offer the panel again rather than drive outputs.
        return 1

    if not restart:
        return 0

    StartupFailures(config_file).allow_one_retry()
    if _is_service():
        # systemd starts us again (Restart=always); a clean exit is all it needs.
        _LOGGER.info("Leaving recovery mode; systemd will start boneIO again.")
        return 0
    _LOGGER.info("Leaving recovery mode; starting boneIO again.")
    for handler in logging.getLogger().handlers:
        with contextlib.suppress(Exception):
            handler.flush()
    os.execv(sys.executable, [sys.executable, *sys.argv])
    return 0  # pragma: no cover - execv does not return
