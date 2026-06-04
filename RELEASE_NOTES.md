# boneIO v1.4.3 Release Notes

## 🐛 Bug Fixes

### System Migration Helper (`boneio-migrate`)
- **Tolerant `systemctl reload/restart`**: Migration helper no longer fails when reloading or restarting a service that isn't currently active. This fixes the critical issue where `setup_boneio.sh` failed to apply migrations during image building because `mosquitto` was stopped at the time.

## ✨ New Features

### OLED Shutdown Messages
- **Late-phase shutdown service** (`boneio-oled-shutdown.service`): New systemd service that displays "System stopped. Safe to unplug." on the OLED screen **after** the network has gone down during shutdown.
- **Restart-aware ExecStopPost**: `boneio.service` now only shows "Shutting down..." during actual system shutdown. During `systemctl restart boneio`, the OLED skips the stop message and goes directly to "is starting...".

## 📦 Migration: v1.4.3

This release includes migration `v1.4.3` which automatically:
1. Installs `boneio-oled-shutdown.service` (late-phase shutdown OLED message)
2. Updates `boneio.service` with shutdown-aware `ExecStopPost`

The migration runs automatically on first startup after upgrade.
