"""Everything a support case needs, in one file the owner can send.

Warranty diagnosis used to mean asking the owner for a shell, which for a
device in someone's home means either a vendor key on every controller or a
long email thread. Most cases do not need a shell at all — they need the
configuration, the logs around the failure, and whether the broker, the
containers and the network are where they should be.

Two things shape what is collected.

**The logs are usually worthless.** Almost nobody runs with debug on, so the
journal holds INFO and the interesting detail was never written. An always-on
debug ring buffer was the obvious fix and is the wrong one: an idle controller
publishes around twenty MQTT messages a second, each of which logs its topic
and payload at debug, so the buffer would be publish spam and the formatting
would cost CPU on hardware that has none to spare. Instead the panel opens a
short, self-closing capture window — see :mod:`boneio.webui.routes.diagnostics`
— and the bundle takes the journal from where that window began.

**The file leaves the building.** It goes to an inbox, so it carries no
credentials: ``secrets.yaml`` and ``users.json`` are never read, and every text
file is scrubbed of the secret values the configuration holds before it is
written. The README says what was removed, because a support engineer who does
not know a value was masked will waste time on it.
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import tarfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from pathlib import Path

from boneio.core.config.secret_masking import collect_secrets, scrub_text
from boneio.version import __version__

from boneio.core import containers

_LOGGER = logging.getLogger(__name__)

#: Files in the config directory that must never be collected, whatever their
#: extension. These are the credential stores themselves; scrubbing them would
#: leave a file that is entirely mask.
EXCLUDED_FILES = frozenset({"secrets.yaml", "secrets.yml", "users.json"})

#: Lines of journal to take when no capture window is open. Enough to cover a
#: restart loop, small enough to stay mailable.
DEFAULT_LOG_LINES = 5000

#: A command that hangs must not hang the download.
COMMAND_TIMEOUT = 20


@dataclass
class Section:
    """One file in the bundle.

    Args:
        path: Path inside the archive.
        body: File contents.
    """

    path: str
    body: str


def _run(command: list[str], *, timeout: int = COMMAND_TIMEOUT) -> str:
    """Run a command and return its output, never raising.

    A diagnostic bundle that fails because one tool is missing is a bundle
    nobody gets, so every failure becomes text in the file instead.

    Args:
        command: Command and arguments.
        timeout: Seconds to wait.

    Returns:
        Combined output, or a line explaining why there is none.
    """
    if shutil.which(command[0]) is None:
        return f"[{command[0]} is not installed on this system]"
    try:
        result = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"[{' '.join(command)} timed out after {timeout}s]"
    except OSError as err:
        return f"[{' '.join(command)} could not run: {err}]"

    output = (result.stdout or "") + (result.stderr or "")
    return output.strip() or f"[{' '.join(command)} produced no output]"


def _summary(
    config: dict,
    config_file: Path,
    capture_started: float | None,
    serial: str | None = None,
    real_serial: str | None = None,
) -> str:
    """The first thing a support engineer reads.

    Args:
        config: Parsed configuration.
        config_file: Path to config.yaml.
        capture_started: Epoch seconds when a debug capture began, if any.
        serial: Effective serial of the device the bundle came from.
        real_serial: Serial derived from the MAC, when an override is in use.

    Returns:
        The summary text.
    """
    web = config.get("web") if isinstance(config.get("web"), dict) else {}
    mqtt = config.get("mqtt") if isinstance(config.get("mqtt"), dict) else {}
    boneio = config.get("boneio") if isinstance(config.get("boneio"), dict) else {}

    def count(section: str) -> int:
        value = config.get(section)
        return len(value) if isinstance(value, (list, dict)) else 0

    lines = [
        "boneIO Black diagnostics",
        f"collected       {datetime.now(UTC).isoformat()}",
        f"boneIO version  {__version__}",
        f"device name     {boneio.get('name', '?')}",
        # Which unit this is. The name is whatever the owner typed and two
        # devices commonly share it; the serial is what the MQTT topics and
        # the cloud subdomain are built from, so it is the one that lets a
        # bundle be matched to a device.
        f"serial          {serial or '(unknown)'}",
        *(
            [f"  real serial   {real_serial} (overridden above)"]
            if real_serial and serial and real_serial != serial
            else []
        ),
        f"config file     {config_file}",
        "",
        f"MQTT broker     {mqtt.get('host', '(not configured)')}:{mqtt.get('port', 1883)}",
        f"MQTT user       {mqtt.get('username', '(none)')}",
        f"web port        {web.get('port', 8090)}   proxy {web.get('proxy_port', '(none)')}",
        f"cloud           {(web.get('cloud') or {}).get('enabled', False)}",
        "",
        "configured entities",
        f"  outputs       {count('output')}",
        f"  covers        {count('cover')}",
        f"  sensors       {count('sensor')}",
        f"  modbus        {count('modbus_devices')}",
        f"  remote        {count('remote_devices')}",
        f"  templates     {count('template')}",
        f"  irrigation    {count('irrigation')}",
        "",
    ]

    if capture_started:
        began = datetime.fromtimestamp(capture_started, UTC).isoformat()
        lines.append(f"DEBUG CAPTURE   logs start at {began}")
    else:
        lines.append(
            "no debug capture — logs are at whatever level the device was "
            "already running. If the cause is not visible, ask the owner to "
            "open a capture window in Settings > Security and reproduce the "
            "fault, then send a new bundle."
        )
    return "\n".join(lines)


def _readme(masked: int, capture_started: float | None) -> str:
    """What the owner is about to send, in their own terms.

    Args:
        masked: How many distinct secret values were removed.
        capture_started: Epoch seconds when a debug capture began, if any.

    Returns:
        The README text.
    """
    return "\n".join(
        [
            "boneIO Black — diagnostic bundle",
            "",
            "What is in here:",
            "  summary.txt    versions, ports, how much of the device is configured",
            "  config/        your YAML configuration",
            "  logs/          the device log",
            "  status/        MQTT, Mosquitto, Docker, system and network state",
            "",
            "What is NOT in here:",
            "  secrets.yaml and your account file are never read.",
            f"  {masked} secret value(s) from the configuration were replaced",
            "  with a placeholder everywhere they appeared, including in the logs.",
            "",
            "What it still contains: the names of your devices, your MQTT topics,",
            "your network addresses and your automation setup. Send it to someone",
            "you are asking for help, not to a public forum.",
            "",
            (
                "The log covers the debug capture window you opened."
                if capture_started
                else "The log is at the level the device was already running, which "
                "is usually INFO. If support asks for more, open a capture window "
                "in Settings > Security, reproduce the fault, and send a new bundle."
            ),
            "",
        ]
    )


def gather_secrets(config: dict, config_dir: Path) -> set[str]:
    """Every secret value that could appear in anything being collected.

    The parsed configuration is not enough. It only holds what config.yaml
    pulls in, and the directory can contain a YAML file that nothing includes —
    left from an edit, or included conditionally — whose passwords would then
    go out in clear text because no rule knew to look for them. Every file
    about to be written to the archive is mined, so the scrubbing covers
    exactly what is being sent.

    Args:
        config: Parsed configuration.
        config_dir: Directory holding config.yaml.

    Returns:
        The union of secret values found.
    """
    from boneio.core.config.yaml_util import load_yaml_file

    secrets = set(collect_secrets(config))
    for path in config_dir.glob("*.y*ml"):
        if path.name in EXCLUDED_FILES:
            continue
        try:
            loaded = load_yaml_file(str(path))
        except Exception as err:  # noqa: BLE001
            # A file that will not parse is still going into the archive, so
            # say so rather than passing over it in silence.
            _LOGGER.warning(
                "Diagnostics could not mine %s for secrets: %s", path.name, err
            )
            continue
        secrets |= collect_secrets(loaded)
    return secrets


def _config_sections(config_dir: Path, secrets: set[str]) -> list[Section]:
    """Every YAML file beside config.yaml, scrubbed.

    Args:
        config_dir: Directory holding config.yaml.
        secrets: Values to remove.

    Returns:
        One section per readable file.
    """
    sections: list[Section] = []
    for path in sorted(config_dir.glob("*.y*ml")):
        if path.name in EXCLUDED_FILES:
            sections.append(
                Section(f"config/{path.name}.omitted", "[withheld: this file is credentials]")
            )
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as err:
            text = f"[could not read: {err}]"
        sections.append(Section(f"config/{path.name}", scrub_text(text, secrets)))
    return sections


def _log_section(capture_started: float | None) -> Section:
    """The device log, from the capture window when there is one.

    Args:
        capture_started: Epoch seconds when a debug capture began, if any.

    Returns:
        The log section.
    """
    if capture_started:
        since = datetime.fromtimestamp(capture_started).strftime("%Y-%m-%d %H:%M:%S")
        command = ["journalctl", "-u", "boneio", "--since", since, "--no-pager"]
    else:
        command = ["journalctl", "-u", "boneio", "-n", str(DEFAULT_LOG_LINES), "--no-pager"]
    # Longer than the rest: a debug window can be a lot of lines.
    return Section("logs/boneio.log", _run(command, timeout=60))


def _container_names() -> list[str]:
    """Names of the running containers, as Docker actually calls them.

    Not guessed. Compose prefixes names with the project — the containers here
    are `nodered-caddy-1`, not `caddy` — so a hard-coded list produces "No such
    container" for exactly the logs someone wanted to read.

    Returns:
        Container names, or an empty list when Docker cannot be asked.
    """
    return containers.container_names()


def _docker_report() -> str:
    """Container state, and the tail of each container's log.

    Returns:
        The report text.
    """
    if not containers.helper_available() and shutil.which("docker") is None:
        # Say why rather than producing an empty section: a bundle that does
        # not explain a gap sends the reader looking for the wrong problem.
        return "[docker is not installed on this system]"

    parts = [
        "$ containers ps",
        _describe(containers.containers(), "containers ps"),
        "$ containers status",
        _describe(containers.status(), "containers status"),
    ]
    for name in _container_names():
        parts.append(f"$ container logs --tail 200 {name}")
        parts.append(_describe(containers.container_logs(name), f"logs {name}"))
    return "\n\n".join(parts)


def _describe(result: containers.Result, what: str) -> str:
    """Render a container operation's outcome for the bundle.

    Args:
        result: The outcome.
        what: What was attempted, for the failure line.

    Returns:
        The output, or a line explaining why there is none.
    """
    text = (result.stdout or "") + (result.stderr or "")
    text = text.strip()
    if text:
        return text
    return f"[{what} produced no output]"


def _status_sections(config: dict) -> list[Section]:
    """Whether the things boneIO depends on are where they should be.

    Args:
        config: Parsed configuration.

    Returns:
        One section per subsystem.
    """
    mqtt = config.get("mqtt") if isinstance(config.get("mqtt"), dict) else {}
    host = str(mqtt.get("host", "")).strip()
    #: A broker on this machine is one boneIO installed and can report on; one
    #: somewhere else is the owner's, and `systemctl` here would say nothing.
    local_broker = host in {"localhost", "127.0.0.1", "::1", ""} and bool(mqtt)

    sections = [
        Section("status/docker.txt", _docker_report()),
        Section(
            "status/system.txt",
            "\n\n".join(
                [
                    "$ uptime", _run(["uptime"]),
                    "$ free -h", _run(["free", "-h"]),
                    "$ df -h", _run(["df", "-h"]),
                    "$ systemctl status boneio", _run(["systemctl", "status", "boneio", "--no-pager"]),
                    "$ uname -a", _run(["uname", "-a"]),
                ]
            ),
        ),
        Section(
            "status/network.txt",
            "\n\n".join(
                [
                    "$ ip -brief address", _run(["ip", "-brief", "address"]),
                    "$ ip route", _run(["ip", "route"]),
                    "$ ss -tlnp", _run(["ss", "-tln"]),
                ]
            ),
        ),
    ]

    if local_broker:
        sections.append(
            Section(
                "status/mosquitto.txt",
                "\n\n".join(
                    [
                        "$ systemctl status mosquitto",
                        _run(["systemctl", "status", "mosquitto", "--no-pager"]),
                        "$ journalctl -u mosquitto -n 200",
                        _run(["journalctl", "-u", "mosquitto", "-n", "200", "--no-pager"]),
                    ]
                ),
            )
        )
    else:
        sections.append(
            Section(
                "status/mosquitto.txt",
                f"The broker is at '{host}', not on this device, so there is no "
                "local service to report on. See status/mqtt.txt for whether "
                "boneIO can reach it.",
            )
        )

    return sections


def build(
    config: dict,
    config_file: str | os.PathLike[str],
    *,
    mqtt_status: str = "",
    capture_started: float | None = None,
    serial: str | None = None,
    real_serial: str | None = None,
) -> tuple[bytes, str]:
    """Assemble the diagnostic bundle.

    Args:
        config: Parsed configuration.
        config_file: Path to config.yaml.
        mqtt_status: Connection state as the running process sees it.
        capture_started: Epoch seconds when a debug capture began, if any.
        serial: Effective serial of the device, for the summary.
        real_serial: MAC-derived serial, when an override is in use.

    Returns:
        Tuple of ``(gzipped tar bytes, suggested filename)``.
    """
    started = time.monotonic()
    path = Path(config_file)
    secrets = gather_secrets(config, path.parent)

    sections: list[Section] = [
        Section("README.txt", _readme(len(secrets), capture_started)),
        Section(
            "summary.txt",
            _summary(config, path, capture_started, serial, real_serial),
        ),
        Section("status/mqtt.txt", mqtt_status or "[no MQTT state available]"),
        _log_section(capture_started),
    ]
    sections.extend(_config_sections(path.parent, secrets))
    sections.extend(_status_sections(config))

    name = (
        config.get("boneio", {}).get("name", "boneio")
        if isinstance(config.get("boneio"), dict)
        else "boneio"
    )
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in str(name)).strip("-")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    root = f"boneio-diagnostics-{safe or 'device'}-{stamp}"

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for section in sections:
            # Scrubbed on the way in, without exception. A section added later
            # cannot forget to do it, because there is nowhere else to do it.
            body = scrub_text(section.body, secrets).encode("utf-8")
            info = tarfile.TarInfo(f"{root}/{section.path}")
            info.size = len(body)
            info.mtime = int(time.time())
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(body))

    _LOGGER.info(
        "Diagnostic bundle built: %d files, %d bytes, %.1fs",
        len(sections),
        buffer.tell(),
        time.monotonic() - started,
    )
    return buffer.getvalue(), f"{root}.tar.gz"
