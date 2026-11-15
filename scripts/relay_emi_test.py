#!/usr/bin/env python3
"""Bench test: does switching one relay reset the expanders or fake input edges?

Run on the controller, with the boneIO venv (it has paho-mqtt), so the toggle
times and the journal share one clock:

    /home/boneio/boneio/venv/bin/python relay_emi_test.py run OUT_04 --cycles 200 --period 3

The broker and account come from the controller's own mqtt.yaml/secrets.yaml.

``run`` switches the output ON/OFF through MQTT, writes the time of every
transition to a CSV and then exports the matching boneio journal next to it.
``analyze`` pairs each logged event with the transition that preceded it:

    python3 relay_emi_test.py analyze toggles.csv journal.txt

Input edges are only logged at DEBUG; before the test add to config.yaml
``logger: {logs: {boneio.hardware.gpio.input.manager: debug}}`` and restart.

An expander reset is caught on the next write to that expander, before the
write happens, so a reset found while switching ON was caused by the OFF
before it (and the other way round). A reset of an expander that is not
being switched is caught only by the 30 s watchdog and cannot be attributed.
"""

import argparse
import csv
import re
import subprocess
import sys
import time
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime

JOURNAL_TS = re.compile(r"^(\d{4}-\d\d-\d\dT[\d:.]+[+-]\d\d:?\d\d)\s")
MCP_ON_WRITE = re.compile(r"MCP23017@(0x[0-9A-F]{2}) IODIR[AB] reads 0x")
MCP_BY_WATCHDOG = re.compile(r"MCP23017@(0x[0-9A-F]{2}) lost its configuration")
GPIO_EDGE = re.compile(r"GPIO event: (rising|falling) edge on (.+?) \(")
DETECTION = re.compile(r"Detected (\w+) (?:click|press) on (.+?) \(|Binary sensor (.+?) \(\S+\): (pressed|released)")
STALE = re.compile(r"Stale release on (.+?) \(")
DELAY_BINS_MS = (10, 100, 1000)


def run(args: argparse.Namespace) -> None:
    import paho.mqtt.client as mqtt

    host, port, user, password = args.host, args.port, args.user, args.password
    topic_prefix = "boneio"
    if not user:
        # Same broker and account boneIO itself uses.
        import yaml

        secrets = yaml.safe_load(open(f"{args.config_dir}/secrets.yaml")) or {}

        class Loader(yaml.SafeLoader):
            pass

        Loader.add_constructor("!secret", lambda loader, node: secrets[loader.construct_scalar(node)])
        cfg = yaml.load(open(f"{args.config_dir}/mqtt.yaml"), Loader=Loader) or {}
        cfg = cfg.get("mqtt", cfg)
        host, port = host or cfg.get("host", "localhost"), port or cfg.get("port", 1883)
        user, password = cfg.get("username"), cfg.get("password")
        topic_prefix = cfg.get("topic_prefix", topic_prefix)

    states: list[str] = []
    found: list[str] = []

    def on_message(_client, _userdata, msg) -> None:
        found.append(msg.topic.rsplit("/output/", 1)[0])
        states.append(msg.payload.decode(errors="replace"))

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if user:
        client.username_pw_set(user, password)
    client.on_message = on_message
    client.connect(host or "localhost", port or 1883)
    client.loop_start()
    # The device id in the topics is the controller serial, not its hostname:
    # find it from the output's retained state, which also confirms each switch.
    client.subscribe(f"{args.prefix or topic_prefix + '/+'}/output/{args.output}", qos=1)
    time.sleep(2)
    if not found:
        sys.exit(f"no retained state for {args.output} under {topic_prefix}/+/output/ — check the id or pass --prefix")
    prefix = found[0]
    topic = f"{prefix}/cmd/output/{args.output}/set"
    print(f"switching {topic}")

    def switch(state: str) -> float:
        t = time.time()
        client.publish(topic, state, qos=1).wait_for_publish()
        return t

    out = args.csv or f"relay_emi_{args.output}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    switch("OFF")
    time.sleep(args.period)
    states.clear()
    start = datetime.now().astimezone()
    with open(out, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time", "output", "state"])
        for i in range(args.cycles * 2):
            state = "ON" if i % 2 == 0 else "OFF"
            writer.writerow([f"{switch(state):.6f}", args.output, state])
            fh.flush()
            print(f"\r{i + 1}/{args.cycles * 2} {state} ", end="", flush=True)
            time.sleep(args.period)
    # One more period so the watchdog gets a look after the last OFF.
    time.sleep(max(args.period, 31))
    client.loop_stop()
    print(f"\ntransitions: {out}")
    acked = sum('"ON"' in s or '"OFF"' in s for s in states)
    print(f"state reports from the controller: {acked} of {args.cycles * 2}")

    journal = out.replace(".csv", "_journal.txt")
    cmd = ["journalctl", "-u", "boneio", "-o", "short-iso-precise", "--no-pager",
           "--since", start.strftime("%Y-%m-%d %H:%M:%S")]
    try:
        with open(journal, "w") as fh:
            subprocess.run(cmd, stdout=fh, check=True)
        print(f"journal:     {journal}")
        analyze_files(out, journal, args.window)
    except (OSError, subprocess.CalledProcessError):
        print("could not read the journal as this user; run:\n  sudo " + " ".join(cmd[:-1])
              + f" '{cmd[-1]}' > {journal}")


def parse_journal_time(line: str) -> float | None:
    m = JOURNAL_TS.match(line)
    return datetime.fromisoformat(m.group(1)).timestamp() if m else None


def analyze(toggles: list[tuple[float, str, str]], lines: list[str], window_s: float) -> dict:
    times = [t for t, _, _ in toggles]
    r: dict = {
        "toggles": Counter(s for _, _, s in toggles),
        "mcp_after": Counter(),        # (expander, transition that caused it)
        "mcp_watchdog": Counter(),     # expander
        "edges_after": Counter(),      # (transition, input)
        "edge_delays": defaultdict(Counter),  # transition -> delay bin
        "edges_outside": Counter(),    # input
        "detections": Counter(),       # (transition or "outside", input)
        "stale": Counter(),
    }

    def preceding(t: float, back: int = 0) -> tuple[float, str] | None:
        i = bisect_right(times, t) - 1 - back
        return (times[i], toggles[i][2]) if i >= 0 else None

    for line in lines:
        t = parse_journal_time(line)
        if t is None or not times or t < times[0]:
            continue
        if m := MCP_ON_WRITE.search(line):
            # Logged during the write of the latest transition: the reset
            # happened after the one before it.
            prev = preceding(t, back=1)
            r["mcp_after"][(m.group(1), prev[1] if prev else "?")] += 1
        elif m := MCP_BY_WATCHDOG.search(line):
            r["mcp_watchdog"][m.group(1)] += 1
        elif m := GPIO_EDGE.search(line):
            last = preceding(t)
            delay = t - last[0]
            if delay <= window_s:
                r["edges_after"][(last[1], m.group(2))] += 1
                ms = delay * 1000
                label = next((f"<{b} ms" for b in DELAY_BINS_MS if ms < b), f">={DELAY_BINS_MS[-1]} ms")
                r["edge_delays"][last[1]][label] += 1
            else:
                r["edges_outside"][m.group(2)] += 1
        elif m := DETECTION.search(line):
            last = preceding(t)
            name = m.group(2) or m.group(3)
            r["detections"][(last[1] if t - last[0] <= window_s else "outside", name)] += 1
        elif m := STALE.search(line):
            r["stale"][m.group(1)] += 1
    return r


def report(r: dict, window_s: float) -> None:
    print(f"\ntransitions: ON {r['toggles']['ON']}, OFF {r['toggles']['OFF']}")
    print("expander resets caught on write, by the transition that caused them:")
    for (exp, tr), n in sorted(r["mcp_after"].items()) or [(("-", "-"), 0)]:
        print(f"  {exp} after {tr}: {n}")
    print("expander resets caught only by the watchdog (not attributable):")
    for exp, n in sorted(r["mcp_watchdog"].items()) or [("-", 0)]:
        print(f"  {exp}: {n}")
    print(f"input edges within {window_s:g} s of a transition:")
    for tr in ("ON", "OFF"):
        per_input = {i: n for (t, i), n in r["edges_after"].items() if t == tr}
        print(f"  after {tr}: {sum(per_input.values())}  {dict(r['edge_delays'][tr])}  {per_input}")
    print(f"  outside those windows: {sum(r['edges_outside'].values())}  {dict(r['edges_outside'])}")
    print("clicks/presses the detectors reported (phantoms, if nobody touched a button):")
    for (tr, name), n in sorted(r["detections"].items()) or [(("-", "-"), 0)]:
        print(f"  {'after ' + tr if tr in ('ON', 'OFF') else tr}: {name}: {n}")
    if r["stale"]:
        print(f"stale releases (press with a lost release): {dict(r['stale'])}")


def analyze_files(csv_path: str, journal_path: str, window_s: float) -> None:
    with open(csv_path, newline="") as fh:
        toggles = [(float(row["time"]), row["output"], row["state"]) for row in csv.DictReader(fh)]
    with open(journal_path, encoding="utf-8", errors="replace") as fh:
        report(analyze(toggles, fh.readlines(), window_s), window_s)


def selftest() -> None:
    base = datetime.fromisoformat("2026-11-16T10:00:00+01:00").timestamp()

    def line(dt: float, msg: str) -> str:
        ts = datetime.fromtimestamp(base + dt).astimezone().isoformat(timespec="microseconds")
        return f"{ts} blk boneio[1]: {msg}"

    toggles = [(base + 0, "OUT_04", "ON"), (base + 3, "OUT_04", "OFF"), (base + 6, "OUT_04", "ON")]
    lines = [
        line(3.002, "DEBUG (MainThread) [x] GPIO event: falling edge on IN_10 (P8_46)"),
        line(3.050, "DEBUG (MainThread) [x] GPIO event: rising edge on IN_10 (P8_46)"),
        line(4.500, "DEBUG (MainThread) [x] GPIO event: falling edge on IN_11 (P9_42)"),
        line(6.001, "WARNING (a) [x] MCP23017@0x23 IODIRA reads 0xFF, expected 0x00: ..."),
        line(6.300, "INFO (MainThread) [x] Detected SINGLE click on IN_10 (P8_46)"),
        line(20.0, "WARNING (a) [x] MCP23017@0x24 lost its configuration and stopped ..."),
    ]
    r = analyze(toggles, lines, window_s=1.0)
    assert r["mcp_after"] == Counter({("0x23", "OFF"): 1}), r["mcp_after"]
    assert r["mcp_watchdog"] == Counter({"0x24": 1})
    assert r["edges_after"] == Counter({("OFF", "IN_10"): 2})
    assert r["edge_delays"]["OFF"] == Counter({"<10 ms": 1, "<100 ms": 1})
    assert r["edges_outside"] == Counter({"IN_11": 1})
    assert r["detections"] == Counter({("ON", "IN_10"): 1})
    print("selftest ok")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run", help="switch an output and record the transitions")
    pr.add_argument("output", help="output id as in the config, e.g. OUT_04")
    pr.add_argument("--cycles", type=int, default=200, help="ON+OFF pairs (default 200)")
    pr.add_argument("--period", type=float, default=3.0, help="seconds between transitions")
    pr.add_argument("--prefix", help="device topic prefix, e.g. boneio/blk265f49 (found automatically)")
    pr.add_argument("--config-dir", default="/home/boneio/boneio",
                    help="read broker and account from mqtt.yaml/secrets.yaml here unless --user is given")
    pr.add_argument("--host")
    pr.add_argument("--port", type=int)
    pr.add_argument("--user")
    pr.add_argument("--password")
    pr.add_argument("--csv", help="where to write the transitions")
    pr.add_argument("--window", type=float, default=1.0, help="seconds after a transition that count")
    pa = sub.add_parser("analyze", help="pair journal events with transitions")
    pa.add_argument("csv")
    pa.add_argument("journal", help="journalctl -u boneio -o short-iso-precise output")
    pa.add_argument("--window", type=float, default=1.0)
    sub.add_parser("selftest")
    args = p.parse_args()
    if args.cmd == "run":
        run(args)
    elif args.cmd == "analyze":
        analyze_files(args.csv, args.journal, args.window)
    else:
        selftest()


if __name__ == "__main__":
    sys.exit(main())
