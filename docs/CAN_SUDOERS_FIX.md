# CAN Sudoers Auto-Fix Feature

## Overview

When CAN bus is enabled in the configuration, the application needs to run `sudo /sbin/ip link set can0 ...` to manage the CAN interface. If sudoers is not configured with NOPASSWD, this fails with "a terminal is required to read the password".

This feature:
1. **Detects** the sudoers issue and shows it as a warning in the web UI
2. **Provides a fix** button that creates the correct sudoers file via the UI

## Backend Changes

### New Module: `boneio/hardware/can/sudoers.py`
- `check_sudo_nopasswd_for_ip()` — checks if `sudo -n /sbin/ip link show can0` works without password
- `create_sudoers_file(password)` — creates `/etc/sudoers.d/boneio-can` with correct NOPASSWD rules
- Uses `visudo -c` to validate the file before installing

### Modified: `boneio/webui/routes/can.py`
- `GET /api/can/sudoers/check` — returns `{needs_password, sudoers_file_exists, error}`
- `POST /api/can/sudoers/fix` — accepts `{password}`, creates sudoers file

### Modified: `boneio/webui/routes/system.py`
- `GET /api/hardware/errors` — now also checks CAN sudoers status when CAN is enabled
- Returns `{type: "can_sudoers", error: "sudo_password_required", message: "..."}` in errors array

## Frontend Changes

### New Component: `SudoPasswordDialog.tsx`
- **Reusable modal dialog** for sudo password input, used across the entire app
- Based on Radix Dialog (`@/components/ui/dialog`)
- Features: auto-focus, Enter to submit, loading/error/success states, i18n
- Props: `open`, `onOpenChange`, `title`, `description`, `submitLabel`, `isSubmitting`, `error`, `success`, `onSubmit(password)`
- Used by: `FixAppPermissions`, `FixCanSudoers`, `WebServerForm` (cloud permissions)

### Modified: `HardwareErrors.tsx`
- Separates `can_sudoers` errors from other hardware errors
- Shows CAN sudoers error as `alert-warning` (orange) with "Fix" button linking to `/system`
- Regular hardware errors continue showing as `alert-error` (red)

### New Component: `FixCanSudoers.tsx`
- Standalone card shown on SystemState page
- Auto-checks sudoers status on mount
- Hidden if sudoers is already OK
- Opens `SudoPasswordDialog` when "Create sudoers file" is clicked

### Modified: `FixAppPermissions.tsx`
- Refactored to use `SudoPasswordDialog` instead of inline password input

### Modified: `WebServerForm.tsx`
- Refactored cloud permission fix to use `SudoPasswordDialog`
- Replaced inline password `<input>` with "Fix" button that opens the dialog

### Modified: `SystemState.tsx`
- Added `<FixCanSudoers />` after `<FixAppPermissions />`

## Translations

Added `can_sudoers` section to both EN and PL `common.json` with keys:
- `title`, `description`, `checking`
- `error_title`, `error_description`, `fix_button`
- `password_required`, `password_required_hint`
- `sudo_password_placeholder`, `create_sudoers`
- `info_1`, `info_2`

## Sudoers File Content

Created at `/etc/sudoers.d/boneio-can` with permissions `0440`:

```
boneio ALL=(ALL) NOPASSWD: /sbin/ip link set can0 *
boneio ALL=(ALL) NOPASSWD: /sbin/ip link set can1 *
```
