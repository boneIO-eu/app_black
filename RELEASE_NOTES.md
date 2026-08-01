# v1.5.1

## 🐛 Bug Fixes

- **Fix HA MQTT discovery for event entities**: Home Assistant rejected MQTT discovery messages for `event` entities (inputs configured as events) because `device_class: None` was sent in the payload. HA requires either a valid `EventDeviceClass` value (`button`, `doorbell`, `motion`) or the field to be omitted entirely. The fix filters out `None` values from discovery message kwargs before publishing.
