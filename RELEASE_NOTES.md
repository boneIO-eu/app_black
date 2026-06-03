## v1.4.2 (2026-06-03)

Hotfix — TimePeriod object handling in input forms.

### 🐛 Bug Fixes

- **EventForm crash** — `parseMs()` called `.match()` on TimePeriod objects (`{milliseconds: 220}`) instead of strings, causing `Uncaught TypeError: val.match is not a function`. Replaced with the existing `convertTimeperiodToMilliseconds()` utility.
- **BinarySensorForm wrong bounce_time** — `typeof data.bounce_time === 'number'` always returned `false` for TimePeriod objects, displaying default `120ms` instead of the configured value. Fixed using `convertTimeperiodToMilliseconds()`.

### 🛡️ Improvements

- **Pre-commit hook** — Added `tsc --noEmit` TypeScript type-check before vitest to catch build-breaking issues (unused variables, type errors) before commit.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.1...v1.4.2
