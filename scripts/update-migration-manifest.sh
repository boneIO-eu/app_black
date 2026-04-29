#!/usr/bin/env bash
# Regenerate MANIFEST.sha256 for migration assets.
# Called by pre-commit when any file under boneio/migrations/assets/ changes.

set -euo pipefail

ASSETS_DIR="boneio/migrations/assets"
MANIFEST="$ASSETS_DIR/MANIFEST.sha256"

cd "$(git rev-parse --show-toplevel)"

# Compute SHA-256 for every file except the manifest itself
find "$ASSETS_DIR" -type f ! -name 'MANIFEST.sha256' -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  | sed "s|$ASSETS_DIR/||" \
  > "$MANIFEST"

# Stage the updated manifest so it's included in the commit
git add "$MANIFEST"
