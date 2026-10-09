#!/usr/bin/env python3
"""Drive the panel in headless Chromium on a real controller, before a release.

Two scenarios, both ending with the cloud address served with a real
certificate:

  wizard-cloud    the first-run wizard: account, then the cloud step, until
                  the wizard confirms the new address. The controller must be
                  unprovisioned (no users.json) with cloud registration off.
  settings-cloud  Settings → Web server: turn cloud registration off (Caddy
                  back on its self-signed certificate), save, turn it on, save,
                  until the cloud name is served by Let's Encrypt again.

The panel is reached through an SSH tunnel to localhost, so the browser is on
a local origin, as on a page opened by IP: the cloud address is another
origin. Chromium ignores certificate errors; the certificate actually served
is checked from Python, by SNI, through the same tunnel.

Usage:
  scripts/browser_e2e.py wizard-cloud   --ssh boneio@192.168.50.141 --credentials FILE
  scripts/browser_e2e.py settings-cloud --ssh boneio@192.168.50.141 --credentials FILE

FILE holds ``user:password`` (test credentials; never printed). For
wizard-cloud they become the new administrator — and, through the wizard, the
SSH password of the boneio account. Labels come from the panel's own locale
(``--lang``, the language the controller shows). Screenshots go to ``--out``.
Needs Chromium and ``websockets`` (pyenv black13 has it).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

LOCALES = Path(__file__).resolve().parents[1] / "frontend" / "src" / "locales"
LOCAL_PORT = 18443
CDP_PORT = 9334

HELPERS = r"""
window.__t = {
  buttons() {
    return [...document.querySelectorAll('button')].filter(b => !b.disabled && b.offsetParent !== null);
  },
  click(text) {
    const el = this.buttons().find(b => b.innerText.trim() === text)
            || this.buttons().find(b => b.innerText.trim().startsWith(text));
    if (!el) return 'no button "' + text + '": ' + this.buttons().map(b => b.innerText.trim()).join(' / ');
    el.click(); return 'clicked ' + el.innerText.trim();
  },
  fill(selector, value, index = 0) {
    const el = document.querySelectorAll(selector)[index];
    if (!el) return 'no input ' + selector + '#' + index;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, value);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    return 'filled ' + selector + '#' + index;
  },
  toggle(label) {
    const span = [...document.querySelectorAll('label span')].find(s => s.innerText.trim() === label);
    const input = span && span.closest('label').querySelector('input[type=checkbox]');
    if (!input) return null;
    return input.checked;
  },
  flip(label) {
    const span = [...document.querySelectorAll('label span')].find(s => s.innerText.trim() === label);
    const input = span && span.closest('label').querySelector('input[type=checkbox]');
    if (!input) return 'no toggle ' + label;
    input.click(); return 'toggled ' + label + ' -> ' + input.checked;
  },
  text() { return document.body ? document.body.innerText : ''; },
};
"""


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def served_issuer(sni: str) -> str:
    """The issuer of the certificate served for *sni* through the tunnel."""
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    with socket.create_connection(("127.0.0.1", LOCAL_PORT), timeout=10) as raw:
        with ctx.wrap_socket(raw, server_hostname=sni) as tls:
            der = tls.getpeercert(binary_form=True)
    out = subprocess.run(["openssl", "x509", "-inform", "DER", "-noout", "-issuer"],
                         input=der, capture_output=True, check=False).stdout.decode()
    return out.strip().removeprefix("issuer=")


class Page:
    """Just enough of the DevTools protocol for these scenarios."""

    def __init__(self, ws):
        self.ws, self.n, self.console = ws, 0, []
        # Saves of a settings section: request id -> (start, end or None, status).
        self.saves: dict[str, list] = {}
        self.answered: set[str] = set()

    async def call(self, method, **params):
        self.n += 1
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("method") == "Page.javascriptDialogOpening":
                # confirm() before turning cloud off: accept, as a person would.
                log(f"dialog: {msg['params'].get('message', '')[:80]}… accepted")
                await self.ws.send(json.dumps({"id": 0, "method": "Page.handleJavaScriptDialog",
                                               "params": {"accept": True}}))
            elif msg.get("method") == "Network.requestWillBeSent":
                req = msg["params"]["request"]
                if req["method"] == "PUT" and "/api/config/" in req["url"]:
                    self.saves[msg["params"]["requestId"]] = [time.time(), None, None]
            elif msg.get("method") == "Network.responseReceived":
                self.answered.add(msg["params"]["response"]["url"].split("?")[0])
                if msg["params"]["requestId"] in self.saves:
                    self.saves[msg["params"]["requestId"]][2] = msg["params"]["response"]["status"]
            elif msg.get("method") in ("Network.loadingFinished", "Network.loadingFailed") \
                    and msg["params"].get("requestId") in self.saves:
                self.saves[msg["params"]["requestId"]][1] = time.time()
            elif msg.get("method") == "Log.entryAdded":
                e = msg["params"]["entry"]
                self.console.append(f"{e.get('level')}: {e.get('text', '')[:160]}")
            if msg.get("id") == self.n:
                return msg

    async def js(self, expr):
        r = await self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        return r["result"]["result"].get("value")

    async def do(self, expr, wait=2.0):
        log(await self.js(expr))
        await asyncio.sleep(wait)

    async def text(self) -> str:
        return (await self.js("window.__t ? __t.text() : ''")) or ""

    async def wait_for(self, needle: str, timeout: float = 60) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if needle in await self.text():
                return True
            await asyncio.sleep(1)
        return False

    async def open(self, url: str) -> None:
        await self.call("Page.navigate", url=url)
        for _ in range(30):
            if len(await self.text()) > 50:
                return
            await asyncio.sleep(1)

    async def shot(self, out: Path, name: str) -> None:
        r = await self.call("Page.captureScreenshot", format="png")
        path = out / f"{name}.png"
        path.write_bytes(base64.b64decode(r["result"]["data"]))
        log(f"screenshot {path}")


async def wizard_cloud(page: Page, base: str, user: str, password: str, L: dict, out: Path) -> bool:
    ob = L["onboarding"]

    def prefix(key):
        return ob[key].split("{{")[0].strip()[:40]

    await page.open(base + "/")
    if L["panel_guard"]["continue_anyway"] in await page.text():
        await page.do(f"__t.click({json.dumps(L['panel_guard']['continue_anyway'])})", 4)
    await page.do(f"__t.click({json.dumps(ob['start'])})")
    await page.do(f"__t.fill('input[autocomplete=username]', {json.dumps(user)})", 0.3)
    for i in (0, 1):
        await page.do(f"__t.fill('input[autocomplete=new-password]', {json.dumps(password)}, {i})", 0.3)
    await page.do(f"__t.click({json.dumps(ob['create_account'])})", 1)
    # The account step also sets the SSH password; the steps up to the cloud
    # one are skipped.
    for _ in range(90):
        body = await page.text()
        if ob["cloud_enable"] in body:
            break
        skip = next((b for b in (ob["skip_import"], ob["devices_skip"]) if b in body), None)
        if skip:
            await page.do(f"__t.click({json.dumps(skip)})", 2)
        await asyncio.sleep(2)
    else:
        log("never reached the cloud step")
        await page.shot(out, "wizard-stuck")
        return False
    await page.shot(out, "wizard-cloud-before")
    started = time.time()
    await page.do(f"__t.click({json.dumps(ob['cloud_enable'])})", 1)
    states = {"ready": prefix("cloud_ready"), "ready_here": prefix("cloud_ready_here"),
              "timeout": prefix("cloud_timeout_at"), "unreachable": prefix("cloud_unreachable"),
              "failed": ob["cloud_failed"], "switching": ob["cloud_switching_title"]}
    last = None
    while time.time() - started < 240:
        body = await page.text()
        state = next((k for k, v in states.items() if v in body), "?")
        if state != last:
            log(f"+{int(time.time() - started)}s: {state}")
            last = state
        if state in ("ready", "ready_here", "timeout", "unreachable", "failed"):
            break
        await asyncio.sleep(2)
    await page.shot(out, "wizard-cloud-after")
    return last in ("ready", "ready_here")


async def settings_cloud(page: Page, base: str, user: str, password: str, L: dict, sni: str,
                         out: Path) -> bool:
    label = L["boneio_config"]["cloud_registration"]
    save = L["settings"]["save"]
    await page.open(base + "/")
    if L["panel_guard"]["continue_anyway"] in await page.text():
        await page.do(f"__t.click({json.dumps(L['panel_guard']['continue_anyway'])})", 4)
    if await page.js(
            "!!document.querySelector('input[autocomplete=current-password]')"):
        await page.do(f"__t.fill('input[autocomplete=username]', {json.dumps(user)})", 0.3)
        await page.do(f"__t.fill('input[autocomplete=current-password]', {json.dumps(password)})", 0.3)
        await page.do(f"__t.click({json.dumps(L['login']['submit'])})", 4)
    await page.open(base + "/settings/web")
    if not await page.wait_for(label, 30):
        log("no cloud toggle on the web server page")
        await page.shot(out, "settings-no-toggle")
        return False
    # The form is drawn, with defaults, before the configuration arrives; a save
    # made before that replaces the section with those defaults.
    for _ in range(60):
        await page.js("1")
        if f"{base}/api/config" in page.answered:
            break
        await asyncio.sleep(1)
    await asyncio.sleep(2)
    restart = L["settings"]["app_restart_required"]
    save_enabled = f"[...document.querySelectorAll('button')].some(b => b.innerText.trim() === {json.dumps(save)} && !b.disabled)"

    async def until_save(enabled: bool, seconds: int = 40) -> bool:
        """Turning cloud off first reloads Caddy (~8 s) before the form changes;
        a save is done when its button goes back to disabled."""
        for _ in range(seconds):
            if bool(await page.js(save_enabled)) == enabled:
                return True
            await asyncio.sleep(1)
        return False

    async def save_and_wait(expect: str, what: str) -> bool:
        if not await until_save(True):
            log(f"{what}: the save button never became active")
            await page.shot(out, f"settings-{what}-nosave")
            return False
        before = set(page.saves)
        await page.do(f"__t.click({json.dumps(save)})", 0)
        started = time.time()
        # Until the PUT is answered — not just the button greyed out while it
        # runs: a change made meanwhile is forgotten when the save finishes.
        while time.time() - started < 60:
            await page.js("1")  # pumps the network events
            new = [v for k, v in page.saves.items() if k not in before]
            if new and new[-1][1] is not None:
                log(f"PUT answered {new[-1][2]} after {new[-1][1] - new[-1][0]:.1f}s")
                break
            await asyncio.sleep(0.5)
        else:
            log("the save was not answered within 60 s")
        await asyncio.sleep(2)
        if restart in await page.text():
            log(f"{what}: the panel asks for a restart the cloud toggle does not need")
            await page.shot(out, f"settings-{what}-restart")
            return False
        while time.time() - started < 180:
            issuer = served_issuer(sni)
            if expect in issuer:
                log(f"+{int(time.time() - started)}s after save: {sni} served by {issuer}")
                return True
            await asyncio.sleep(3)
        log(f"{what}: still served by {served_issuer(sni)} after 180 s")
        await page.shot(out, f"settings-{what}")
        return False

    log(f"before: toggle {await page.js(f'__t.toggle({json.dumps(label)})')}, {sni} served by {served_issuer(sni)}")
    if await page.js(f"__t.toggle({json.dumps(label)})"):
        await page.do(f"__t.flip({json.dumps(label)})", 1)
        if not await save_and_wait("Caddy Local Authority", "off"):
            return False
    await page.shot(out, "settings-cloud-off")
    await page.do(f"__t.flip({json.dumps(label)})", 2)
    if L["settings"]["pwa_privacy_understood"] in await page.text():
        await page.do(f"__t.click({json.dumps(L['settings']['pwa_privacy_understood'])})", 1)
    ok = await save_and_wait("Let's Encrypt", "on")
    await page.shot(out, "settings-cloud-on")
    return ok


async def run(args) -> bool:
    user, password = Path(args.credentials).read_text().strip().split(":", 1)
    L = json.loads((LOCALES / args.lang / "common.json").read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    host = args.ssh.split("@")[-1]
    sni = args.cloud_name or None

    tunnel = subprocess.Popen([
        "ssh", "-N", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-L", f"{LOCAL_PORT}:127.0.0.1:8443", args.ssh,
    ], stderr=subprocess.DEVNULL)
    chromium = shutil.which("chromium") or shutil.which("google-chrome-stable")
    browser = subprocess.Popen([
        chromium, "--headless=new", "--ignore-certificate-errors", "--no-first-run",
        "--window-size=700,1100", f"--user-data-dir={tempfile.mkdtemp()}",
        f"--remote-debugging-port={CDP_PORT}", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"https://localhost:{LOCAL_PORT}"
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json"))
                served_issuer(host)
                break
            except OSError:
                time.sleep(0.3)
        if sni is None:
            # The serial is the MAC's tail, as boneIO computes it; the hostname
            # can be wrong (an image that carried its build board's name).
            mac = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
                 "-o", "UserKnownHostsFile=/dev/null", args.ssh,
                 "cat /sys/class/net/eth0/address 2>/dev/null || cat /sys/class/net/end0/address"],
                capture_output=True, text=True, check=True,
            ).stdout.strip().replace(":", "")
            sni = f"blk{mac[-6:].lower()}.black.boneio.app"
        ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
        async with websockets.connect(ws_url, max_size=None) as ws:
            page = Page(ws)
            await page.call("Log.enable")
            await page.call("Page.enable")
            await page.call("Network.enable")
            await page.call("Page.addScriptToEvaluateOnNewDocument", source=HELPERS)
            if args.scenario == "wizard-cloud":
                ok = await wizard_cloud(page, base, user, password, L, out)
            else:
                ok = await settings_cloud(page, base, user, password, L, sni, out)
            errors = [c for c in page.console if c.startswith("error") and "401" not in c and "403" not in c]
            for line in errors[-5:]:
                log(f"console {line}")
            log(f"{args.scenario}: {'PASS' if ok else 'FAIL'}; {sni} served by {served_issuer(sni)}")
            return ok
    finally:
        browser.terminate()
        tunnel.terminate()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("scenario", choices=("wizard-cloud", "settings-cloud"))
    parser.add_argument("--ssh", required=True, help="boneio@<controller>, with key login")
    parser.add_argument("--credentials", required=True, help="file with user:password")
    parser.add_argument("--lang", default="pl", help="the panel's language (locale directory)")
    parser.add_argument("--cloud-name", help="defaults to <serial>.black.boneio.app")
    parser.add_argument("--out", default=tempfile.gettempdir() + "/boneio-e2e")
    return 0 if asyncio.run(run(parser.parse_args())) else 1


if __name__ == "__main__":
    sys.exit(main())
