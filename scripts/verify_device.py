#!/usr/bin/env python3
"""Ask the controller you just deployed to whether it still works.

The development loop had a hole. Unit tests run against code with no hardware
and no Manager; the harness in remote_test.sh builds a small application out of
the auth middleware alone, for the same reason. Both were green for every one
of these:

  * The socket refused every connection once a device had an account, because
    whether a token was required had been decided once at startup. Entity state
    reaches a panel through that socket and nowhere else, so the panel showed a
    controller with no outputs, no inputs and no sensors — while every HTTP
    request it made was answered correctly.
  * The migration chain stopped at one plan the signing helper would not
    accept and stayed stopped, six migrations short, for two releases.
  * A value the first-run wizard reads was computed correctly and returned by
    an endpoint the wizard does not call.

What they have in common is that the application was running and answering.
This talks to the real service, after a restart, and asks the questions those
failures would have answered wrongly.

Read-only. It signs in, listens, and compares; it changes nothing. A viewer
account is enough and is what it is meant to be given.

Usage:
    DEV_PASSWORD=... scripts/verify_device.py 192.168.50.220 --user tester
    scripts/verify_device.py 192.168.50.220          # unauthenticated subset

Exit status is 0 when nothing failed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import sys

try:
    import requests
    import websockets
except ImportError as err:  # pragma: no cover
    sys.exit(f"needs requests and websockets: {err}")

G, R, Y, D, O = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


class Result:
    """Tally of what the run found."""

    def __init__(self) -> None:
        self.passed = self.failed = self.skipped = 0

    def ok(self, what: str, detail: str = "") -> None:
        self.passed += 1
        print(f"  {G}PASS{O} {what}" + (f" {D}{detail}{O}" if detail else ""))

    def bad(self, what: str, why: str) -> None:
        self.failed += 1
        print(f"  {R}FAIL{O} {what} — {why}")

    def skip(self, what: str, why: str) -> None:
        self.skipped += 1
        print(f"  {Y}SKIP{O} {what} {D}({why}){O}")

    def note(self, text: str) -> None:
        print(f"  {D}·{O} {text}")


class Panel:
    """The device, over the API a browser uses."""

    def __init__(self, host: str, port: int, tls: bool, timeout: float = 20.0):
        self.host, self.port, self.tls, self.timeout = host, port, tls, timeout
        self.token: str | None = None
        self.base = f"{'https' if tls else 'http'}://{host}:{port}"
        self.http = requests.Session()
        # The certificate is the device's own. Verifying it here would test
        # this laptop's trust store, not the controller.
        self.http.verify = False
        requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]

    def get(self, path: str):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        return self.http.get(self.base + path, timeout=self.timeout, headers=headers)

    def login(self, user: str, password: str) -> str | None:
        """Sign in and remember the token.

        Args:
            user: Account name.
            password: Its password.

        Returns:
            The token, or None.
        """
        try:
            r = self.http.post(
                self.base + "/api/login",
                json={"username": user, "password": password},
                timeout=self.timeout,
            )
        except requests.RequestException:
            return None
        if r.status_code != 200:
            return None
        self.token = (r.json() or {}).get("token")
        return self.token


async def entities_over_socket(panel: Panel, seconds: float) -> dict[str, int]:
    """Open the socket a browser opens and count what the device sends.

    The token travels as a WebSocket subprotocol, which is how the panel sends
    it — and the part that broke, because a server which does not agree to the
    subprotocol fails the handshake in a browser with no error naming the
    cause. Asking for a resync rather than trusting the burst on connect is
    also what the panel does.

    Args:
        panel: The device.
        seconds: How long to listen.

    Returns:
        A count of distinct entities seen, by event type.

    Raises:
        Exception: Whatever the connection attempt raised.
    """
    context = None
    if panel.tls:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    url = f"{'wss' if panel.tls else 'ws'}://{panel.host}:{panel.port}/ws/state"
    subprotocols = [f"token.{panel.token}"] if panel.token else None

    seen: dict[str, set[str]] = {}
    async with websockets.connect(
        url,
        subprotocols=subprotocols,  # type: ignore[arg-type]
        ssl=context,
        open_timeout=15,
        close_timeout=5,
    ) as socket:
        await socket.send("request_state")
        loop = asyncio.get_running_loop()
        end = loop.time() + seconds
        while loop.time() < end:
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=max(0.1, end - loop.time()))
            except (TimeoutError, asyncio.TimeoutError):
                break
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "replace")
            if raw == "pong":
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = str(message.get("event_type") or message.get("type") or "?")
            # entity_id, not id. Getting this wrong counts every message of a
            # kind as the same entity, so an empty controller and a full one
            # both report one of each — which is worse than no check.
            data = message.get("data") if isinstance(message.get("data"), dict) else {}
            ident = str(
                message.get("entity_id")
                or data.get("entity_id")
                or message.get("id")
                or data.get("id")
                or ""
            )
            if ident:
                seen.setdefault(kind, set()).add(ident)
    return {kind: len(ids) for kind, ids in sorted(seen.items())}


def check_reachable(panel: Panel, result: Result) -> dict | None:
    """The device answers, and says what it is.

    Args:
        panel: The device.
        result: Tally to record into.

    Returns:
        The init payload, or None when it could not be read.
    """
    try:
        response = panel.get("/api/init")
    except requests.RequestException as err:
        result.bad("the device answers", str(err))
        return None
    if response.status_code != 200:
        result.bad("the device answers", f"HTTP {response.status_code} from /api/init")
        return None
    data = response.json()
    result.ok("the device answers", f"{data.get('name')} · {data.get('version')}")

    # Read by the first-run wizard, and once returned only by an endpoint the
    # wizard does not call — so the field being present is the check.
    if "configured_before" in data:
        result.ok("/api/init carries what the wizard reads")
    else:
        result.bad("/api/init carries what the wizard reads", "configured_before is missing")
    return data


def check_migrations(panel: Panel, result: Result) -> None:
    """No migration is stuck.

    A refusal stops the queue, and the device keeps working and keeps quiet
    about it — one release sat six migrations short for two versions.

    Args:
        panel: The device.
        result: Tally to record into.
    """
    response = panel.get("/api/migrations/status")
    if response.status_code in (401, 403):
        result.skip("migrations are all applied", "needs a token")
        return
    if response.status_code != 200:
        result.bad("migrations are all applied", f"HTTP {response.status_code}")
        return
    data = response.json() or {}
    pending = data.get("pending_count", data.get("pending", 0))
    status = str(data.get("status", "")).lower()
    if pending:
        result.bad("migrations are all applied", f"{pending} pending, status={status or '?'}")
    elif status == "error":
        result.bad("migrations are all applied", f"status={status}: {data.get('last_error')}")
    else:
        result.ok("migrations are all applied")


def check_hardware(panel: Panel, result: Result) -> None:
    """Nothing failed to initialise.

    Args:
        panel: The device.
        result: Tally to record into.
    """
    response = panel.get("/api/hardware/errors")
    if response.status_code in (401, 403):
        result.skip("no hardware errors", "needs a token")
        return
    if response.status_code != 200:
        result.bad("no hardware errors", f"HTTP {response.status_code}")
        return
    errors = (response.json() or {}).get("errors") or []
    if errors:
        result.bad("no hardware errors", f"{len(errors)}: {errors[:2]}")
    else:
        result.ok("no hardware errors")


def check_entities(panel: Panel, result: Result, listen: float) -> None:
    """The socket opens, and the device is not empty over it.

    The centre of this script. Nothing polls for entity state, so a socket that
    will not open — or opens and says nothing — is a controller that looks
    empty to every panel while answering HTTP perfectly.

    Args:
        panel: The device.
        result: Tally to record into.
        listen: Seconds to listen for.
    """
    if not panel.token:
        result.skip("the socket delivers entities", "needs a token")
        return
    try:
        counts = asyncio.run(entities_over_socket(panel, listen))
    except Exception as err:  # noqa: BLE001 - any failure is the finding
        result.bad("the socket delivers entities", f"{type(err).__name__}: {err}")
        return

    total = sum(counts.values())
    if total == 0:
        result.bad(
            "the socket delivers entities",
            "connected, and nothing arrived in "
            f"{listen:.0f}s — this is what an empty panel looks like",
        )
        return
    result.ok("the socket delivers entities", ", ".join(f"{k}={v}" for k, v in counts.items()))


def check_config_matches(panel: Panel, result: Result) -> None:
    """The configuration the device serves has the outputs it should.

    Args:
        panel: The device.
        result: Tally to record into.
    """
    response = panel.get("/api/config")
    if response.status_code in (401, 403):
        result.skip("the configuration is readable", "needs a token")
        return
    if response.status_code != 200:
        result.bad("the configuration is readable", f"HTTP {response.status_code}")
        return
    payload = response.json() or {}
    # The endpoint wraps it: {"config": {...}}. Reading the top level finds
    # nothing and reports a device with no entities configured at all.
    config = payload.get("config") if isinstance(payload.get("config"), dict) else payload
    sections = {
        name: len(config[name])
        for name in ("output", "event", "binary_sensor", "cover")
        if isinstance(config.get(name), list)
    }
    if not sections:
        result.bad("the configuration is readable", "no entity sections at all")
        return
    result.ok("the configuration is readable", ", ".join(f"{k}={v}" for k, v in sections.items()))


def check_posture(panel: Panel, result: Result) -> None:
    """The security posture can be computed, and what it says.

    Reported rather than judged: a development controller is allowed to have
    findings. It failing to answer is the problem.

    Args:
        panel: The device.
        result: Tally to record into.
    """
    response = panel.get("/api/security/posture")
    if response.status_code in (401, 403):
        result.skip("the security posture answers", "needs an admin token")
        return
    if response.status_code != 200:
        result.bad("the security posture answers", f"HTTP {response.status_code}")
        return
    summary = (response.json() or {}).get("summary") or {}
    result.ok("the security posture answers", f"{summary.get('actionable', '?')} actionable")


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Command line arguments, or None for ``sys.argv``.

    Returns:
        Process exit status: 0 when nothing failed.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="the controller, by name or address")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--tls", action="store_true", help="talk HTTPS, for the proxy port")
    parser.add_argument("--user", default=os.environ.get("DEV_USER", ""))
    parser.add_argument(
        "--listen",
        type=float,
        default=10.0,
        help="seconds to wait for entity state (default 10)",
    )
    args = parser.parse_args(argv)

    password = os.environ.get("DEV_PASSWORD", "")
    panel = Panel(args.host, args.port, args.tls)
    result = Result()

    print(f"\n{D}verify{O} {panel.base}")
    data = check_reachable(panel, result)
    if data is None:
        print(f"\n  {R}1 failed{O} — nothing else could be asked\n")
        return 1

    if data.get("auth_required"):
        if args.user and password:
            if panel.login(args.user, password):
                result.ok("signed in", f"as {args.user}")
            else:
                result.bad("signed in", f"/api/login refused {args.user}")
        else:
            result.note(
                "no credentials — set DEV_USER and DEV_PASSWORD to check the "
                "socket, the migrations and the configuration"
            )
    else:
        result.note("this device has no accounts yet, so nothing needs a token")

    check_migrations(panel, result)
    check_hardware(panel, result)
    check_config_matches(panel, result)
    check_entities(panel, result, args.listen)
    check_posture(panel, result)

    colour = R if result.failed else G
    print(
        f"\n  {colour}{result.passed} passed, {result.failed} failed"
        f"{O}{D}, {result.skipped} skipped{O}\n"
    )
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
