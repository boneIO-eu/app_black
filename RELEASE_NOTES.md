# ⛔ DO NOT INSTALL THIS VERSION ⛔

**This is a beta. Please do not use this version.**

`1.6.0.dev18` exists so that we can test the new system-migration chain on a
development controller. The chain has been run end to end on two devices, and
dev4 stalled partway through on one of them — see below. That is the entire
body of evidence behind it.

It changes how boneIO obtains root privileges, installs new system helpers,
rewrites sudo rules, takes ownership of `docker-compose.yaml` and removes the
`boneio` account from the `docker` group. On a device in production, a mistake
in any of that means a controller that needs physical access to repair.

- **Do not install it on a controller you depend on.**
- **Do not install it on a device you cannot reach with a console or an SD card
  reader.**
- If your panel offers it as an update, **skip it.** It is marked as a
  pre-release and is not offered automatically; you would have to select it by
  hand.

Stay on the latest stable release. A version of this work that is meant for you
will be announced as such, and it will not look like this notice.

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
