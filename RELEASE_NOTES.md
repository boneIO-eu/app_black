# ⛔ DO NOT INSTALL THIS VERSION ⛔

**This is a non-working beta. Please do not use this version.**

`1.6.0.dev2` exists so that we can test the new system-migration chain on a
development controller. It has **not** been run end to end on real hardware even
once. It changes how boneIO obtains root privileges, installs new system
helpers, rewrites sudo rules and takes ownership of `docker-compose.yaml` — on a
device in production, a mistake in any of that means a controller that needs
physical access to repair.

- **Do not install it on a controller you depend on.**
- **Do not install it on a device you cannot reach with a console or an SD card
  reader.**
- If your panel offers it as an update, **skip it.** It is marked as a
  pre-release and is not offered automatically; you would have to select it by
  hand.

Stay on the latest stable release. A version of this work that is meant for you
will be announced as such, and it will not look like this notice.

---

# v1.6.0.dev2 — internal test build

## What this build is for

Everything below is about closing CVE-2026-77055 (privilege assignment) and the
sudo-password paths reported alongside it. The mechanism is new and the point of
this build is to find out how it behaves on a real 1.5.x controller that is
upgraded in place.

## What changed

**Migration plans are signed.** A privileged helper used to accept a complete
migration plan over stdin from the unprivileged application — the actions, the
asset digests, and a `validate_cmd` string it ran as root. Plans are now frozen
at release time and signed with an Ed25519 key; the helper accepts a version
string and verifies everything else against a key pinned outside the
application's reach.

**Two trust anchors, not one.** Re-pinning a signing key needs a migration
signed by a key the device already trusts. With a single anchor, a lost release
key would mean a controller that keeps running but can never accept a signed
migration again. A second, offline recovery anchor ships alongside the release
one and may only authorise re-pinning.

**Named operations instead of wildcards.** Container management, CAN interface
setup, the device-tree overlay, the timezone rule and the hostname each went
through a wildcard sudo rule or an endpoint that asked for the operator's system
password. They now go through three helpers with closed vocabularies:
`boneio-migrate-v2`, `boneio-containers`, `boneio-system`.

**No endpoint collects a sudo password any more**, except the one-time bootstrap
on a device that has no helper at all — there is nothing else to elevate with
there. Two of the removed ones were actively harmful: one wrote a sudoers file
using the password, and one chowned `docker-compose.yaml` back to the logged-in
user, which undoes the hardening on request.

**The compose file belongs to root.** `docker compose up` executes that file, so
being able to write it is being able to run a container as root with the host
filesystem mounted — routing the commands through a helper would have achieved
nothing on its own.

## What is deliberately not done yet

- The `boneio` account is still in the `docker` group, and still has
  `(ALL : ALL) ALL` through the `admin` group inherited from the stock
  BeagleBone image. Removing those is the last step and comes after this build
  has been verified on hardware — it is also the step that takes away the
  operator's own way back in over SSH.
- `mosquitto_passwd` still receives a new password as a command-line argument,
  where `ps` can see it.
- Fresh images do not yet ship the helpers preinstalled, so an upgraded device
  installs them through the migration chain. That path is exactly what this
  build is meant to exercise.

## For the record

A device compromised **before** this update is not fixed by it. An attacker who
already holds root can replace the pinned keys locally, and no in-place update
can bootstrap trust on a machine that is already owned.

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
