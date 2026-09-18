# Timezone & NTP

Configure the system timezone, whether the clock synchronises, and **which NTP
servers it synchronises with** — from the web interface.

## Why the NTP server matters on this board

The BeagleBone has no battery-backed real-time clock. After a power cut it boots
with a meaningless date and keeps it until something corrects it. Everything
that depends on wall-clock time is wrong until that happens: time and date
conditions on actions, irrigation schedules, log timestamps, certificate
validity.

On a site with no route to the internet — which is a normal way to install a
controller — the distribution's public NTP pool never answers, so nothing ever
corrects it. That is the case the NTP server setting exists for: point the
device at a server on the local network (a router, a domain controller, a
dedicated appliance) and the clock becomes trustworthy again.

## Backend API

All endpoints live in `boneio/webui/routes/system.py`.

### `GET /api/timezone`

```json
{
  "timezone": "Europe/Warsaw",
  "ntp_synchronized": true,
  "ntp_enabled": true,
  "local_time": "2026-09-17 20:04:06"
}
```

### `POST /api/timezone`

```json
{ "timezone": "Europe/Warsaw" }
```

The name is validated against `zoneinfo.available_timezones()`, then applied
with `sudo timedatectl set-timezone`. The validation is not cosmetic: the check
it replaced was `os.path.isfile("/usr/share/zoneinfo/" + tz)`, which passes for
`../../etc/passwd`.

### `GET /api/ntp`

Everything about time synchronisation in one place — what is configured, and
what the clock is actually following.

```json
{
  "enabled": true,
  "synchronized": true,
  "servers": ["192.168.1.1", "ntp.company.local"],
  "source": "boneio",
  "max_servers": 5,
  "server_name": "192.168.1.1",
  "server_address": "192.168.1.1",
  "poll_interval_usec": "34min 8s"
}
```

| Field | Meaning |
|---|---|
| `enabled` | Whether `systemd-timesyncd` is switched on |
| `synchronized` | Whether it has actually reached a server |
| `servers` | What boneIO configured, empty when using distribution defaults |
| `source` | `boneio` (a drop-in exists), `system` (defaults), `unknown` (helper not installed) |
| `server_name` / `server_address` | The server currently in use, straight from `timedatectl show-timesync` |

`server_address` is the field to look at when a local server was entered and the
clock still will not sync: if it names something else, the drop-in did not take.

### `POST /api/ntp`

Both fields are optional; send either or both.

```json
{ "enabled": true, "servers": ["192.168.1.1"] }
```

- `servers: []` — an **empty list removes** the drop-in and restores the
  distribution defaults. That is the only honest way to express "use the
  defaults": boneIO does not know what they were, so it stops overriding them.
- `servers` omitted — the configured servers are left alone.
- `enabled` omitted — the on/off state is left alone.

Servers are written **before** the on/off state is applied, so switching
synchronisation on in the same request does not spend a poll interval on the
public pool first.

Invalid server names come back as **400** with the helper's own message naming
the offending entry, not as a 500.

### `GET /api/timezones`

All names from `timedatectl list-timezones` (~600).

### `GET /api/timezone/sudoers/check`

Read-only check that the NOPASSWD rules exist.

```json
{ "needs_password": false, "sudoers_file_exists": true, "error": null }
```

> **`POST /api/timezone/sudoers/fix` no longer exists.** It accepted the
> operator's sudo password over HTTP to write the sudoers file. That password is
> the same on every controller that shipped, so an endpoint collecting it is a
> way to intercept it. The file is installed by migration 1.6.7 instead, over a
> channel that needs no password.

## How the NTP servers are applied

```
web UI ──POST /api/ntp──▶ system.py ──▶ system_ops.ntp_set()
                                              │  sudo -n /usr/sbin/boneio-system ntp-set "a,b"
                                              ▼
                                       boneio-system  (root)
                                              │  validates every entry
                                              │  writes /etc/systemd/timesyncd.conf.d/boneio.conf
                                              ▼
                                   systemctl try-restart systemd-timesyncd
```

The generated drop-in:

```ini
# Written by boneio-system. Edits here are replaced on the next change
# from the boneIO web interface.
[Time]
NTP=192.168.1.1 ntp.company.local
```

Three decisions worth knowing about:

**A drop-in, not `timesyncd.conf`.** The distribution's file is never touched,
so "use the defaults" is a file deletion rather than an edit that has to guess
what the defaults were.

**`try-restart`, not `restart`.** Changing *where* the time comes from must not
switch synchronisation back on for someone who deliberately turned it off.
`try-restart` only acts on a running daemon.

**Validation happens in the helper, not in the application.** The value is
written into a file systemd parses as root, so a space or a newline inside a
"server name" would let the caller append directives of their own. The check for
that belongs on the root side of the boundary; the copies in the API and in the
React component exist only to produce better error messages sooner.

Accepted: an IPv4 address, an IPv6 address, or a DNS name (letters, digits,
hyphens and dots, labels ≤63 characters, total ≤253). At most 5 entries, no
duplicates. Everything else is refused and nothing is written.

## Privileged helper

`boneio-system` (`boneio/migrations/assets/helpers/boneio-system`) gained two
verbs in 1.6.9:

| Verb | Does |
|---|---|
| `ntp-get` | Print the configured servers as JSON |
| `ntp-set <servers\|default>` | Write or remove the drop-in, then nudge the daemon |

The sudoers fragment names the helper and says nothing about its verbs, so
adding verbs does **not** widen what the service account may run. That is the
whole point of a helper with a closed vocabulary instead of a wildcard rule —
see `docs/CAN_SUDOERS_FIX.md` and CVE-2026-77055.

## Sudoers

`/etc/sudoers.d/boneio-timedatectl`, installed by migration 1.6.7:

```
boneio ALL=(root) NOPASSWD: /usr/bin/timedatectl set-timezone *
boneio ALL=(root) NOPASSWD: /usr/bin/timedatectl set-ntp *
```

`/etc/sudoers.d/boneio-helpers`, installed by migrations 1.6.5 / 1.6.8:

```
boneio ALL=(root) NOPASSWD: /usr/sbin/boneio-migrate-v2
boneio ALL=(root) NOPASSWD: /usr/sbin/boneio-containers
boneio ALL=(root) NOPASSWD: /usr/sbin/boneio-system
```

The wildcard on `set-timezone` is bounded by `timedatectl` itself, which refuses
any name that is not in tzdata. A polkit rule for
`org.freedesktop.timedate1.set-timezone` would be narrower still and is the
better long-term shape.

Read-only `timedatectl` commands (`show`, `show-timesync`, `list-timezones`)
need no privileges, which is why the status endpoints do not go through sudo.

## Frontend

| Component | Location |
|---|---|
| `TimezoneSection` | `frontend/src/components/UISettings/SystemStateComponents/TimezoneSection.tsx` |
| `NtpServersField` | `frontend/src/components/UISettings/SystemStateComponents/NtpServersField.tsx` |
| `FixTimezoneSudoers` | `frontend/src/components/UISettings/FixTimezoneSudoers.tsx` |

`NtpServersField` offers a choice between the system defaults and a custom list,
validates each entry as it is typed, and — once saved — shows which server the
clock actually ended up following. It re-reads the status two seconds after
saving, because `timesyncd` needs a moment to pick a server before the answer
means anything.

### Live ticking clock (`useTickingTime`)

The backend sends a snapshot (`local_time`). The frontend records `Date.now()`
at the moment of the fetch and, every second, adds the elapsed wall-clock time
to that snapshot, so the display advances instead of looking frozen. The next
fetch resets the snapshot.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "NTP status: not synchronized" and `server_address` is empty | No route to any configured server | Enter a server on the local network |
| Saving servers returns 400 | The entry is not an address or a DNS name | The message names the entry; check for stray spaces |
| Saving servers returns "not installed" | Migration 1.6.9 has not run | Apply pending system migrations, then retry |
| Servers saved but `source` is `system` | The drop-in was removed outside boneIO | Save again |
| Clock jumps far backwards after a power cut | No RTC and no reachable NTP server | This is the setting's whole purpose |

## Tests

- `tests/unit/core/test_system_helper.py` — the NTP verbs: what is accepted,
  what is refused (spaces, newlines, `[Time]`, over-long names), the drop-in's
  contents and mode, removal, and that a refused entry leaves the previous
  configuration untouched.
- `tests/unit/webui/test_timezone_sudoers.py` — the read-only sudoers check.
