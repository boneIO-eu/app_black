# boneIO Black 1.6.4

A small fix release after 1.6.3. On a controller already running 1.6.0 to
1.6.3 it only brings the fix below. Coming from 1.5.x, this is your update
to the 1.6 series: read "Before you update" first.

## What 1.6.4 fixes

- **After changing the configuration in settings, it could not be loaded.**
  Changing the controller type (for example to 32x10A) opens the "Device type
  change warning" dialog. It was clipped to the form card, so the Cancel and
  "Load and apply" buttons were out of view and the change could not be
  confirmed. The same happened to other dialogs opened from settings cards,
  such as Web server and Self-test. The dialogs now open over the whole
  screen again. This was present since 1.6.0.

## Before you update

- **Update to 1.5.6 first.** Only 1.5.6 knows how to hand the browser over to
  the new panel cleanly; from older versions the old panel may keep coming
  back after the update until you press Ctrl+Shift+R.
- **Be able to reach the controller physically**: an SD card reader or a
  serial console. This update changes how boneIO gets administrator rights on
  the system (see below). It has been run on our own controllers, but a
  mistake here is the kind that needs hands on the device to repair.
- **Keep a copy of your configuration** (the `/home/boneio/boneio` folder).
- **Plan up to an hour.** The update, with the system migrations that run at
  startup, can take up to an hour on a controller coming from 1.5.x; the
  display and the panel say what is happening. Let it finish and do not cut
  the power while it runs.

## What 1.6 changes on the device

1.6 is the work of adapting boneIO Black to the EU Cyber Resilience Act. It is
not a declaration of conformity; it is the engineering that has to exist
before one can be made. A new controller is secure from the first start: the
panel over HTTPS only, no default passwords, and an administrator account
created in the wizard.

- **The panel over HTTPS only.** New controllers do not serve the panel in
  plain HTTP on the local network; you open `https://<address>:8443`.
  Controllers updated from 1.5.x keep their current setting, and the Security
  page tells you how to change it.
- **Multiple accounts.** Besides administrators you can add read-only
  accounts: they see the controller and switch outputs, but cannot change
  settings or restart it.

- **No standing path to root.** Privileged work goes through three small
  system helpers with a fixed list of operations. Wildcard sudo rules are
  gone, and the `boneio` account is no longer in the `docker` or `kmem` group.
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
- **Whole-system updates from the panel**: Debian packages, the kernel and boneIO.

## New features and fixes in 1.6

- First-run wizard for new and freshly reset controllers.
- Schedules and sun-driven actions, and virtual switches that can run actions.
- New navigation: a bottom bar on phones and tablets.
- Hardware revision 1.1 supported end to end.
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
- v0.2/v0.3 controllers: `IN_26`, `IN_27` and `IN_28` work again.

The full list is in [CHANGELOG.md](CHANGELOG.md).

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

System migrations 1.6.1 to 1.6.46 are signed with the plans; this release
adds none. No plan changed since 1.6.0, only the manifest is re-signed,
because it names the release.
