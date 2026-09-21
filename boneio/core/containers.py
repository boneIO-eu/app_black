"""Container operations, through the privileged helper when it is there.

The application talks to Docker today because the ``boneio`` account is in the
``docker`` group — which is root-equivalent, since a container can bind-mount
the host root and write to it. Taking the account out of that group is the fix
(F-04), and this module is what makes it possible: every container operation
goes through ``boneio-containers``, which accepts a fixed verb and passes
nothing from the caller to Docker.

Direct ``docker`` invocation stays as a fallback while the helper is not
installed. That is not a loophole, it is the transition: a device that has not
applied the trust-transition migration yet is in exactly the state it is in
today, and refusing to manage its containers would break Node-RED and the TLS
panel for no gain. Once the helper is present it is always preferred, and once
the account leaves the ``docker`` group the fallback stops working on its own.

Nothing here is a security boundary. The boundary is the helper, which refuses
to run compose against a compose file the caller could have written.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

HELPER_PATH = "/usr/sbin/boneio-containers"
#: Where the compose project lives. The helper has its own hard-coded copy of
#: this; ours is only used by the fallback.
PROJECT_DIR = Path.home() / "docker" / "nodered"

#: What compose interpolates into the compose file. Writable by the
#: application; the compose file next to it is not. See set_project_env.
ENV_FILE = PROJECT_DIR / ".env"

#: The live compose file. Root-owned — read here, never written.
COMPOSE_FILE = PROJECT_DIR / "docker-compose.yaml"

CADDY_SERVICE = "caddy"
NODERED_SERVICE = "node-red"

#: verb → the equivalent direct command, for the fallback path. Keeping the two
#: side by side is deliberate: it is the only way to see that the helper's verb
#: really does what the code used to do.
_FALLBACK: dict[str, list[str]] = {
    "status": ["docker", "compose", "ps", "--format", "json"],
    "ps": ["docker", "ps", "-a", "--format", "json"],
    "names": ["docker", "ps", "-a", "--format", "{{.Names}}"],
    "up": ["docker", "compose", "up", "-d"],
    "down": ["docker", "compose", "down"],
    "pull": ["docker", "compose", "pull"],
    "start-nodered": ["docker", "compose", "up", "-d", NODERED_SERVICE],
    "stop-nodered": ["docker", "compose", "stop", NODERED_SERVICE],
    "restart-nodered": ["docker", "compose", "restart", NODERED_SERVICE],
    "pull-nodered": ["docker", "compose", "pull", NODERED_SERVICE],
    "start-caddy": ["docker", "compose", "up", "-d", CADDY_SERVICE],
    "restart-caddy": ["docker", "compose", "restart", CADDY_SERVICE],
    "reload-caddy": [
        "docker", "compose", "exec", CADDY_SERVICE,
        # /tmp/Caddyfile, not /etc/caddy/Caddyfile: the container runs the
        # file init-certs.sh writes on every start. /etc/caddy/Caddyfile is the
        # stock config baked into the image, and reloading that swaps the
        # working proxy for Caddy's welcome page — HTTPS goes down and stays
        # down until the container is restarted.
        "caddy", "reload", "--config", "/tmp/Caddyfile",
    ],
}

_LOG_VERBS = {"logs-caddy": CADDY_SERVICE, "logs-nodered": NODERED_SERVICE}

#: Verbs whose fallback needs the caller's argument, so they are built in
#: :func:`run` rather than looked up in a table.
_PARAMETERISED = {"logs-container"}

#: Verbs that only the helper can perform. The fallback used to be "write the
#: compose file from the application", which is the thing being removed: that
#: file is what ``docker compose up`` executes, so whoever can write it can run
#: a container as root with the host filesystem mounted.
_HELPER_ONLY = {
    "apply-cloud-template",
    "remove-cloud-template",
    "set-nodered-image",
}


@dataclass
class Result:
    """Outcome of a container operation.

    Attributes:
        returncode: Process exit status.
        stdout: Captured standard output.
        stderr: Captured standard error.
        via_helper: Whether the privileged helper was used.
    """

    returncode: int
    stdout: str
    stderr: str
    via_helper: bool

    @property
    def ok(self) -> bool:
        """Whether the operation succeeded."""
        return self.returncode == 0

    def json(self) -> list | dict | None:
        """Parse the output as JSON, tolerating Docker's line-delimited form.

        Returns:
            The parsed output, or None when it is not JSON.
        """
        text = self.stdout.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            pass
        items = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except ValueError:
                return None
        return items or None


_helper_available: bool | None = None


def helper_available(recheck: bool = False) -> bool:
    """Whether ``boneio-containers`` is installed and callable without a password.

    Args:
        recheck: Ask again instead of reusing the cached answer. Used after a
            migration may have installed it.

    Returns:
        True when the helper can be used.
    """
    global _helper_available
    if _helper_available is not None and not recheck:
        return _helper_available

    if not (os.path.isfile(HELPER_PATH) and os.access(HELPER_PATH, os.X_OK)):
        _helper_available = False
        return False
    try:
        result = subprocess.run(
            ["sudo", "-n", HELPER_PATH, "--list-verbs"],
            capture_output=True, text=True, timeout=20,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        _LOGGER.warning("boneio-containers is present but not callable: %s", exc)
        _helper_available = False
        return False

    _helper_available = result.returncode == 0
    if _helper_available:
        _LOGGER.info("Using boneio-containers for container operations.")
    else:
        _LOGGER.warning(
            "boneio-containers refused --list-verbs (rc=%d): %s",
            result.returncode, result.stderr.strip(),
        )
    return _helper_available


def run(verb: str, argument: str | None = None, timeout: int = 120) -> Result:
    """Perform one container operation.

    Args:
        verb: One of the helper's verbs.
        argument: A log line count or a domain, for the verbs that take one.
        timeout: Seconds to allow.

    Returns:
        The outcome.

    Raises:
        ValueError: If the verb is unknown to this module.
    """
    if helper_available():
        argv = ["sudo", "-n", HELPER_PATH, verb]
        if argument is not None:
            argv.append(str(argument))
        return _execute(argv, timeout=timeout, via_helper=True, cwd=None)

    if verb in _HELPER_ONLY:
        return Result(
            returncode=1,
            stdout="",
            stderr=(
                f"{verb} needs {HELPER_PATH}, which is not installed. The compose "
                "file is no longer written by the application — apply the pending "
                "system migrations and try again."
            ),
            via_helper=False,
        )

    if verb == "logs-container":
        if argument is None:
            raise ValueError("logs-container needs a container name")
        argv = ["docker", "logs", "--tail", "200", str(argument)]
    elif verb in _LOG_VERBS:
        lines = str(argument) if argument is not None else "200"
        argv = [
            "docker", "compose", "logs", "--tail", lines, "--no-color",
            _LOG_VERBS[verb],
        ]
    elif verb in _FALLBACK:
        argv = list(_FALLBACK[verb])
    else:
        raise ValueError(f"unknown container verb: {verb!r}")

    return _execute(argv, timeout=timeout, via_helper=False, cwd=str(PROJECT_DIR))


def _execute(
    argv: list[str], timeout: int, via_helper: bool, cwd: str | None
) -> Result:
    """Run a command and capture its outcome.

    Args:
        argv: The command.
        timeout: Seconds to allow.
        via_helper: Whether this is the helper path, for the result.
        cwd: Working directory, or None.

    Returns:
        The outcome; a failure to start is reported, never raised.
    """
    try:
        completed = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return Result(1, "", f"timed out after {timeout}s", via_helper)
    except OSError as exc:
        return Result(1, "", str(exc), via_helper)

    if completed.returncode != 0:
        _LOGGER.warning(
            "container operation failed (rc=%d, helper=%s): %s",
            completed.returncode, via_helper, completed.stderr.strip(),
        )
    return Result(
        completed.returncode, completed.stdout or "", completed.stderr or "", via_helper
    )


# --------------------------------------------------------------------- verbs


def status(timeout: int = 30) -> Result:
    """Compose project status as JSON."""
    return run("status", timeout=timeout)


def service_status(service: str, timeout: int = 30) -> dict | None:
    """One compose service's status.

    The helper reports the whole project rather than taking a service name, so
    the filtering happens here. That is deliberate: a service name from the
    caller is one more string that would otherwise reach Docker.

    Args:
        service: Compose service name.
        timeout: Seconds to allow.

    Returns:
        The service's entry, or None when it is not running or cannot be read.
    """
    parsed = status(timeout=timeout).json()
    if parsed is None:
        return None
    if isinstance(parsed, dict):
        parsed = [parsed]
    for item in parsed:
        if not isinstance(item, dict):
            continue
        if item.get("Service") == service or item.get("Name", "").endswith(service):
            return item
    return None


def containers(timeout: int = 30) -> Result:
    """All containers on the host as JSON."""
    return run("ps", timeout=timeout)


def container_names(timeout: int = 30) -> list[str]:
    """Names of every container on the host.

    Args:
        timeout: Seconds to allow.

    Returns:
        The names, or an empty list when Docker cannot be asked. Compose
        prefixes them with the project, so these are ``nodered-caddy-1`` rather
        than ``caddy``.
    """
    result = run("names", timeout=timeout)
    if not result.ok:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def container_logs(name: str, timeout: int = 60) -> Result:
    """The tail of one container's log, by name.

    Args:
        name: Container name as reported by :func:`container_names`.
        timeout: Seconds to allow.

    Returns:
        The outcome. The helper accepts the name only if such a container
        exists, so a stale name is a refusal rather than a shell surprise.
    """
    return run("logs-container", argument=name, timeout=timeout)


def start_nodered(timeout: int = 120) -> Result:
    """Bring Node-RED up."""
    return run("start-nodered", timeout=timeout)


def stop_nodered(timeout: int = 60) -> Result:
    """Stop Node-RED."""
    return run("stop-nodered", timeout=timeout)


def restart_nodered(timeout: int = 120) -> Result:
    """Restart Node-RED."""
    return run("restart-nodered", timeout=timeout)


def pull_nodered(timeout: int = 600) -> Result:
    """Pull the Node-RED image."""
    return run("pull-nodered", timeout=timeout)


def start_caddy(timeout: int = 120) -> Result:
    """Bring Caddy up."""
    return run("start-caddy", timeout=timeout)


def restart_caddy(timeout: int = 60) -> Result:
    """Restart Caddy."""
    return run("restart-caddy", timeout=timeout)


def reload_caddy(timeout: int = 30) -> Result:
    """Ask Caddy to reload its configuration."""
    return run("reload-caddy", timeout=timeout)


def logs(service: str, lines: int = 200, timeout: int = 60) -> Result:
    """Tail a service's log.

    Args:
        service: ``"caddy"`` or ``"node-red"``.
        lines: How many lines.
        timeout: Seconds to allow.

    Returns:
        The outcome.

    Raises:
        ValueError: If the service has no log verb.
    """
    verb = {CADDY_SERVICE: "logs-caddy", NODERED_SERVICE: "logs-nodered"}.get(service)
    if verb is None:
        raise ValueError(f"no log verb for service {service!r}")
    return run(verb, argument=str(lines), timeout=timeout)


def apply_cloud_template(timeout: int = 60) -> Result:
    """Switch the compose project to the cloud template.

    The file is copied by the helper from a root-owned template, with nothing
    substituted in: the cloud setup serves a wildcard certificate and takes the
    hostname from the container, so no caller value belongs in it. The
    application no longer writes the compose file at all — that file is what
    ``docker compose up`` executes, so writing it was equivalent to being able
    to run a container as root.

    Args:
        timeout: Seconds to allow.

    Returns:
        The outcome.
    """
    return run("apply-cloud-template", timeout=timeout)


def set_nodered_image(tag: str, timeout: int = 60) -> Result:
    """Change the Node-RED image tag in the compose file.

    The application used to rewrite the compose file to do this, which is the
    same escalation path as the docker group reached through the update flow:
    that file is what ``docker compose up`` executes. The helper changes one
    tag, matched by a fixed pattern, and validates the tag first.

    Args:
        tag: The image tag, e.g. ``"4.1.2-22-minimal"``.
        timeout: Seconds to allow.

    Returns:
        The outcome.
    """
    return run("set-nodered-image", argument=tag, timeout=timeout)


def remove_cloud_template(timeout: int = 60) -> Result:
    """Restore the plain compose template."""
    return run("remove-cloud-template", timeout=timeout)


def set_project_env(name: str, value: str) -> bool:
    """Set one variable in the compose project's ``.env``, leaving the rest alone.

    Compose reads ``.env`` from the project directory and interpolates it into
    the compose file, which is how the panel's own port reaches Caddy. The
    application may write this file: the directory belongs to it. It may not
    write the compose file beside it, which is root-owned because
    ``docker compose up`` executes it — that distinction is F-04, and it holds
    here because interpolation substitutes into scalar values after the YAML is
    parsed, so nothing passed this way can introduce a volume or an entrypoint.

    Read-modify-write rather than truncate: an operator may have put their own
    variables here, and a port change is no reason to lose them. Comments and
    order are preserved, and the replacement is atomic, so a crash mid-write
    cannot leave compose reading half a file.

    Args:
        name: Variable name, e.g. ``"WEB_PORT"``.
        value: Its value, written verbatim.

    Returns:
        True when the file now says so, False when it could not be written.
    """
    assignment = f"{name}={value}"
    try:
        existing = ENV_FILE.read_text().splitlines()
    except FileNotFoundError:
        existing = []
    except OSError as err:
        _LOGGER.error("Could not read %s: %s", ENV_FILE, err)
        return False

    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=")
    lines, replaced = [], False
    for line in existing:
        if pattern.match(line):
            # Only the first assignment is authoritative for compose, but a
            # later duplicate would override it, so every one has to go.
            if not replaced:
                lines.append(assignment)
                replaced = True
            continue
        lines.append(line)
    if not replaced:
        lines.append(assignment)

    body = "\n".join(lines).rstrip("\n") + "\n"
    try:
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=ENV_FILE.parent, prefix=".env.")
        try:
            with os.fdopen(handle, "w") as stream:
                stream.write(body)
            os.chmod(temporary, 0o644)
            os.replace(temporary, ENV_FILE)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise
    except OSError as err:
        _LOGGER.error("Could not write %s: %s", ENV_FILE, err)
        return False

    _LOGGER.info("Set %s in %s", assignment, ENV_FILE)
    return True


def cloud_template_is_live() -> bool:
    """Whether the compose file in use is the cloud template.

    Asked of the file rather than of the configuration, because the two
    disagree on real devices: a controller whose ``web.cloud.enabled`` is true
    but whose registration never completed is still running the local
    template. Refreshing it from the cloud one on the strength of the config
    would put it on an init script whose certificates are not there.

    Returns:
        True for the cloud template, False for the local one or when the file
        cannot be read — the local template is the safe assumption, being the
        one that needs nothing from outside the device.
    """
    try:
        body = COMPOSE_FILE.read_text()
    except OSError as err:
        _LOGGER.warning("Could not read %s, assuming the local template: %s", COMPOSE_FILE, err)
        return False
    # The init script each template runs is the thing that differs and the
    # thing that matters: it decides which certificate Caddy serves.
    return "init-certs-cloud.sh" in body
