# ⛔ DO NOT INSTALL THIS VERSION ⛔

**This is a beta. Please do not use this version.**

`1.6.0.dev10` exists so that we can test the new system-migration chain on a
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
