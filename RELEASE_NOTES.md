# v1.5.5

Hotfix on top of `v1.5.4`, for the same field report: clicking an input logged
`Detected SINGLE click` but the output action never ran, until the service was
restarted.

v1.5.4 fixed one half and left the other. The event dispatcher no longer *dies*
on a cancelled listener — but it could still *block* on one forever.

## 🐛 A WebSocket client that stops answering no longer stops the controller

A browser whose host leaves the network does not raise `WebSocketDisconnect`.
The socket stays registered, the send buffer fills, and the write waits for as
long as TCP keeps retrying. The WebSocket broadcast is a global listener for
every event type and is awaited by the single dispatcher task, so that wait
stopped inputs, outputs, covers and sensors alike — while the click detector,
which sits upstream on plain event-loop timers, kept logging clicks that no
longer did anything.

Frames are now bounded at 5s, sent concurrently, and a client that misses the
deadline is dropped. The manager's lock is no longer held across the sends.

## 🔎 A stalled event bus now says so

It was silent twice, which is most of why this took two releases. The
dispatcher records which listener it is awaiting and, past 20s, logs an error
naming it and saying what is stalled behind it. Diagnostics only.

---

# v1.5.4

Hotfix release on top of `v1.5.3`, for the report of inputs that stop responding
— "sometimes" on 1.5.1, "very often" on 1.5.2 — with nothing in the log about
the button press.

The inputs were not at fault, and the input code did not change between 1.5.1
and 1.5.2. A debug capture from an affected controller shows the asyncio event
loop standing still for 40 seconds: every MainThread log line stops, including
the once-per-7s migration status poll, while the Modbus worker threads keep
publishing and their message ids run on. Nothing reads GPIO while the loop is
stopped, so the edges are dropped in the kernel buffer and the detector is left
mid-press. What changed between the two versions was the load on that loop, not
the input handling.

## 🐛 Blocking I2C taken off the event loop

Reading an I2C device is a blocking transfer that first waits for a bus lock
shared with the relay expanders, the OLED and every other device on the bus.
Three call sites did that wait inline in a coroutine, so it was the event loop
that waited — and with it the GPIO reader, every timer and the whole event bus.

- **INA219** reads all of its measurements in a worker thread, in one hop.
- **Temperature sensors** (PCT2075, MCP9808) read in a worker thread.
- **`Cover.stop()`** waits for the movement thread and de-energises both relays
  in a worker thread. `toggle`, `toggle_open` and `toggle_close` all call
  `stop()` first, so an ordinary press of a cover button used to freeze the loop
  for up to half a second — the same press that then went missing.

## 🐛 The event bus no longer dies on a cancelled listener

Every input, output, cover and sensor event is dispatched by a single worker
task. `CancelledError` is a `BaseException`, so a listener raising one passed
straight through the `except Exception` handlers and ended that task — with no
traceback, because a task ending that way counts as merely cancelled, and with
nothing watching or restarting it. From then on the queue filled and nobody
drained it: every input dead at once, nothing in the log, and only a restart
would bring them back.

The websocket broadcast is a global listener for all six event types and raises
exactly this when a browser disconnects mid-send. A cancelled listener is now
contained and logged; cancelling the worker itself still works.

## 🐛 Orphaned long-hold timer chains

A long press runs a self-rescheduling 200ms timer chain, and only the newest
handle is kept. If a release went missing — the edge lost while the loop was
blocked, or swallowed as a bounce — the next press started a second chain while
the first was still running and now unreachable: nothing could cancel it, and
its safety timeout measured against the newer press, so it never tripped. Each
such press added another chain firing LONG five times a second.

- A press now ends any chain still running from the previous one.
- A chain that stops on its own drops its handle, instead of leaving a stale one
  that made the next ordinary short click emit a phantom LONG as well.

## Considered and left alone

The per-write `IODIR` verification in the MCP23017 driver and the expander
health watchdog were both suspects and both cleared. One extra one-byte register
read per relay write is on the order of 100µs of bus time — three orders of
magnitude short of explaining a 40-second stall — and it guards a failure mode
seen in the field, so it stays as it is.

---

# v1.5.3

Hotfix release on top of `v1.5.2`. Two input-configuration bugs reported from the
field, plus three more found in the same code while fixing them.

## 🐛 Bug Fixes — input settings that needed an application restart

Flipping **Inverted** on a binary sensor saved the value and reloaded the config,
but the input kept reporting the old polarity until the service was restarted.
The reload itself always ran; it just updated only actions, name, area and
device_class on the running input, leaving everything baked into the GPIO
detector at construction on its old value.

- **`inverted` applied live** — `update_inverted()` swaps the sensor's click
  types, re-reads the pin and re-anchors the detector, so no restart is needed.
- **First edge no longer swallowed** — the detector's cached state and pending
  debounce window belonged to the old polarity and are now reset with it.
- **State republished immediately** — after a flip the reported state is the
  opposite one, so MQTT, Home Assistant and the WebUI hear about it at once.
- **`bounce_time` applied live too**, on binary sensors and event inputs.

`gpio_mode` is untouched — deprecated, ignored at runtime, never set from the UI.

## 🐛 Bug Fixes — time values lost on the hot-reload path

Time fields reach an input as `TimePeriod` at startup, because the schema
coerces them. The hot reload skips that validation for speed, so the same fields
arrive as a bare number of milliseconds or a string like `"300ms"` — and the
code that read them only understood `TimePeriod`.

- **Custom click timings survive a reload** — `double_click_duration`,
  `long_press_duration`, `sequence_window_duration` and
  `max_long_press_duration` used to snap back to 220/400/500 ms and 120 s on
  every reload, silently.
- **Adding an input cannot abort the reload** — the constructor called
  `.total_in_seconds` on the raw value, raising `AttributeError` past the only
  handler in that path.
- **`bounce_time` resolves consistently**, falling back to the schema default
  for its input type when the key is absent.

## 🐛 Bug Fixes — binary sensors offered the wrong device classes

The **Device class** list in Settings → Inputs held only Button / Doorbell /
Motion — the Home Assistant *event* classes — whatever the input type.

- **Each form gets its own schema** — the merged `local_inputs` section was built
  on the event schema, which is not a superset of binary_sensor. It now carries
  both item schemas, and binary sensors get door, window, opening, moisture,
  smoke, gas, occupancy, vibration, tamper and the rest.
- **Also fixed by the same change** — the pressed/released action types and the
  binary-sensor `bounce_time` default now come from the schema.

Backend schemas were already correct; no config.yaml change is needed.

---

# v1.5.2

Hotfix release branched from `v1.5.1`. Carries the bug fixes and performance work
that had accumulated on `dev-debian13`, minus the 1.6.0 feature work.

## 🐛 Bug Fixes — relay outputs stop switching until restart

Reported on a Black 32x10A: after 12-48 hours, a whole MCP23017 port stopped
driving relays. WebUI showed states changing, no errors in the log, and
`systemctl restart boneio` restored everything.

- **MCP23017 watchdog** — re-checks `IOCON`/`IODIR` every 30 s, detects a
  silently reset expander and reconfigures it, restoring latches before
  re-enabling drivers so relays go straight to the last commanded state.
- **`IOCON` bank-safe init** — zeroes register `0x05` first so `BANK=0` is
  guaranteed regardless of the chip's current state.
- **Writes from cache, not hardware latch** — `_write_pin` no longer reads
  `OLAT` (which is stale after a reset); it uses the driver's cache and only
  reads the hardware to detect divergence.
- **Cold-boot safe level derived from polarity** — active-HIGH boards no longer
  briefly latch `0xFF` during init.

## 🐛 Bug Fixes — covers silently immobile

- Covers with `open_time`/`close_time` = 0 now log an ERROR at startup and on
  every movement attempt instead of silently ignoring commands.

## 🐛 Bug Fixes — hostname out of sync with MQTT serial

- `set-hostname-once.sh` now reads MAC from the live NIC (`end0` on Debian 13)
  instead of hardcoded `eth0`.

## 🐛 Other Bug Fixes

- **WebUI**: `delay`/`delay_cancel_on` and `restore_tilt` no longer stripped on
  action save round-trip.
- **Overlay**: detect and repair the path U-Boot actually reads; kernel postinst
  hook copies `.dtbo` to `/boot/dtbs/$K/`.
- **Node-RED**: Docker Hub tag fetch no longer freezes the event loop.
- **GitHub update check**: non-blocking (`asyncio.to_thread`).
- **Irrigation**: fixed control logic.
- **Wanas 415**: register type `input` → `holding` (FC 0x04 → FC 0x03).
- **Frontend**: cancel long-press on touch scroll; LogViewer auto-scroll pauses
  during text selection; WLED cache enrichment preserved on save.

## ⚡ Performance — boot & login

- Boot time reduced by deferring non-critical services, disabling keyboard/console
  setup, shrinking journal preallocation, and taking the OLED splash off the
  critical path.
- SSH login time: **6.9 s → 2.7 s** (user lingering enabled).
- Mosquitto gets boneIO's CPU/IO priority.

## 📦 CI

- Test workflow installs full project dependencies (fixes fastapi/httpx collection errors).
