# How boneIO signs what it runs as root

This document exists to be handed to someone auditing the device. It describes
the mechanism by which boneIO changes privileged system state, why it is built
the way it is, and — as importantly — what it does not protect against. It is
part of the work of bringing boneIO Black into line with the EU Cyber
Resilience Act (Regulation (EU) 2024/2847); it is not a declaration of
conformity.

Everything below can be checked on a device or in the repository. Where a claim
rests on a file, the file is named.

## The problem this solves

A controller has to change things only root may change: install a systemd unit,
write a sudoers fragment, set permissions on the broker's password file, take a
service account out of a group. The application itself runs unprivileged, as
`boneio`. So there has to be a channel from the unprivileged process to root.

The shape of that channel decides everything. If the privileged end accepts
*instructions* — do this, to that file, and validate it by running this command
— then holding the unprivileged account is equivalent to holding root, through
a completely legitimate call. No exploit is needed; the mechanism is the
vulnerability. An earlier version of boneIO's migration helper worked exactly
that way: it read a whole plan from standard input, including the paths to
write, the digests to check them against, and a free-text validation command it
ran as root.

The fix is not to sanitise that input. It is to stop accepting it.

## What the privileged helper receives

`/usr/sbin/boneio-migrate-v2` accepts one thing: a version string.

```json
{"protocol": 2, "version": "1.6.5", "package_root": "/path/to/boneio"}
```

`package_root` is a hint about where to look, not a grant of trust. The
application's `site-packages` are writable by `boneio`, so every byte read from
there is verified before use. There is no parameter through which a caller can
name a file, a digest, or a command.

## The verification chain

In order, and any failure ends the run:

1. **The manifest's signature.** `migrations/plans/manifest.json` must carry a
   valid Ed25519 signature from a key pinned in `/etc/boneio`, which is outside
   the application's reach.
2. **The release floor.** The manifest's release must not be older than the
   highest release this device has already accepted, recorded root-owned in
   `/var/lib/boneio/migrations.d/.release-floor`. Without this check an
   attacker could present a whole *older* package tree — every signature in it
   genuinely valid — and replay a migration this device never applied, or one
   whose effect has since been superseded.
3. **The plan is the one the manifest names.** The requested version must
   appear in the manifest, and the plan file's SHA-256 must equal what the
   manifest says. This is what stops a validly-signed plan from one version
   being presented as another.
4. **The plan's own signature.** Verified against the same pinned key.
5. **Not already applied.** Judged by root-owned flag files in
   `/var/lib/boneio/migrations.d`, never by anything the caller claims.
6. **The actions are in the whitelist.** A closed vocabulary — install a file,
   remove a file, reload/enable/disable/restart a unit, append a line if
   missing, allow a firewall port, install a package, install a wheel, set
   permissions, remove one named group membership, and a few more. Validation
   uses *named* validators only (`sudoers` → `visudo -cf`, `sshd` → `sshd -t -f`,
   `python` → `python3 -m py_compile`). There is no way to ask this helper to
   run a command of the caller's choosing.

One detail is easy to miss and carries real weight: **asset digests come from
inside the signed plan.** In the earlier design the digest arrived over the
same channel as the file path, from the same process that could replace the
file — so the integrity check compared a file against a hash supplied by
whoever could change the file. It proved nothing.

## Two trust anchors, not one

`/etc/boneio` holds two public keys:

| anchor | signs | may authorise |
|---|---|---|
| release | every release's plans | the full action vocabulary |
| recovery | no release, ever | nothing but re-pinning the two anchors |

Two rather than one, because re-pinning a key requires a migration signed by a
key the device already trusts. With a single anchor, losing the release key
would leave the installed base working but permanently unable to accept a
signed migration again — repairable only by reflashing each controller by hand.

The recovery key is deliberately not a second, equivalent key to root across
the fleet: a plan carrying its signature is restricted, by the helper, to
installing or removing exactly the two anchor files and nothing else.

## Where the keys live

- **The release signing key is not in CI.** Signatures are committed to the
  repository, and the workflows only *verify* them — verification needs the
  public half alone. A compromised release pipeline therefore cannot mint a
  plan that runs as root on every controller in the field. Signing is a
  deliberate local act by the release owner, against a key held outside the
  build system.
- **The recovery private key is offline, on paper, in a safe.** It signs no
  release and is expected never to be used.
- Current anchor fingerprints, which a device can be checked against:
  release `1d081f69f00e36da`, recovery `8c0c9029c94a0f57`.

## How plans come to exist

Plans are frozen at release time, not built on the device:

```
scripts/generate_signed_plans.py --key <the signing key>
```

writes, under `boneio/migrations/plans/`, a canonical serialisation of each
migration module's `plan()` output, an Ed25519 signature over those exact
bytes, a manifest naming the release and the SHA-256 of every plan, and a
signature over the manifest. Because the manifest names the release it belongs
to, bumping the version invalidates it even when no migration changed — which
is intentional, so a release cannot ship plans belonging to another.

`--check` re-derives every plan from its module and verifies every signature
against the public key. It runs in CI, so a release whose plans drifted from
the code they describe fails the build rather than shipping.

## Recovery without the shared account

The pristine copies of every privileged helper live in
`/usr/lib/boneio/trusted`, root-owned, and `boneio-helpers-heal.service`
restores from there at boot if one goes missing.

There is deliberately **no sudo rule for reinstalling the helpers or the
anchors.** The password for the `boneio` account is shared across controllers,
and a recovery path that could reinstall the *public key* would let an attacker
re-pin their own anchor and then sign every future "trusted" plan — a
persistence that would survive this entire design.

## What this does not protect against

Stated plainly, because an auditor will ask and because a mechanism whose
limits are hidden is worse than one whose limits are written down.

- **A device already compromised as root.** An attacker with root can replace
  both anchors, the helpers and the flag files locally. No in-place update can
  bootstrap trust on a machine that is already owned.
- **The operator's own route to root.** The `boneio` account is in a group
  carrying a password-gated `(ALL:ALL) ALL` rule inherited from the stock
  BeagleBone image. It is retained on purpose: it is how an operator reaches a
  root shell on a controller in a cabinet. It is behind a password, and on
  images from 1.6 onwards the shipped password is expired at first login so the
  owner sets their own — but anyone who learns that password has root.
- **A development escape hatch.** While the root-owned file
  `/etc/boneio/allow-unsigned-migrations` exists, the helper accepts an
  unsigned plan over standard input — that is the old behaviour, and it
  reopens the escalation this design closes. It exists so migrations can be
  developed on a real device. It is honoured only while the file is
  *root-owned*, so the application cannot grant itself the hatch by creating
  it; every use is logged at WARNING, and `--selftest` reports its presence. It
  must not be present on a shipped device, and an audit should check for it.
- **The integrity of the wheel itself.** This mechanism protects what runs *as
  root*. The unprivileged application is installed by pip from PyPI and is
  covered by that channel's guarantees, not by these signatures.

## Checking it yourself

On a device:

```bash
sudo boneio-migrate-v2 --selftest     # protocol, verification path, anchors, flags
ls -l /etc/boneio/                     # the two pinned anchors, root-owned, 0444
cat /var/lib/boneio/migrations.d/.release-floor
ls /var/lib/boneio/migrations.d/       # which migrations this device has applied
test -e /etc/boneio/allow-unsigned-migrations && echo "DEV HATCH PRESENT"
sudo tail /var/log/boneio-migrate.log
```

In the repository:

```bash
python scripts/generate_signed_plans.py --check
```

## Where the code is

| what | where |
|---|---|
| the privileged helper | `boneio/migrations/assets/helpers/boneio-migrate-v2` |
| plan generation and signing | `scripts/generate_signed_plans.py` |
| the action vocabulary | `boneio/migrations/actions.py` |
| the runner that decides what is pending | `boneio/migrations/runner.py` |
| installing the helper and pinning the anchors | `boneio/migrations/versions/v1_6_5_trust_transition.py` |
| retiring the helper that accepted a plan | `boneio/migrations/versions/v1_6_6_retire_legacy_helper.py` |
| the self-heal unit | `boneio/migrations/assets/systemd/boneio-helpers-heal.service` |
