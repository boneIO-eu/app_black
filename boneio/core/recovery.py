"""Recovery mode: what boneIO does when it cannot start normally.

Before this, a config.yaml the application could not load ended the process
with exit code 1, systemd started it again three seconds later into the same
error, and the only trace of why was the first hundred characters on the OLED
and whatever the owner could dig out of the journal over SSH. The web panel,
the one tool the owner actually has, was exactly the thing that never came up.

Recovery mode starts only the panel instead: the owner's usual login, the
error, the log, the config files and the backups - and nothing else. No
outputs are driven, no bus is opened and no broker is connected, so a
controller in recovery sits in the same safe state it would with the service
stopped.

Two things send a controller there:

* **A configuration that does not load** - bad YAML, a failed validation, a
  missing include. That is deterministic, so it goes to recovery at once.
* **A crash loop** - the configuration loads, but startup dies on it all the
  same, :data:`CRASH_LOOP_THRESHOLD` times running. A single crash is not
  enough: a broker or a bus that is not ready yet is worth another try, which
  is what systemd gives it. Only a start that stays up for
  :data:`STABLE_AFTER_SECONDS` clears the count.

This module holds the part of that which does not need the web stack, so the
CLI can decide cheaply whether to go there at all.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

#: Crashes in a row, each before the application had been up for
#: :data:`STABLE_AFTER_SECONDS`, that put the controller into recovery.
CRASH_LOOP_THRESHOLD = 3

#: How long a start has to stay up before its predecessors' crashes are
#: forgiven. Long enough to cover the parts of startup that run in the
#: background after the panel is already answering - remote devices wait for
#: the first page load and can take most of a minute on a BeagleBone.
STABLE_AFTER_SECONDS = 120

#: Kept next to config.yaml, like state.json, so it survives a reboot: a crash
#: loop that a power cycle cleared would come straight back.
FAILURES_FILENAME = "startup_failures.json"

#: How much of a traceback is kept. Enough for the frames that matter; a crash
#: inside a deep library stack would otherwise grow this file without bound.
_MAX_TRACEBACK_CHARS = 8000

#: Default panel port, the same one the runner falls back to.
DEFAULT_WEB_PORT = 8090


@dataclass
class RecoveryReason:
    """Why the controller is in recovery, in a form the panel can show.

    Attributes:
        kind: ``"config"`` for a configuration that did not load, ``"crash"``
            for a crash loop.
        message: The error, as the application reported it.
        file: The file the error points at, when it points at one.
        line: 1-based line in that file.
        column: 1-based column in that line.
        details: A traceback, for a crash.
        failures: Crashes counted, for a crash loop.
        at: When it happened, as a UNIX timestamp.
    """

    kind: str
    message: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    details: str | None = None
    failures: int = 0
    at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """The reason as plain JSON-serialisable data."""
        return asdict(self)


def _find_mark(err: BaseException) -> Any | None:
    """The YAML position an error carries, looking through its causes.

    ``load_yaml_file`` wraps a parser error into a ConfigurationException and
    keeps the original as ``__cause__``; an error in an included file arrives
    the same way, one level further down.
    """
    seen: set[int] = set()
    current: BaseException | None = err
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        mark = getattr(current, "problem_mark", None)
        if mark is not None:
            return mark
        current = current.__cause__ or current.__context__
    return None


def describe_config_error(err: BaseException, config_file: str) -> RecoveryReason:
    """A :class:`RecoveryReason` for a configuration that did not load.

    Args:
        err: What loading the configuration raised.
        config_file: The config.yaml the application was started with, used
            when the error names no file of its own.

    Returns:
        The reason, with the file and position when the parser reported one.
    """
    reason = RecoveryReason(kind="config", message=str(err) or type(err).__name__)
    mark = _find_mark(err)
    if mark is not None:
        name = getattr(mark, "name", None)
        # PyYAML names a string stream "<unicode string>"; that is no file.
        reason.file = name if name and not str(name).startswith("<") else config_file
        reason.line = getattr(mark, "line", -1) + 1 or None
        reason.column = getattr(mark, "column", -1) + 1 or None
    else:
        reason.file = config_file
    return reason


def describe_crash(err: BaseException) -> RecoveryReason:
    """A :class:`RecoveryReason` for a crash, traceback included.

    Args:
        err: The exception startup died of.

    Returns:
        The reason; ``failures`` is filled in by :class:`StartupFailures`.
    """
    details = "".join(traceback.format_exception(err))
    return RecoveryReason(
        kind="crash",
        message=f"{type(err).__name__}: {err}",
        details=details[-_MAX_TRACEBACK_CHARS:],
    )


class StartupFailures:
    """Counts starts that crashed, persistently, to spot a crash loop.

    Every method swallows its own I/O errors: this exists to help a controller
    that is already failing, and a read-only or full disk must not become one
    more reason for it to fail.

    Args:
        config_file: The config.yaml; the counter lives beside it.
    """

    def __init__(self, config_file: str) -> None:
        self._path = Path(config_file).resolve().parent / FAILURES_FILENAME

    @property
    def path(self) -> Path:
        """Where the counter is kept."""
        return self._path

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as err:
            _LOGGER.warning("Ignoring unreadable %s: %s", self._path, err)
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        try:
            fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".startup_failures.")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self._path)
        except OSError as err:
            _LOGGER.warning("Could not record startup failures in %s: %s", self._path, err)

    @property
    def count(self) -> int:
        """Crashes in a row since the last stable start."""
        count = self._read().get("count", 0)
        return count if isinstance(count, int) and count > 0 else 0

    def in_crash_loop(self) -> bool:
        """True when the next start should go to recovery instead."""
        return self.count >= CRASH_LOOP_THRESHOLD

    def record(self, err: BaseException) -> int:
        """Count one more crash.

        Args:
            err: What the application died of.

        Returns:
            The new count.
        """
        reason = describe_crash(err)
        reason.failures = self.count + 1
        self._write({"count": reason.failures, "last": reason.to_dict()})
        return reason.failures

    def last_reason(self) -> RecoveryReason:
        """The last crash recorded, as a reason to show in the panel."""
        data = self._read()
        last = data.get("last")
        try:
            reason = RecoveryReason(**last) if isinstance(last, dict) else None
        except TypeError:
            reason = None
        if reason is None:
            reason = RecoveryReason(kind="crash", message="boneIO kept crashing during startup.")
        reason.failures = self.count
        return reason

    def allow_one_retry(self) -> None:
        """Let the next start run normally, but only that one.

        Called when the owner leaves recovery, and when recovery cannot run
        at all (no ``web`` section, no account to sign in with): without a
        panel, another normal start is the only way out of the loop.
        Clearing the count outright would cost three more crashes - most of
        a minute each on a BeagleBone - before the panel came back if the fix
        did not work; one below the threshold gives the fix a single try.
        """
        data = self._read()
        if self.count >= CRASH_LOOP_THRESHOLD:
            data["count"] = CRASH_LOOP_THRESHOLD - 1
            self._write(data)

    def clear(self) -> None:
        """Forget every crash: this start has proven itself."""
        try:
            self._path.unlink(missing_ok=True)
        except OSError as err:
            _LOGGER.warning("Could not clear %s: %s", self._path, err)


@dataclass
class WebSettings:
    """The parts of the ``web`` section recovery needs to listen at all.

    Attributes:
        enabled: Whether config.yaml has a ``web`` section. A controller whose
            owner removed the panel does not get it back through recovery.
        port: The panel port.
        expose: ``"all"`` or ``"proxy"``, see :class:`boneio.webui.bind.Exposure`.
        proxy_port: ``web.proxy_port``, the port Caddy serves the panel on.
        security: The ``web.security`` block, for the CSP.
    """

    enabled: bool = True
    port: int = DEFAULT_WEB_PORT
    expose: str = "all"
    proxy_port: int | None = None
    security: dict[str, Any] = field(default_factory=dict)

    def panel_url(self, address: str | None) -> str | None:
        """The link to show for this panel, by the rule the regular OLED uses.

        Mirrors ``ConfigHelper.configuration_url`` without the cloud name:
        that one needs the registration running, and it is too long for the
        display anyway. Through the proxy when a proxy port is configured or
        the panel's own port is off the network; the panel's port otherwise.

        Args:
            address: The controller's IP, or None when it has none yet.

        Returns:
            The URL, or None without an address.
        """
        if not address or address == "none":
            return None
        if self.proxy_port:
            return f"https://{address}:{self.proxy_port}"
        if self.expose == "proxy":
            from boneio.const import DEFAULT_PROXY_PORT

            return f"https://{address}:{DEFAULT_PROXY_PORT}"
        return f"http://{address}:{self.port}"


def _web_from_mapping(config: Any) -> WebSettings | None:
    if not isinstance(config, dict):
        return None
    if "web" not in config:
        return WebSettings(enabled=False)
    web = config.get("web") or {}
    if not isinstance(web, dict):
        return WebSettings()
    settings = WebSettings()
    with contextlib.suppress(TypeError, ValueError):
        settings.port = int(web.get("port", DEFAULT_WEB_PORT))
    if str(web.get("expose", "all")) == "proxy":
        settings.expose = "proxy"
    with contextlib.suppress(TypeError, ValueError):
        if web.get("proxy_port"):
            settings.proxy_port = int(web["proxy_port"])
    if isinstance(web.get("security"), dict):
        settings.security = web["security"]
    return settings


_TOP_LEVEL_KEY = re.compile(r"^([A-Za-z_][\w-]*)\s*:")
_WEB_PORT = re.compile(r"^\s+port\s*:\s*[\"']?(\d+)")
_WEB_PROXY_PORT = re.compile(r"^\s+proxy_port\s*:\s*[\"']?(\d+)")
_WEB_EXPOSE = re.compile(r"^\s+expose\s*:\s*[\"']?(\w+)")


def _web_from_text(text: str) -> WebSettings:
    """Best-effort read of the ``web`` block from YAML that does not parse.

    The point is not to open the panel wider than its owner asked for: a
    controller set to ``expose: proxy`` stays off the LAN in recovery too,
    even when the file around that line is broken.
    """
    settings = WebSettings(enabled=False)
    in_web = False
    for line in text.splitlines():
        top = _TOP_LEVEL_KEY.match(line)
        if top:
            in_web = top.group(1) == "web"
            settings.enabled = settings.enabled or in_web
            continue
        if not in_web:
            continue
        if m := _WEB_PORT.match(line):
            settings.port = int(m.group(1))
        elif m := _WEB_PROXY_PORT.match(line):
            settings.proxy_port = int(m.group(1))
        elif (m := _WEB_EXPOSE.match(line)) and m.group(1) == "proxy":
            settings.expose = "proxy"
    return settings


def read_web_settings(config_file: str) -> WebSettings:
    """How the panel should listen, read from a config that may be broken.

    Tries a real load first, which follows ``!include`` and ``!secret``, and
    falls back to reading the text of config.yaml when that fails. A file that
    cannot be read at all yields the defaults: the panel on its usual port,
    since that is what nearly every controller runs.

    Args:
        config_file: Path to config.yaml.

    Returns:
        The settings to listen with.
    """
    from boneio.core.config.yaml_util import load_yaml_file

    try:
        settings = _web_from_mapping(load_yaml_file(config_file))
        if settings is not None:
            return settings
    except Exception as err:  # noqa: BLE001 - any failure falls back to the text
        _LOGGER.debug("Reading web settings from the text of %s: %s", config_file, err)

    try:
        text = Path(config_file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return WebSettings()
    if not text.strip():
        return WebSettings()
    return _web_from_text(text)
