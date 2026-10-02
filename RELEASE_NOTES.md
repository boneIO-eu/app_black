# boneIO Black 1.6 — open for testing on real installations

`1.6.0.dev30` is a 1.6 build we consider ready to run on controllers in
real installations, for owners who want to help test it before 1.6 is final.
It is still a pre-release: the panel does not offer it automatically, you
have to pick it by hand. If you just want a controller that works, stay on
**1.5.6**.

## Before you update

- **Update to 1.5.6 first.** Only 1.5.6 knows how to hand the browser over to
  the new panel cleanly; from older versions the old panel may keep coming
  back after the update until you press Ctrl+Shift+R.
- **Be able to reach the controller physically**: an SD card reader or a
  serial console. This update changes how boneIO gets administrator rights on
  the system (see below). It has been run on our own controllers, but a
  mistake here is the kind that needs hands on the device to repair.
- **Keep a copy of your configuration** (the `/home/boneio/boneio` folder).
- Let the update finish. System migrations run at startup and can take
  several minutes; the display and the panel say so. Do not cut the power
  while they do.

## What 1.6 changes on the device

1.6 is the work of adapting boneIO Black to the EU Cyber Resilience Act. It is
not a declaration of conformity; it is the engineering that has to exist
before one can be made.

- **No standing path to root.** Privileged work goes through three small
  system helpers with a fixed list of operations. Wildcard sudo rules are
  gone, and the `boneio` account is no longer in the `docker` group.
- **Signed updates.** System migrations are signed when a release is made and
  checked on the controller before anything runs as root.
- **Logins and sessions.** The panel requires an administrator account
  (created in the first-run wizard). Changing a password signs out that
  account's other sessions, repeated wrong passwords are throttled, and so
  are the alarm's PIN codes.
- **SSH.** New images ship without a known SSH password. You can set or change
  the SSH password from the Accounts page.
- **MQTT password** moves out of `mqtt.yaml` into `secrets.yaml`, and saving
  the MQTT page no longer writes it back in the open.
- **MQTT over TLS**, in both directions: boneIO connecting out to a broker,
  and the controller's own Mosquitto broker taking encrypted connections in.
- **Operating-system updates from the panel.**

## New features and fixes

- First-run wizard for new and freshly reset controllers.
- Schedules and sun-driven actions, and virtual switches that can run actions.
- New navigation: a bottom bar on phones and tablets.
- Hardware revision 1.1 supported end to end.
- CAN comes up correctly.
- Faster startup, and the controller survives a power cut better.
- **Home Assistant:** entities assigned to a room stay under that room's
  device (e.g. "Black - Salon") and are no longer moved to the main device
  after startup. Covers keep their type (`shutter` no longer turns into a
  window), and entities with `show_in_ha: false` stay out of HA. Updating
  does not create duplicate entities.
- **System updates** on controllers with a small eMMC no longer stop at "not
  enough space" because of packages apt downloaded earlier, and a finished
  update now says so.
- GPIO binary sensors publish their state as retained, so HA knows it right
  after a restart.
- **Home Assistant, again:** saving a section (inputs, outputs, covers) no
  longer removes entities it does not own from Home Assistant — security
  events, virtual switches, irrigation, remote outputs and more could
  disappear or stop updating on a save.
- v0.2/v0.3 boards: `IN_26`, `IN_27` and `IN_28` work again.

The full list, build by build, is in [CHANGELOG.md](CHANGELOG.md).

## Known limitations

- The `boneio` account keeps full sudo through the `admin` group of the stock
  BeagleBone image, behind the account password. It is the owner's own way to
  a root shell; removing it would leave only the SD card or a serial console
  for repairs.
- A controller that was compromised before this update is not fixed by it.

## Found a problem?

Please report it with the version you updated from, what you saw, and — if
you can — the output of `journalctl -u boneio -b`.

---

# v1.6.0.dev30 — internal test build

## Since dev29

Node-RED's editor came up open on a controller flashed from the dev29
image: `GET /nodered/flows` answered with no token, and a flow with an exec
node is code execution. The image's rootfs had run migration 1.6.0, which
installs `settings.js` with `adminAuth`, before a later build step wrote a
four-line stub back over it — the migration itself never reran, so the file
stayed wrong on anything built from that rootfs. Migration 1.6.34 installs
the right `settings.js` again; where it already matches, the helper finds
the hash already correct. That alone would not fix a controller already
running, since an update restarts boneIO, not the controller, and Node-RED
keeps whatever settings it started with — `boneio.core.nodered_guard` now
asks the running editor, a minute after start, how it signs people in, and
restarts it once if it answers with no login while the file on disk asks
for one. No answer, because Node-RED is off, still starting, or its proxy
is being recreated, is retried for ten minutes and never triggers a restart
on its own.

Every controller flashed from the dev27–dev29 images also carried the same
token secret: those images are built on a rootfs that had already run
boneIO once, sealing does not remove the secret file, and it was reused as
found, so anyone holding the image could sign an administrator's token for
any device made from it. The secret file now carries a hash of the
machine's own `/etc/machine-id` alongside it; a secret with no binding, or
bound to another machine, is replaced on start. `machine-id` is itself
emptied when an image is sealed and drawn fresh on first boot, so a secret
made while building the image is replaced there too. Every session is
signed out once, on the first start of this version, since no secret from
before carries the binding yet.

Two smaller panel-hardening fixes: the Content-Security-Policy no longer
allows `'unsafe-eval'`, which nothing in the panel's own code needs; and
`/docs`, `/redoc` and `/openapi.json`, which only serve outside of
developer mode, now answer 404 instead of the SPA's catch-all handing back
the panel itself with a 200.

The PWA/HTTPS switch is steadier. Turning registration on used to run
`compose up` and then `compose restart` on Caddy — `up` already recreates
the container from the new template, so the restart only took the reverse
proxy down a second time, the only way into the panel once it is moved
behind it. A template swap now runs `up` alone. `GET /api/cloud/status`
gains `serving` and `url`: the existing `cloud_config_active` turned true
as soon as the template was copied, half a minute before Caddy actually
answered on it, so it was no signal for when to send the owner to the new
address. The onboarding wizard's PWA step now follows that status instead
of reloading straight into "the controller is not answering" while Caddy
restarts — it offers "Go to `<name>`" once the browser itself can reach
that address, never a name a DNS-rebinding router would refuse to resolve,
and says to sign in again there, since another origin keeps its own
storage. Past three minutes it says so and shows the backend's own error;
a name that never answers can still be opened anyway. The availability
screen no longer replaces an open wizard either — a failed `/api/init`
poll during the restart used to swap the wizard for that screen,
unmounting it and losing everything it knew. Separately, Settings shows
the restart banner again when a save needs one: `GET /api/status/restart`
had been reading `restart_pending` off an attribute nothing ever set, so
the banner was always false on reopening the page.

Checked: on 192.168.50.220 — the image's stub `settings.js` in place,
Node-RED restarted on it (`auth/login` answered `{}`, `flows` 200); after
deploying, 1.6.34 applied, the guard restarted Node-RED a minute later, and
`auth/login` asked for credentials, `flows` 401. Backend suite 4274
passed. The CSP change was checked on .220 in a browser — the login page
and the Monaco chunk load with no violation, and a string evaluated from
page script is refused; the YAML editor itself was not opened under the
new header, no account being set up there. The token-secret fix has eight
new tests; the image side, removing the secret file when sealing, is a
separate change in black_debian_images, not this one. The cloud/PWA and
restart-banner fixes are `tsc -b` clean, eslint clean, frontend suite
636/636 (seven new); the onboarding flow itself has not yet been run
through on a controller being onboarded.

Migration 1.6.34 is new, and the manifest is re-signed since it names the
release; no other plan changed since dev29.

---

# v1.6.0.dev29 — internal test build

## Since dev28

Seen on a fresh controller during onboarding: turning the PWA on left
`web: {cloud: {enabled: true}}` behind. `expose: proxy`, the ports and
`security` were gone, the panel kept listening off the LAN only until the
next start, and the save asked for a restart — correctly, since to the
backend more than `cloud` had changed. "Move the panel behind the proxy" on
the security page did the opposite: it saved `{expose: proxy}` alone, which
dropped `cloud`, read by the backend as the PWA switched off, so
registration stopped and the local Caddy template came back.

The cause was the same in both places: `PUT /api/config/web` replaces the
whole section, and each caller merged the one setting it cares about into
the section read from the wrong level of `GET /api/config`'s answer —
`config.web` instead of `config.config.web`. Reading nothing meant the
merge started from nothing, so the save kept only the caller's own key.

Both now go through a shared `updateWebSection()` helper that reads the
stored section from under `config` and saves the merged result.

Checked: `tsc -b` clean, eslint clean, frontend suite 629/629 (four new).
Seen on blk239bb2; not yet tried end to end on a controller's own panel
after this fix.

No migration of its own, and no plan changed since dev28 — only the
manifest is re-signed, since it names the release.

---

# v1.6.0.dev28 — internal test build

## Since dev27

Reported by a user: a controller a year behind, with well over a hundred
packages to bring in, had 300 MB free — the panel's own minimum — and still
ended an update in `dist-upgrade failed (rc=100)`, with `/` filled to zero.
The check ran before `apt-get update`, against a flat 300 MB that took no
account of how much a given upgrade would actually download and unpack, and
`autoremove`/`clean` ran only on success, so the downloads that caused the
failure stayed on disk for the next attempt. `boneio-system` now runs
`apt-get --assume-no dist-upgrade` after `update` and reads apt's own
figures for what is still to download and how much the installed packages
grow by, and requires that total plus a 100 MB margin for the new kernel's
initramfs and dpkg's working copies — never less than the old 300 MB; the
refusal states the figures. The apt cache is cleared before every upgrade
and after a failed one, `dpkg --configure -a` runs before the gate so a
device a failed run left full can be repaired from the panel, and the
OS-update card now warns against the figure the check actually measured
instead of a fixed minimum. Migration 1.6.33 reinstalls `boneio-system`.

A virtual switch normally has no `id` of its own — the identifier is made
from its name — and the panel's own form for adding one has no id field, so
this affected every switch added from the panel. The action picker on an
input, the condition picker, and the action summary all read `vs.id`
directly and dropped anything without one, so a freshly added switch simply
did not appear in either list; the "no virtual switches" message did not
show either, because the list itself was not empty. Both pickers and the
summary now resolve the id the way the switch's own form and the backend
already do, and the summary shows the switch's name instead of its id.
Reported by a user.

Checked: `boneio-system`'s own test suite, 166/166. The apt-output parser
against real apt output captured on 192.168.50.220 (44.4 MB / 59.0 MB → 43 /
57 MiB); a full upgrade on a small eMMC has not been reproduced, since .220
has 25 GB free. The virtual-switch fix is checked with `tsc -b` and the
frontend test suite (625/625, one of them new); neither fix has been tried
on a controller's own panel yet.

Migration 1.6.33 is new. Its plan, and the plans of every earlier migration
that installs `boneio-system` — 1.6.5, 1.6.8, 1.6.9, 1.6.17, 1.6.18, 1.6.22,
1.6.26, 1.6.27, 1.6.29, 1.6.30, 1.6.31 and 1.6.32 — are re-signed, since the
helper's content, and so its hash, changed. The manifest is re-signed too,
as it is every release.

---

# v1.6.0.dev27 — internal test build

## Since dev26

"Messaging Protocols" was one settings entry with two tabs behind it, so
saving, restoring and the unsaved-changes dot all had to treat MQTT and
Loxone (UDP) as one section — and a Loxone host the panel did not like
blocked saving the MQTT broker underneath it, even though the two have
nothing to do with each other. They are now two entries under Connections,
MQTT and Loxone (UDP), each with its own form, save, description and
restart badge; saving one no longer touches the other. This also makes room
for what comes next in that group: a Home Assistant entry once boneIO can
talk to it without MQTT.

Checked with `tsc -b` and the frontend test suite (624/624, six of them
new); not tried on a controller in a browser yet.

No new migrations this release, and no plan changed since dev26. Only the
manifest is re-signed, since it names the release.

---

# v1.6.0.dev26 — internal test build

## Since dev25

A broker can now require TLS, and boneIO can speak it on both sides.
Connecting out, a new `mqtt.tls` section checks the broker's certificate
against the system's trusted authorities or your own CA, with an optional
client certificate; turning it on and failing to set up means no connection
at all, never a silent fall-back to a plain one — the broker password
travels in the CONNECT packet. Taking connections in, the Mosquitto page
gets a Broker encryption card: make a ten-year certificate here or upload
your own, and choose plain, TLS alongside plain, or TLS only from the
network — boneIO itself keeps a plain loopback connection so it cannot lock
itself out, and Node-RED on the controller reaches the broker through
`host.docker.internal`, from Docker's network rather than localhost, so its
own broker node needs moving to 8883 as well if the mode goes TLS-only.
Changes go through `boneio-system` and roll back automatically if the
broker does not come back up on the new settings. Migration 1.6.32 installs
the updated helper and opens 8883 in the firewall. See `docs/MQTT_TLS.md`
for both directions and an openssl recipe for the certificates.

Ten fixes close the same family of bug: saving one section of the
configuration — inputs, outputs, covers — rebuilds its own discovery
entries and, in doing so, could silently remove or stop updating entities
it does not own. Saving inputs no longer wipes event and binary_sensor
entities (security events, the security alert, the OLED button) out of
Home Assistant; saving outputs or covers no longer removes schedules,
virtual switches, irrigation, modbus switches, remote outputs, output
groups, remote covers or gate covers. Covers, irrigation, thermostats, gate
covers, alarm panels and virtual energy sensors now follow the new output
objects an output reload creates instead of going on watching ones nobody
updates any more; remote outputs survive an output reload as the same
objects. A Modbus device that has not answered yet is no longer dropped
from Home Assistant as unused. Entities that register a while after startup
— security, updates, irrigation, remote inputs — are no longer caught by
the discovery-replay race at startup and removed moments after they appear.

v0.2 and v0.3 boards get a corrected pin overlay: P9_11, P9_12 and P9_13
work as inputs `IN_26`, `IN_27` and `IN_28` again, instead of being claimed
by 1-Wire and a UART4 these boards do not have. Migration 1.6.31 installs
it and reinstalls `boneio-system`; the startup check now asks for a repair
whenever an installed overlay copy differs from the shipped one, not only
when it is missing outright.

Smaller things: the security page and the SSH login card no longer wait on
a slow sudo check on every open — both are kept warm and refreshed in the
background. Outputs and inputs can be grouped by area on the dashboard.
Frontend assets are gzipped once at build time instead of on the
BeagleBone's CPU on every request. A number of webui rough edges — ghost
buttons that did not look clickable, a bounce-time field with no limit, a
Save button that did not span its card — are fixed.

No migrations beyond 1.6.31 and 1.6.32 above; the plans that install
`boneio-system` carry its new hash and are re-signed with it (1.6.5, 1.6.8,
1.6.9, 1.6.17, 1.6.18, 1.6.22, 1.6.26, 1.6.27, 1.6.29, 1.6.30, plus the new
1.6.31 and 1.6.32).

Checked on 192.168.50.220: MQTT over TLS, including the broker's own TLS
mode and migration 1.6.32. The discovery/reload fixes too, read off Home
Assistant's `online` status and what the discovery cache held before and
after each reload: an input reload went from 0 to 50 event/binary_sensor
entries kept instead of wiped; an output or cover reload stopped dropping
other entity types (switch 8→0, valve 7→4, cover 4→2 before the fix,
unchanged after); a remote output stayed reachable after an output reload;
`OUT_02`'s energy sensor resumed counting after a reload (0 → +0.5 Wh/min);
the startup discovery race, an offline Modbus device and irrigation were
checked on the same controller by a second session. Migration 1.6.31 (the
v0.2/v0.3 overlay) has not been tried on a controller yet.

A system update no longer stops at "not enough space" because of apt's own
downloads. On a controller with a small eMMC the panel refused with 277 MB
free and 300 MB needed, and 144 MB of that was packages apt had downloaded
earlier and keeps until an upgrade succeeds. When short of room, the update
now clears that cache first and checks again; the panel offers the update in
that case and says it will clear the cache.

Two things the card said at the wrong moment are fixed: the space warning
and "restart required" no longer show while an update is running. When an
update finishes, the card now says so in green, with the number of updated
packages and a reminder to restart when one is due.

Migration 1.6.30 installs the new `boneio-system`; the plans that install
the helper are re-signed with it.

---

# v1.6.0.dev25 — internal test build

## Since dev24

Brings 1.5.6's Home Assistant fix onto this line. Field report on 1.5.5/1.5.6:
HA first created a room device such as "Black - Salon" with the room's
entities in it, then moved them to the main "Black" device, and a cover set
to `shutter` in boneIO ended up as a plain window. A dump from .220 on dev23
showed the same fault on 1.6: an output group called "Gabinetowe" with no
room.

Setup publishes the right discovery payload. Right after it, the startup
resend rebuilds every payload straight from the entity objects and replaces
the cached copy that is replayed whenever Home Assistant comes back online.
The entity objects did not keep everything setup had read from the
config: covers lost their area and `device_class`; output groups, Dallas
and ADC sensors lost their area; and inputs, Dallas and ADC sensors with `show_in_ha: false`, plus
remote outputs (`show_in_ha` defaults to false there), were published to HA
regardless. Area and `show_in_ha` now live on the entity itself, set at
creation and kept on reload, and the resend honours both.

`unique_id` does not depend on the area, so the restart after the update
should put entities back under their room device without HA creating
duplicate entities. Checked on a controller on 1.5.6 (config from
1.6, both device naming modes), reading the retained discovery payloads
after startup: without the fix a cover with `area: living_room` and
`device_class: shutter` ended under the main device with no class; with it,
under the room device as a shutter — the same for a venetian cover, an
output group and an ADC sensor. The only other difference was two entities
no longer published: the internal OLED button and a remote output without
`show_in_ha`. Not tried against a real HA instance yet on this line.

No new migrations this release, and no plan changed since dev24. Only the
manifest is re-signed, since it names the release.

---

# v1.6.0.dev24 — internal test build

## Since dev23

Since 1.6.17 the first-run wizard has copied the owner's first panel password
onto the `boneio` SSH login, once. After that the two passwords were
separate, and the only way to change the SSH one was `passwd` over SSH. The
Accounts page now gets an "SSH login password" card that can do it from the
panel: `boneio-system` gains a `service-password-change` verb — the current
password checked against `/etc/shadow`, nothing changes without it — and
migration 1.6.29 installs it. A locked or empty login is refused: those are
`service-password-init`'s states to set from, once, and here they would be a
way to set a password without knowing one; a lost password is still
recovered with the flasher card (`BONEIO_RESET_ACCOUNTS=1`). Wrong tries are
counted globally, five in fifteen minutes with two seconds' penalty each,
and a wrong current password from the panel behaves like a wrong panel
password: 403 `current_password_wrong` with tries left, counted against the
same session budget, and — only when a throttle window fills, not on every
refused try — reported to Home Assistant as one `password_guessing` event.
The card explains itself instead of offering a broken form when it can't help —
locked, empty, or a controller that hasn't applied 1.6.29 yet — and the
security check for a shipped SSH password now sends you here instead of
only to `passwd`.

The rest of the Accounts page moved off `window.prompt`/`window.confirm`
onto proper dialogs, with the password checked as you type and, for your
own account, a wrong current password now an inline error instead of a
sign-out; and the account list wraps into rows that fit a phone instead of
scrolling sideways.

An SSH login has been showing BeagleBoard's base-image banner and its build
date — months stale on a controller that has since taken every point
release and security update — before the password prompt and on every
non-interactive `ssh` command. Migration 1.6.28 replaces it with boneIO's
own two-line banner before login, and, after login, a dynamic MOTD showing
boneIO's version and state, the panel's address, the Debian point release
and kernel, when dpkg last changed anything, and the base image, labelled as
what it is rather than as the system's age. The base images shipped
`update-motd.d` without execute bits, so nothing dynamic had ever shown
there before this.

Outside the security work: GPIO binary sensor states now publish retained,
so a tank float switch or any other input that can sit still for weeks
reads correctly in Home Assistant right after an HA restart instead of
`unknown` until it next moves; every MQTT connect re-reads and republishes
each sensor's pin once the GPIO manager is up. A remote MQTT input now
recognises a retained replay on reconnect and no longer runs a phantom
action from it, which also fixes inputs mirroring a retained source such as
ESPHome. Click events are deliberately left unretained. One known leftover:
deleting an input or switching it to event mode leaves its last retained
state on the broker, though peers and HA's event entity ignore it. Reported
in #70. And the update list now asks GitHub for 100 releases instead of the
default 30, so a stable release doesn't fall off the page behind a run of
dev builds.

Migrations 1.6.28 and 1.6.29 are new this release. `boneio-system`'s hash is
part of every plan that installs it, so 1.6.5, 1.6.8, 1.6.9, 1.6.17, 1.6.18,
1.6.22, 1.6.26 and 1.6.27 are re-signed alongside 1.6.29. The manifest is
re-signed too, since it names the release.

---

# v1.6.0.dev23 — internal test build

## Since dev22

A stolen or shared login token used to work for the full 30 days no matter
what happened to the account afterwards. Changing a password now bumps a
session version kept in `users.json`; every token issued before that change
stops working at once with 401 `session_revoked` — on the API, on
`/api/init` and `/api/version`, and on the WebSocket, which until now never
even checked the account still existed. The session that made the change is
not caught by this: it gets a fresh token immediately, whether it changed
its own password or an admin reset it from the accounts page. Accounts and
tokens from before this upgrade read as session version 0, so upgrading
itself signs nobody out.

Two more limits land on top of that. First, a session that keeps typing the
wrong password — at the login form, a password prompt, or the own-password
form — is signed out on the fifth try, with 401 `session_locked`; the count
is cumulative, survives a restart and only the right password clears it,
while the account's other devices are untouched. Second, beyond the 30-day
token there is now a 10-minute one: creating, deleting or changing an
account's role or password; importing a config archive, restoring a backup,
a full or partial factory reset, restoring Node-RED flows; an application
update or rollback, a system upgrade, switching automatic security updates,
updating Caddy; uploading or removing the panel's certificate — all of these
now ask for the password again if it wasn't typed in the last 10 minutes. A
stale token gets 403 `reauth_required`, the panel raises one password
dialog regardless of how many requests were refused at once, and a correct
password retries them through the new `POST /api/auth/confirm`. Restart,
reboot, the file editor and section saves are deliberately left alone — a
password on every save just trains people to type it without reading. The
first-run wizard's own import is exempt (its token is new), and a device
still on a legacy `web.auth` pair is never asked, having no account to
check against.

Behind Caddy, every proxied login used to arrive from the same Docker-bridge
address, so the per-IP throttle lumped an entire household into one bucket
and the logs never named the real caller. `X-Forwarded-For` is now trusted
only when the connection itself comes from loopback or a Docker bridge on
this controller — never from the LAN, where trusting it would let a guesser
pick a fresh address on every attempt — and failed logins now log the real
client. A new diagnostic entity, "Security events", also reports
password-guessing and forced sign-outs to Home Assistant over MQTT
(`boneio/security/event`, not retained), once per throttle filling rather
than per refused attempt; emitting never raises, so a device without MQTT
still signs people in.

Two smaller fixes round this release out: the OS-update card no longer
freezes or claims a run has finished the moment `systemctl` itself becomes
unreadable while dpkg replaces `systemd` mid-upgrade, and its log now folds
away under "Last run log" once a run has gone well instead of sitting open
next to the tile showing the new kernel.

None of this needs a config migration: `users.json` gains
`session_version`, `revoked_sessions` and `session_failures`, and a missing
field reads as zero or empty on an account that predates the upgrade.

Verified on the dev controller (192.168.50.220, boneIO Black 32x10A): the
device harness (45/45) and the on-device pytest suite (355/355) pass against
the production service restarted on this code; a login through Caddy on
8443 reports the real client address, and a spoofed `X-Forwarded-For` sent
from the LAN is ignored; a run of wrong passwords produces exactly one
`password_guessing` event. Not yet checked: that the event actually reaches
Home Assistant — no MQTT subscriber was used to confirm delivery — and a
manual run of the password prompt on the production panel, which was still
under way at the time of this build.

No new system migration this release, and no migration plan's content
changed. Only the manifest is re-signed, since it names the release.

---

# v1.6.0.dev22 — internal test build

## Since dev21

The first-run wizard now uses the same shell as the login screen it hands
over to: edge to edge on a phone, a card on the app's tinted field from `sm`
up, theme and language pickers top right, the device name under the
heading. A segmented progress bar replaces the numbered daisyUI steps,
fitting a 320px phone at any step count, and each step opens with a heading
and intro the way a settings card does; solid alerts become the settings
notices, at the same severities. The card floor is re-measured for the new
steps — 36rem from `sm` up, less on a short screen so a 768px laptop still
shows the buttons — and on a phone the buttons sit at the bottom; the theme
and language pickers scroll with the page, since several steps run taller
than a phone. The welcome step now lists what's ahead, import is a drop
zone that names the chosen file, input modes are radio cards,
restore-state is a toggle row, and the finish step leads with "the
controller has an owner". Purely visual: the onboarding logic and the API
it drives are unchanged.

No new system migration this release, and no migration plan's content
changed. Only the manifest is re-signed, since it names the release.

---

# v1.6.0.dev21 — internal test build

## Since dev20

The on-board power monitor stalled the whole controller during a poll and
could misreport a board's voltage. Reading the INA226 is a blocking I2C
transfer behind the bus lock; `async_update` did it inline, so a relay write
holding the lock stalled every timer, the GPIO reader and the event bus until
it let go. The INA219 already read in a worker thread; the INA226 — every
v1.x board — now does the same. Separately, an INA219 wired at the address an
`ina226:` config expects showed 40 V on a 24 V supply instead of failing: the
driver now reads the manufacturer ID before writing anything and refuses the
mismatch, telling the user to switch to `ina219:` and power-cycle the board.
And a new `POST /api/sensors/ina/refresh` reads the sensor on the spot, for
the factory tester, which needs the coil current within a second or two and
was instead seeing whatever the last scheduled poll saw — up to
`update_interval` (60 s by default) old, a delta of exactly 0.0 mA on a good
board. Not checked on hardware.

CAN comes up for the first time since the SDO feature landed. `connect()`
called a canopen-asyncio method that library has never had, so every start
raised and CAN never came up at all — no heartbeat, no discovery, no
CAN-MQTT bridge. Tested on 192.168.50.220: "CANopen manager started". A
configuration pushed over CAN, which an earlier release validated and
applied, is now refused outright (SDO abort `0x08000020`): nothing
authenticates the sender yet, so any node on the bus could replace
`config.yaml`, and it stays refused until signed payloads land. And a bus
with nothing else on it, or no termination, no longer restarts every 4
seconds forever: restarts now back off from 2 s up to 5 min, measured on the
same controller.

The panel is better at telling "an update is running" from "something
broke". Going from 1.5 to 1.6 used to show old settings pages several times
before the wizard appeared, because the service worker answered every
navigation from its precache while the new build downloaded; the build now
carries its own version, and the panel drops its service worker registration
and reloads once when the server reports a different one, marking an update
as running rather than showing "API unavailable". A short missed poll
mid-update no longer reads as a failed update (the restart window is now
15 s), and a build replaced mid-load reloads once instead of leaving a blank
page.

Two smaller fixes: the first-run wizard no longer offers to turn cloud
registration on for a device that already has it (it now reads
`cloud.enabled` from `/api/init` instead of asking), and the "Check for
system updates" button now shows "Starting…" immediately instead of sitting
unchanged for several seconds, while the OS-update helper's supported verbs
are cached per install instead of being re-asked on every request.

No new system migration this release, and no migration plan's content
changed. Only the manifest is re-signed, since it names the release.

---

# v1.6.0.dev20 — internal test build

## Since dev19

Two things change for anyone who has already updated a controller.

The kernel check stopped telling owners of an early, never-upgraded image
(kernel `6.18.2-bone12`) that something was critical and to call support
without restarting. That controller keeps its boneIO overlay only under
`/boot/dtbs/$uname_r/overlays/` and loads it from there by full path, the
way the old UPGRADE.md set it up — a layout the check did not know about. It
now follows the same `uboot_overlay_addrN` entries U-Boot itself reads, so a
copy in the boot kernel's own directory counts, and a missing file is no
longer reported as critical when this boot is provably the same one that
just started. Clearing the false alarm needs migration 1.6.26 to have run,
not just the updated code. Checked read-only on the dev controller
(192.168.50.220, kernel `6.18.53-bone55`, overlay entered by bare name,
overlay active): status `ok`, and the "next boot is this boot" guard
returned `True`. Not checked on an actual `6.18.2-bone12` image.

The screen no longer looks like it has hung during an update. System
migrations run at startup, after the display has taken over and before the
web server answers, and can take minutes on a controller several releases
behind. Until now the OLED (or the early boot screen, on boards without one)
just sat on the host and version, unresponsive, exactly when someone worried
about a stuck controller would be tempted to pull the plug. It now shows
"Updating, do not power off", the share done and which migration is running,
and comes down once migrations finish — including this update's own 1.6.26
and 1.6.27. Not checked on hardware.

Alongside those, the startup check that restores a missing boot overlay
works again — it has silently done nothing since 1.6.6, because the helper
it piped a plan to was removed that release, and only logged "boneio-migrate
helper not installed" (migration 1.6.27). Not checked on hardware. And
covers get five fixes: a
stopped cover no longer loses the last poll's worth of travel, reversing
direction waits for the motor to stop first
(`direction_change_wait_time`, default 500ms, changes every existing
cover on upgrade), a full open or close now runs into the endstop to correct
time-based drift (`endstop_overrun`, default 10%, also changes every
existing cover on upgrade), a venetian blind at 0% with the slats open now
responds to Close, and `actuator_activation_duration` is applied instead of
silently ignored. None of the cover changes have been tried on hardware yet.

Two new system migrations, 1.6.26 and 1.6.27, both reinstall
`boneio-system`; because it changed twice, plans 1.6.5, 1.6.8, 1.6.9,
1.6.17, 1.6.18 and 1.6.22 — everything else that also installs it — are
re-signed alongside it, and the manifest is re-signed as it is for every
release, since it names the release.

---

# v1.6.0.dev19 — internal test build

## Since dev18

This is a fix-up release for the first-run wizard, found on a brand-new
controller flashed straight from the dev18 image — not one upgraded from
1.5. Both bugs below matter for every freshly flashed controller: the first
put every one of them on the same path as an upgraded device, so every
fresh controller also hit the second.

The schema fills `web.auth` with its defaults (`allow_anonymous: false`) on
every device, so the legacy-auth migration always found a non-empty block
with no username or password in it, logged "web.auth is incomplete" and
"Missing username or password", and marked the controller
`configured_before`. The first-run wizard reads that flag to decide which
steps to show, so it hid Import and Devices from every controller straight
out of the box — exactly the ones that need them, since none of them has a
login pair yet either. Only a username or a password now makes `web.auth`
count as a pre-1.6 block; a fresh, empty one no longer does.

On a controller the wizard treats as `configured_before` — every fresh one,
plus any genuinely upgraded from 1.5 — creating the administrator account
then jumped straight from Account to Done, skipping the Cloud step that the
progress bar at the top still showed as upcoming. "Back" from Done returned
to Account and offered to create an account that already existed, rather
than going anywhere useful. The wizard now goes Account → Cloud → Done in
that case, and no step leads back to Account once it has been left.

Alongside those two, Templates with nothing configured now matches the
centered grey text already used in Modbus and Sensors instead of a blue
alert box, and Inputs' "No inputs configured." is translated instead of
hard-coded English.

No new system migration and no plan changed since dev18
(`git diff --stat v1.6.0.dev18..HEAD -- boneio/migrations/` is empty). At
release, only the manifest gets a new signature, because it names the
release. Not yet tried on hardware.

---

# v1.6.0.dev18 — internal test build

## Since dev17

This is a fix-up release after a freshly flashed dev17 controller failed to
come up at all: it started before udev had handed `/dev/i2c-2` its `gpio`
group, since `boneio.service` no longer waits for `multi-user.target`,
crashed on `PermissionError` three times, dropped into recovery, and recovery
refused too — the image has no administrator account yet. Refusing recovery
used to exit at once, so systemd's restart brought the controller straight
back into the same refusal every few seconds, forever, with a black OLED and
Caddy answering 502. This is a regression from dev14, when the recovery panel
was added. `/dev/gpiochip*` has the same first-boot race: a chip not yet
handed to `gpio` failed at once, was reported and skipped, and its inputs
stayed dead — silently, no crash, no retry — until the service was restarted
by hand.

Four changes close this. boneIO now waits up to 60 s (a shared budget) for
`/dev/i2c-N` and `/dev/gpiochip*` to appear before giving up — past that
window the behaviour is what it was before (I2C raises, a GPIO chip is
reported and skipped), but the common first-boot race is now covered. A
refused recovery logs why, shows "Start failed" / "Retrying in 60 s" on the
OLED, and, under systemd, waits 60 s before exiting so the next start is a
normal one instead of another recovery attempt; this is a trade-off, not a
fix by itself — if the crash persists, that loop now does a real start that
drives the outputs roughly once a minute, instead of sitting in recovery
forever. A device that already has an account, whose panel merely fails to
serve, is unaffected and is still offered the panel again next start. Last,
crash messages on the OLED no longer vanish, because `luma`'s exit handler
used to blank the panel regardless of what was just drawn. This was
diagnosed on the controller at 192.168.50.125 — its `startup_failures.json`
recorded the `PermissionError` on `/dev/i2c-2` — but none of these four
fixes have been tried on hardware yet.

Migration 1.6.25 installs a `journald` drop-in that forwards journal entries
at warning level or worse to the serial console (`/dev/ttyS0`), early boot
included, so a controller that won't start can be diagnosed with a
USB-serial adapter even though the `boneio` account is locked and the serial
getty can't be used. Reaching the UART header needs the enclosure open, and
whoever has that already has the SD card and eMMC with the whole journal and
configuration on them, so this doesn't lower the bar for getting at the
device. The console is **not** masked: secrets are hidden only where the
panel shows the journal (`/api/logs`), so the wire carries exactly what
`journalctl` does. Part of adapting the 1.6 series to the CRA — a device
that fails should be diagnosable without weakening its login. Alongside it,
boneIO now tells journald the level of every line it writes instead of
leaving everything at `info`, so its own warnings, errors and tracebacks
reach that console too, and `journalctl -p err` and the panel's log-level
filter start working. This has only been checked against a local journald,
not yet on Debian 13 hardware.

A Modbus device that stops answering used to log an ERROR on every single
poll, from boneIO and from pymodbus both, burying every other warning in the
journal; it now warns once, then counts silently at INFO until it answers
again, and logs at WARNING once more when it recovers. A separate bug had
the coordinator treat a Modbus exception response — which pymodbus returns
on purpose, with no registers — as real data, marking the device ONLINE and
then failing to decode an empty payload on every poll. It's now correctly
treated as a failed read of that one register group, retried and logged
like any other failure, while the device's other groups keep being read
normally.

One new system migration, 1.6.25; its plan is already signed. At release,
only the manifest gets a new signature on top of that, because it names the
release.

---

# v1.6.0.dev17 — internal test build

## Since dev16

A device with no administrator has refused its API since 1.6 — a fresh
image, or an update from 1.5 that had no `web.auth` to migrate — but the
OLED said so only once, at boot, and then went dark with the rest of the
screensaver. The display now opens on a notice instead — "Setup required",
"Onboarding needed.", "Open in a browser:" and the panel's address — and does
not sleep while it stands. The button still leafs through the configured
screens, and a minute without a press brings the notice back rather than
dimming the panel. The address is rebuilt every few seconds, so a DHCP lease
handed out after boot appears, and a cloud address too wide for the panel
breaks after a dot instead of losing its port. Whether an admin exists is
checked every five seconds, so the notice clears itself however the account
was created — the wizard, the accounts CLI, a restored backup. Checked with
a luma render and the test suite; not yet seen on a physical display.

`/boot/firmware`, the small FAT partition a PC can open, was in fstab
without `nofail`, so local-fs.target required it. FAT has no journal, and a
power cut while it is mounted read-write leaves it dirty — the test
controller carried two `FSCK*.REC` files already. The day `fsck.fat` or the
mount gives up, systemd drops to emergency mode with a healthy root, no
network and no panel; U-Boot reads `uEnv.txt` and the kernel from the ext4
root, so nothing the boot actually needs was ever at risk. Migration 1.6.23
teaches the migration helper a new action, `fstab_add_options`, which edits
only the options field of one mount point's entries, atomically, and only
with options it lists itself; 1.6.24 applies `nofail` to `/boot/firmware`.
Needs the helper from 1.6.23. 1.6.24 is v2-only. New images get the option
from the eMMC flasher directly, so this pair is for controllers already
installed.

Two new system migrations, 1.6.23 and 1.6.24. Plans 1.6.5, 1.6.16 and
1.6.19 are re-signed because they install `boneio-migrate-v2`, which
changed; at release, only the manifest gets a new signature on top of that,
because it names the release.

---

# v1.6.0.dev16 — internal test build

## Since dev15

Part of the 1.6.x work adapting boneIO Black to the CRA: boneIO is now ready
for images that set the MQTT broker password per device at first boot, and
the paths around that password stop working against it. The validated
configuration cache used to pickle every `!secret` already
resolved to its value, with `secrets.yaml` outside the cache key, so a
password changed there did nothing until some unrelated edit invalidated
the cache — and the password itself sat in `.cache.pkl` by value. `!secret`
now caches as a reference to the name in `secrets.yaml` and is resolved
against it on every read, so a changed secret takes effect on the next start,
without the cold 20-30 s start a full revalidation costs, and `.cache.pkl`
no longer holds it.

A new config migration, v7 (`config_version: 7`), moves the broker
password out of `mqtt.yaml` into `secrets.yaml` (created or tightened to
0600) for controllers installed before per-device passwords existed,
leaving `password: !secret mqtt_password` behind. A password already given
as `!secret` is left alone, and an existing different `mqtt_password` in
`secrets.yaml` is kept rather than overwritten. Verified on the dev
controller (192.168.50.220): the password is only in `secrets.yaml`, zero
occurrences in `.cache.pkl`, MQTT connected.

Two places that used to undo this are fixed. Saving the MQTT page used to
dump secret fields as the plain value the panel sent back, so it wrote the
broker password into `mqtt.yaml` in the open and dropped the `!secret`
reference — on every image since per-device passwords shipped. A save now
keeps `!secret` references, and a plain password entered on the MQTT page
goes to `secrets.yaml`. Verified on .220. And reconnecting boneIO after the
panel changes the `boneio` account's password only treated the broker as
"installed here" for `localhost`, `127.0.0.1` or `::1` — a config with the
controller's own IP or hostname (`.local`) as `mqtt.host`, copied from the
address bar or shared with Home Assistant, was treated as remote:
mosquitto's password changed, the config kept the old one, the device
dropped off. The device's own hostname, loopback and any address it can
bind to now count as local, with no DNS lookup, and the new password lands
in `secrets.yaml`.

A full factory reset no longer overwrites the device's MQTT password with
the example config's `boneio123`, and no longer deletes `secrets.yaml` in
the process — it holds the owner's credentials, not board configuration,
and travels with the backup either way.

The first-run wizard's request now allows 60 s and login 30 s: creating the
first administrator is a scrypt hash plus two sudo calls, and on a fresh
BeagleBone's first boot it could take exactly the old global 5 s limit — the
panel reported "could not create the account" while the server went on and
created it. Operating-system and Caddy update calls now allow 30 s as well.

Only the manifest is re-signed for this build: no system migration or plan
changed since dev15, so the manifest — which names the release — is the
only file with a new signature.

---

# v1.6.0.dev15 — internal test build

## Since dev14

Part of the 1.6.x work adapting boneIO Black to the CRA requirement for a
secure update channel: a controller shipped a year ago still booted the
kernel and the OpenSSL it left the factory with. The panel gains an
"Operating system" card that checks for Debian updates, upgrades with a live
log, and refuses to offer a restart when the next boot's kernel is not
ready. Automatic security updates are on by default — Debian-Security only,
once a day, never a restart, never a removal — with a switch to turn them
off. A power loss mid-upgrade no longer leaves `dpkg` half-configured
refusing every later `apt` run: a recovery service runs
`dpkg --configure -a` at boot when needed. Caddy is now pinned to a version
this release names (2.11.4) instead of whatever `caddy:2-alpine` happened to
resolve to; a card shows the version running and moves the controller to the
pinned one on request, with the HTTPS panel down for about 15 seconds while
it does. PackageKit and AppStream, unused by boneIO and a source of `apt`
timeouts on a BeagleBone, are purged — migrations can now remove packages as
well as install them. Every update screen now tells the operator to back up
their configuration and Node-RED flows first, with a link to the system
images and recovery instructions.

Tested on the dev controller: 161 packages upgraded in 1770 s, kernel
6.18.2-bone12 → 6.18.53-bone55, overlay loaded after restart;
unattended-upgrades allowed only the Debian-Security origins; PackageKit,
AppStream and their four dependants purged, a system update check down to
36 s from 50; Caddy moved 2-alpine → 2.11.4 in 69 s with the HTTPS panel
down for about 15 s. The `docker-compose.yaml` that image builds copy onto a
fresh controller had lacked `WEB_PORT` since 1.6.15, so Caddy proxied to 8090
whatever `web.port` said; it is the trusted template again.

The alarm's PIN codes are now throttled: five wrong codes in a row are
refused for 30 s, doubling up to 15 min, with a "code lockout" binary_sensor
in Home Assistant and a PIN pad in the panel instead of a text field a
phone's keyboard would learn from. Config saves are atomic, so a power loss
mid-write no longer leaves a file the controller cannot boot from, and share
one lock, so two saves running at once no longer silently lose one of them;
a configuration pushed over CAN is now validated the same way a normal start
is before it replaces `config.yaml`. The panel gains a live card for every
entity on long press or right click, Templates on the phone's bottom bar,
coloured binding-matrix rows, a "Set position" cover action, and a header
that names who is signed in. MQTT stays connected through a bad payload or a
handler error, and Lox UDP can now forward Modbus readings to the
Miniserver.

Only the operating-system update chain above was run on the dev controller
for this build; the alarm, configuration-locking and panel changes have the
automated test suite behind them but not a hardware run.

Migrations 1.6.18–1.6.22 are new since dev14 (the update helper, `apt_purge`,
the PackageKit/AppStream purge, the Caddy pin, automatic security updates).
The plans they and eight earlier releases (1.3.0, 1.4.4, 1.6.5, 1.6.8, 1.6.9,
1.6.15, 1.6.16, 1.6.17) install were re-signed along with the manifest, which
names every release.

---

# v1.6.0.dev14 — internal test build

## Since dev13

A controller whose configuration does not load used to restart into the same
error every three seconds, with a hundred characters on the OLED as the only
clue. It now serves a recovery panel instead: the error with its line, an
editor, the log, backup restore and a restart. Three crashed starts in a row
lead there as well. It uses the regular panel's accounts and is admin-only.

Schedules now record every run, including the ones their own condition
skipped, and show it in the panel and in Home Assistant, where each schedule
appears as a switch with three diagnostic sensors.

The panel's navigation is new: a bottom bar on phones and tablets, a slimmer
desktop header, a redesigned login page, and a confirmation before logout.
The Templates page — thermostats, alarms, gates and irrigation — is redrawn
around one tile with large controls.

`gpio_mode` and `clear_message` leave the schema; both had been ignored at
runtime. Config migration v6 removes them from `event` and `binary_sensor` on
the next start, including sections kept in a separate file via `!include`, and
takes `config_version` to 6.

No system migration changed since dev13; only the manifest was re-signed,
because it names the release.

---

# v1.6.0.dev13 — internal test build

## Since dev12

The SSH login no longer has a password anyone can look up. Images before 1.6
gave the `boneio` account `Black`, the same on every unit and published, and
that account can become root. Expiring it — what the first 1.6 images did —
only made whoever logged in *first* choose a new one, which need not be the
owner: somebody on the same network could get there first with the published
password and lock the owner out.

New images ship the account locked, so no password works over SSH at all until
the owner runs the first-run wizard. The password given there for the panel's
administrator becomes the SSH password for `boneio` too, and the wizard says so
before asking. It is set once. Changing the panel password later does not
change it; `passwd` over SSH does, and asks for the current one.

A device already in service keeps whatever SSH password it has. The security
section now reports when that is still `Black`, as a critical finding, and
the remedy is `passwd`.

Migration 1.6.17 reinstalls `boneio-system`, which is where the password is set
from. The helper refuses to set it except where it grants nothing new — the
account locked, still on `Black`, or with no password — and never replaces a
password the owner chose.

---

# v1.6.0.dev12 — internal test build

## Since dev11

Hardware revision 1.1 is supported end to end: selectable in the panel,
accepted by the schema, and stamped onto a board by the eMMC flasher. It is 1.0
plus the buzzer, so the board maps and the overlay are unchanged.

The buzzer is 1.1 only now. It had been mapped on 1.0 too, where the part is
not fitted, and a config asking for it got an output that logged sysfs errors
rather than making a sound.

The QR code on the display and the device link in Home Assistant are built from
one property again. A cloud-registered controller used to show its certificate
name in Home Assistant and a bare IP on the OLED. The address behind both is
also refreshed now: it was read once at startup, so a DHCP lease that arrived
after boneIO was up left Home Assistant with no link until a restart.

Changing the broker password in the panel no longer takes the controller off
its own broker. The account the panel changes is the one boneIO connects with,
and boneIO kept presenting the old password until somebody edited the
configuration and restarted it. The panel now offers to store the new password
in boneIO's own configuration, and the MQTT section reconnects in place when
only the broker, the account or the password changed.

Saving a schedule from the panel works. Every save sent the section without its
actions, and the backend refused it for having none.

Startup is shorter. A cold configuration load on a BeagleBone took 37s and
takes about 2s: the packaged schema is no longer re-verified on every boot. The
discovery backends are imported when they are first needed instead of at boot,
the login placeholder hash is made on first use, and the web UI answers as soon
as it binds instead of sitting silent while the remote-device backends import.

Migration plans are unchanged since dev10; the manifest names the release, so
it was re-signed for this one and verifies.

# v1.6.0.dev11 — internal test build

## Since dev10

Schedules and sun-driven actions, virtual switches that can run actions of
their own, and a presence-simulation wizard that writes both. `location:` gives
the device coordinates; `earliest:`/`latest:` keep a sun anchor inside a clock
window, which midsummer otherwise pushes past bedtime.

Three things a test station and a running house both care about:

- Cached sun times are dropped when the clock is set and when the timezone
  changes. The board has no battery-backed clock, so it boots in the year 2000
  until NTP answers; the sun provider kept answering with the old timezone
  until a restart.
- A schedule set inside the hour the spring clock change removes fired an hour
  late, while the log and the panel both printed the time that had been asked
  for. It now fires at the first moment that exists.
- The Timezone page reported "permissions not installed, apply your pending
  migrations" whenever the check timed out — on devices whose migrations were
  all applied and whose rule was in place. Six routes that shelled out on the
  event loop were the cause; one of them hangs when NTP is unreachable.

Configuration now refuses at load time what it used to accept and get wrong at
runtime: two names that fold to one identifier, a switch whose actions set
itself, and a condition naming a virtual switch that does not exist.

Entries are written with `name:` and the identifier is derived from it. `id:`
is still accepted where a reference has to survive a rename.

# v1.6.0.dev10 — internal test build

## What this build is for

This release is part of bringing boneIO Black in line with the **EU Cyber
Resilience Act** (Regulation (EU) 2024/2847), which sets essential
cybersecurity requirements for products with digital elements sold in the EU.
Its substantive obligations apply from 11 December 2027, and the reporting
obligations have applied since 11 September 2026. This is not a declaration of
conformity — it is the engineering work that has to exist before one can be
made.

The requirements this build works towards, and what it does about each:

| CRA requirement | In this build |
|---|---|
| Ship with a **secure-by-default configuration** | The application no longer runs with a standing path to root; privileged work goes through helpers with fixed vocabularies. |
| Grant only the **privileges actually needed** | Wildcard sudo rules and the `docker` group — root without a password — are gone; what remains is four narrow NOPASSWD rules. |
| **Minimise the attack surface** | Every endpoint that collected the operator's system password is removed, except the one-time bootstrap on a device with no helper at all. |
| Deliver **security updates through a secure mechanism** | Migration plans are frozen and signed at release time with an Ed25519 key that is not held by CI, and verified on the device against two pinned anchors. |
| **Protect against unauthorised access** to privileged functions | Holding the `boneio` account is no longer equivalent to holding root. |

The mechanism is new, and the point of this build is to find out how it behaves
on a real 1.5.x controller upgraded in place.

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

**The `boneio` account is out of the `docker` group.** That group is root
without a password and without a sudo rule — the daemon starts containers as
root, so anyone who can reach its socket can ask for one with the host
filesystem mounted. It was a way around every helper in this series. Container
management goes through `boneio-containers` now, so nothing boneIO does still
needs it. The helper checks for itself that the replacement is installed and
root-owned before it removes anything, and a device whose migration helper
never arrived defers the step instead of failing it. Fresh images no longer
grant the group at all.

## Since dev9

**Taking the panel off the network keeps the USB cable.** It was binding the
loopback and the Docker bridges and nothing else, which would have closed the
link the factory station uses to reach a board with no other address, and the
one anybody uses to recover a controller whose Ethernet is wrong. A cable is
not the network: whoever plugged it in has physical access already.

**fastapi 0.141.1**, which unblocks starlette — four advisories were sitting on
the version fastapi==0.118.0 held it at. starlette and cryptography get floors
for the same reason anyio did: both are indirect, nothing pins them, and pip
leaves a satisfied dependency alone, so a device keeps whatever it was imaged
with. One controller here was still running cryptography 46.0.4.

Everything else since dev9 is development tooling and changes nothing on a
device: the deployment script now says when a controller is not running the
versions the project declares, and there is a check that asks a live device
whether the socket still delivers entities, migrations are all applied and
nothing failed to initialise — the three things that were wrong in earlier
builds while every test was green.

## Since dev8

**The dependency advisories that reach a controller are closed.** aiohttp,
python-multipart and requests are bumped. anyio needed more than a bump: it is
not a direct dependency, it arrives through starlette, and pip's default
upgrade strategy leaves a satisfied dependency alone — so a device imaged with
an old one would have kept it through every update it ever received, including
this one. A floor in the requirements is what moves it, and the batch's only
critical advisory was against anyio.

**Tokens are signed with PyJWT.** python-jose was carrying ecdsa, rsa, pyasn1
and six for algorithms this panel does not use — it signs one kind of token,
HS256 with a secret it holds — and ecdsa's advisory has no fixed version and no
prospect of one. Four dependencies leave with it.

## Since dev7

**The device's own certificate lasts six months rather than twelve hours.**
Caddy's internal issuer defaults to half a day, which for a certificate nobody
trusts until they decide to means the decision is undone daily: click through
the warning, or add an exception, or install this device's authority on your
laptop, and by the evening you meet a fresh unknown certificate. The
intermediate goes to a year alongside it, because Caddy refuses to start when a
leaf would outlive the intermediate that signs it — and that failure takes the
panel with it, so both were tried against a real Caddy before either was
written down.

Migration 1.6.14 carries it. Nothing restarts the proxy for it: the certificate
in use is valid, and swapping a working one for a longer-lived one is not worth
an interruption nobody asked for.

**A migration can now declare that a later one replaces it.** A file installed
by one and replaced by the next is written once per revision on a device
applying them from scratch, each write a signature check and a validator run
through the privileged helper. Whole migrations are skipped, never parts of one
— the helper is handed a version string and reads its plan from a signed file,
and that is what keeps the application out of deciding what runs as root. The
claim is checked rather than trusted: every effect of the older migration has
to be an effect of the newer.

## Since dev6

Corrections, most of them found by using the thing on a controller.

**The panel says why cloud registration is not working.** One device had it
switched on and was being told to switch it on, while the reason sat in the
application unread: the cloud was refusing the device outright. The error was
being fetched and rendered all along, behind a condition — the compose file
being writable — that 1.6 makes permanently false on every device.

**The certificate check tells the truth about all four cases**, including an
uploaded certificate, which it did not know existed.

**Closing the panel's own port is only recommended when the proxy can take
over.** It was advice we would have refused to carry out, and the operator
would have discovered that by clicking.

**Pressing that button no longer reports a failure for a save that worked.**
The check it makes can take seconds the first time — Caddy mints itself a
certificate before answering — and the browser was giving up at the same moment
the write completed.

**Home Assistant is no longer linked to a port that has been closed**, and the
panel shows the address that was actually published rather than describing the
rule for deriving it.

**The reverse proxy port is gone from the settings.** It only ever chose that
port in the Home Assistant link, the built-in proxy answers on 8443 regardless,
and anyone fronting the device with their own proxy is setting a full URL in
the dashboard add-on. Existing configurations keep working.

## Since dev5

Nothing new, and four things that were wrong in what dev5 shipped.

**One finding per finding.** The Security page listed the leftover pre-1.6
credentials twice: a check with that id already existed and a second was added
beside it rather than the first being improved.

**In Polish.** The check about the panel being served in the clear had no
translation at all, so it arrived as the backend's English with its remedy cut
off mid-sentence. The ids are in Python and the text is in JSON and nothing
connected them; a test does now, and it found both of these.

**Whole sentences.** The card truncated the remedy. That was right when a
remedy was a one-line shell command.

**Where the setting lives.** Taking the panel off the local network was only a
security finding, which is to say visible until it was dealt with and invisible
to anyone looking for it afterwards. It is a switch in the Web Server section
too. The port field next to it was named after nginx, which has not been what
sits in front of this panel since 1.4.4, and read as "there is no proxy unless
you fill this in" on a device whose proxy is always running.

The panel also now shows the address worth using — the device's name rather
than its address, which the next DHCP lease changes — and the certificate card
no longer takes the Security page down when it is talking to an older device.

## Since dev4

**The migration chain ran again.** On a freshly imaged controller upgraded to
dev4 it stopped dead at 1.6.4 and stayed there, with six later migrations
behind it and no `boneio-system`. Three plans — 1.3.0, 1.4.0 and 1.6.4 — still
named a validator as a command string, which the signing helper refuses by
design; that refusal is the fix for the privilege-assignment weakness, and the
plans were simply never rewritten in the vocabulary that replaced it. The test
that was supposed to catch this asked whether the helper's own validator table
was well formed. It never asked whether the migrations were written in it. It
does now, by putting every action of every migration through the helper's own
gate.

**The panel gets its state back after the first-run wizard.** The socket
carries every entity to the panel and nothing polls for them, so a socket that
cannot open is a controller that appears to have no outputs, inputs or sensors
at all. Whether a token is required was decided once, at startup — on a device
that ships with no account, which is to say: decided as "no", permanently. The
moment the wizard created an account the client began offering its token and
the server kept refusing to agree to it. Every device claimed through the
wizard was in that state until the service was restarted.

**The wizard knows an upgraded device when it sees one.** It skips the import
and device-binding steps there, and it has never once done so: the value it
reads was computed, correct, and returned by an endpoint the wizard does not
call. The devices step replaces the whole `event` section, so this was the path
that loses a controller's input actions to a wizard its owner opened only to
create an account.

**Plain HTTP redirects to HTTPS.** That port was serving the login form, the
token it hands back and a configuration carrying passwords, readable by anyone
on the network.

**The panel can be taken off the local network.** `web.expose: proxy` binds it
to the loopback and the Docker bridges, leaving it reachable over TLS and
through an SSH tunnel. Offered from the Security section, and refused unless
the proxy is demonstrably already serving this panel — the failure mode is a
controller answering on no port at all.

**A certificate of your own.** Upload one and the proxy serves it, checked
first: a key that does not match stops the proxy from starting, and names that
do not cover the address people type leave exactly the warning they were meant
to remove. The device's own certificate authority can also be downloaded and
trusted on the machines that open the panel — no domain, nothing exposed.

**Cloud registration starts when it is switched on**, rather than at the next
boot.

**The serial console shows how to reach the device** — its name and its
address, filled in as the prompt is drawn.

## Since dev3

**An upgraded device is recognised as upgraded.** The first-run wizard decided
whether a controller was new by looking for a pre-1.6 `web.auth` block — which
detects "this device had a password on the panel", not "this device has a
configuration". Most 1.5.x controllers never had web authentication, so an
upgraded device was shown the full wizard, including the step that replaces the
whole `event` section. Freshness now has to be demonstrated rather than
assumed, and the two ways of being wrong are treated as what they are: showing
one step too few costs nothing, showing one too many costs a configuration.

**The serial console shows the device's address.** `agetty` fills it in when it
draws the prompt, so it is current rather than whatever DHCP had managed during
boot; a blank field means the lease had not arrived and Enter redraws it.

**Every release carries a component inventory.** A CycloneDX SBOM covering the
Python application and the frontend is attached to the release, so "there is a
vulnerability in X, are you affected" has an answer for a version that shipped
months ago.

**There is a vulnerability disclosure policy.** `SECURITY.md`: where to report,
what happens next, disclosure timelines, and a safe-harbour commitment for
research done in good faith.

## What is deliberately not done yet

- The `boneio` account still has `(ALL : ALL) ALL` through the `admin` group
  inherited from the stock BeagleBone image. That one is staying: it is behind
  the account password, and it is the operator's own way to a root shell on a
  controller in a cabinet. Taking it away would mean a device whose only repair
  is a serial console or the SD card.
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

# v1.5.6

Prepares 1.5 controllers for the update to 1.6, and fixes Home Assistant
moving entities out of their room.

## 🏠 Entities stay in their room in Home Assistant

Entities assigned to a room appeared in HA under "Black - Room" at first and
were moved to the main "Black" device shortly after, and a cover set to
`shutter` showed up as a window. The second discovery message boneIO sends
at startup had lost the room and the cover type. Covers, output groups and
Dallas/ADC sensors now keep their room, covers keep their type, and entities
with `show_in_ha: false` — including remote outputs — no longer appear in HA.

## 🧭 No more old panel after an update

After an update the browser could keep showing the previous panel for several
refreshes — its service worker serves a stored copy until it has downloaded
the new one. The panel now knows which version it was built for: when the
controller runs another one, it reloads itself once from the controller, and
if that is not enough it says so and suggests Ctrl+Shift+R.

While an update started from this browser is installing, a controller that
does not answer shows "update in progress — do not power off" instead of "API
unavailable". A controller that comes back on its old version is reported as
a failed update. The update page now waits for the new version to answer
before it reloads, and a page caught between two builds reloads itself instead
of staying blank.

Update to 1.5.6 before going to 1.6: the old panel cannot be fixed from the
new version, only from its own code.

---

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
