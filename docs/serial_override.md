# Serial Number Override Feature

## Introduction
When a boneIO controller is replaced (e.g. during an RMA/warranty exchange), the new device has a different MAC address and therefore a different default serial number.
Restoring a backup from the old controller directly onto the new controller would normally cause issues because:
1. The MQTT topic prefix changes (derived from the serial number).
2. The Home Assistant `entity_id` and unique IDs change (also containing the serial number).

This feature allows overriding the default serial number of the controller, allowing a replacement device to adopt the identity of the device it replaces, keeping all Home Assistant entities, dashboard mappings, and automations intact.

---

## Technical Concept: Dual Serial Numbers

In `ConfigHelper`, we split the concept of device serial numbers into two distinct properties:

1. **`real_serial`** (property): Always generated from the MAC address. Used for Home Assistant `device_info.serial_number` and `device_info.model_id`, so users can see the actual physical serial.
2. **`serial_number`** (property, a.k.a. effective serial): Used for MQTT topics, entity unique IDs, Cloud/PWA registration, and HA discovery paths. Defaults to `real_serial`, but returns the override value when `serial_override` is set in the `boneio` YAML section.

> **Note**: The deprecated `serial_no` alias has been removed. All code should use `serial_number`.

---

## How It Works During Restore

1. **Backup Metadata**:
   When creating a backup (either via download, automatic backup before restore, or creating a backup on device disk), a `_boneio_meta.json` file is added to the tar.gz archive.
   It stores metadata about the backup, including the `effective_serial` and `real_serial` of the controller it was generated on.

2. **Backup Inspection**:
   When restoring a backup:
   - The frontend calls the inspection endpoints (`/api/config/inspect_backup_file` or `/api/config/inspect_backup_path`) to check the backup metadata without performing the restore first.
   - If the `effective_serial` in the backup differs from the current controller's serial, a warning dialog is presented to the user.

3. **Dialog Confirmation**:
   The user is asked whether they want to adopt the old controller's serial number (`Keep Old Serial`).
   - If **Yes**: The restore proceeds, and the API automatically injects `serial_override: <old_serial>` into the `boneio` configuration section.
   - If **No**: The restore proceeds without modifying the serial. The controller will use its default MAC-based serial (meaning Home Assistant will see new entities).
   - If **Cancel**: The restore is aborted.

---

## Configuration Schema

The `boneio` section in `config.yaml` (or the included file) accepts `serial_override`:

```yaml
boneio:
  name: boneIO
  version: "0.8"
  device_type: "32x10a"
  serial_override: blk112233  # Overrides default serial with the specified one
```

---

## UI Display
- In the top-left navigation corner and the mobile drawer footer, the active override is shown next to the physical serial number:
  `S/N: blk445566 (as: blk112233)`
- In the system configuration forms (`boneIO` settings tab), the override can be manually changed or removed. The input validates format in real-time (`blk` + 6 hex chars).

## Validation
- **Schema YAML**: `regex: '^blk[a-f0-9]{6}$'` — enforced when saving config.
- **Frontend**: Real-time format validation with `input-error` class and error message when invalid.
