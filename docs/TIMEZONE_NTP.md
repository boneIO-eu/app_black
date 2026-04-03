# Timezone & NTP Configuration

## Overview

Allows configuring the system timezone and NTP (Network Time Protocol) synchronization from the web interface.

## Backend API

All endpoints are in `boneio/webui/routes/system.py`.

### `GET /api/timezone`

Returns current timezone, NTP status, and local time.

```json
{
  "timezone": "Europe/Warsaw",
  "ntp_synchronized": true,
  "ntp_enabled": true,
  "local_time": "2026-04-03 13:10:00"
}
```

### `POST /api/timezone`

Set system timezone.

```json
{ "timezone": "Europe/Warsaw" }
```

- Validates against `/usr/share/zoneinfo/`
- Uses `sudo timedatectl set-timezone`

### `POST /api/ntp`

Enable/disable NTP synchronization.

```json
{ "enabled": true }
```

- Uses `sudo timedatectl set-ntp true/false`

### `GET /api/timezones`

Lists all available timezones from `timedatectl list-timezones`.

### `GET /api/timezone/sudoers/check`

Check if NOPASSWD sudoers rules exist for `timedatectl set-timezone` and `timedatectl set-ntp`.

```json
{
  "needs_password": false,
  "sudoers_file_exists": true,
  "error": null
}
```

### `POST /api/timezone/sudoers/fix`

Create `/etc/sudoers.d/boneio-timedatectl` with NOPASSWD rules.

```json
{ "password": "user_sudo_password" }
```

Response:

```json
{
  "status": "success",
  "message": "Sudoers file created at /etc/sudoers.d/boneio-timedatectl",
  "content": "boneio ALL=(ALL) NOPASSWD: /usr/bin/timedatectl set-timezone *\n..."
}
```

## Frontend

### `TimezoneSection` component

- Location: `frontend/src/components/UISettings/SystemStateComponents/TimezoneSection.tsx`
- Rendered in `SystemState.tsx` between `HostnameSection` and `MqttPasswordsSection`
- Features:
  - Current timezone + **live ticking local time** display (useTickingTime hook)
  - NTP sync status badge (green/yellow)
  - Searchable timezone selector with popular timezone group
  - NTP toggle switch
  - Embedded `FixTimezoneSudoers` component for sudoers management
  - i18n (en + pl)

### `FixTimezoneSudoers` component

- Location: `frontend/src/components/UISettings/FixTimezoneSudoers.tsx`
- Mirrors `FixCanSudoers` pattern
- Auto-checks sudoers on mount, shows OK/warning status
- When needs fix: shows warning + "Create sudoers file" button → SudoPasswordDialog
- Uses `timezone_sudoers.*` i18n keys

### Live Ticking Clock (`useTickingTime` hook)

When the backend returns `local_time` (e.g. `"2026-04-03 19:40:00"`), the frontend:

1. Parses the timestamp and records the `Date.now()` at the moment of fetch
2. Every 1 second, calculates elapsed time and adds it to the base timestamp
3. Displays the ticked-forward time so the user sees an updating clock
4. On next API fetch, the snapshot resets to the fresh server time

This prevents the user from thinking the clock is "stuck" or "off by N seconds".

## Sudoers

### `/etc/sudoers.d/boneio-timedatectl`

Created by `FixTimezoneSudoers` or manually. Contents:

```
boneio ALL=(ALL) NOPASSWD: /usr/bin/timedatectl set-timezone *
boneio ALL=(ALL) NOPASSWD: /usr/bin/timedatectl set-ntp *
```

### `/etc/sudoers.d/boneio-can` (existing)

For CAN interface management. Contents:

```
boneio ALL=(ALL) NOPASSWD: /sbin/ip link set can0 *
boneio ALL=(ALL) NOPASSWD: /sbin/ip link set can1 *
```

### Note

`timedatectl set-timezone` and `timedatectl set-ntp` require sudo.
The `timedatectl` read-only commands (`show`, `list-timezones`) work without sudo.

## Files Changed

| File                                        | Change                                                                         |
| ------------------------------------------- | ------------------------------------------------------------------------------ |
| `boneio/webui/routes/system.py`             | Added `GET/POST /api/timezone/sudoers/check`, `POST /api/timezone/sudoers/fix` |
| `boneio/webui/routes/timezone_sudoers.py`   | **New** — sudoers check/fix logic for timedatectl                              |
| `FixTimezoneSudoers.tsx`                    | **New** — sudoers config component for timezone                                |
| `SystemStateComponents/TimezoneSection.tsx` | Added `useTickingTime` hook + embedded `FixTimezoneSudoers`                    |
| `locales/en/common.json`                    | Added `timezone_sudoers.*` keys                                                |
| `locales/pl/common.json`                    | Added `timezone_sudoers.*` keys (Polish)                                       |
| `docs/TIMEZONE_NTP.md`                      | Updated documentation                                                          |
