# Release Notes Management

## Rule: Maintain RELEASE_NOTES.md on every significant change

After implementing any **significant feature, fix, or breaking change**, you MUST update (or create) the file `RELEASE_NOTES.md` in the repository root.

### What counts as "significant":
- New user-facing feature (new UI section, new API endpoint, new device type support)
- New system migration
- Breaking API or config changes
- Major bug fixes affecting user workflows
- Performance improvements noticeable to users
- New i18n support / translations for new sections

### What does NOT need an entry:
- Code cleanup / refactoring without user-visible impact
- Dev dependency bumps
- Lint fixes, formatting changes
- Test-only changes
- Minor translation fixes for existing keys

### RELEASE_NOTES.md format:

```markdown
# Release Notes — v{NEXT_VERSION}

> This file is auto-included in the GitHub Release when a stable version is tagged.
> Delete this file after the stable release is published.

## ✨ New Features

- **Feature name** — short description of what it does and why it matters

## 🐛 Bug Fixes

- **Fix description** — what was broken and how it was fixed

## ♻️ Improvements

- **Improvement description** — what was improved

## ⚠️ Breaking Changes

- **What changed** — migration instructions if needed

## 🗃️ System Migrations

- **vX.Y.Z** — what the migration does (files installed, services changed)
```

### Workflow:
1. When implementing a significant change, **append** to the relevant section in `RELEASE_NOTES.md`
2. If the file doesn't exist yet, create it with the template above
3. Use the current dev version cycle's target version (e.g., if working on `1.4.0devN`, set header as `v1.4.0`)
4. When issuing a **stable release** (not dev), the `auto-release.yml` workflow will use this file as the release body
5. After the stable release is pushed, **delete** `RELEASE_NOTES.md` and commit — the next dev cycle starts fresh

### Reminders:
- Before running the `/release-app` workflow for a **stable** release, check if `RELEASE_NOTES.md` exists and is up to date
- If it's missing or incomplete for a stable release, **warn the user** and offer to generate one from git log before proceeding
