## v1.4.1 (2026-06-03)

Hotfix release with SSL certificate renewal and Modbus chart improvements.

### 🐛 Bug Fixes

- **SSL certificate renewal** — `_cert_needs_refresh()` was checking file modification time (`st_mtime`) instead of the actual X.509 expiry date. If the cert file was touched by backup/copy/rsync, `mtime` would reset and the certificate would never be renewed even after expiry. Now parses the real `Not After` date using `openssl x509` and refreshes when the cert expires within 14 days.
- **Modbus sparkline charts for energy meters** — `shouldRenderHistory()` only whitelisted temperature/humidity sensors (by name pattern or unit `%`, `°C`, `rh%`). Energy meters with units like `W`, `kWh`, `V`, `A`, `Hz`, `VA`, `var` were excluded. Changed to show charts for all numeric read-only sensors that have a unit of measurement.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0...v1.4.1
