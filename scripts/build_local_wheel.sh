#!/bin/bash
# Build a boneIO wheel from this checkout — the working tree, uncommitted
# changes included — the way the release workflow does (publish-to-pypi.yaml:
# JSON schemas, frontend, then the package), to test on a controller or in an
# image without releasing a dev version for each attempt.
#
# Usage:
#   scripts/build_local_wheel.sh [out_dir]          (default: dist-local/)
#
# Then, for an image:
#   sudo ../black_debian_images/scripts/build_rootfs_offline.sh <base.img> <out.img> \
#        --boneio-wheel dist-local/boneio-<version>-py3-none-any.whl
# or on a controller:
#   scp dist-local/boneio-*.whl boneio@<ip>:/tmp/
#   sudo BONEIO_WHEEL=/tmp/boneio-<version>-py3-none-any.whl ./setup_boneio.sh
#
# The wheel carries the version in boneio/version.py, and the migration plans
# as they are signed in this tree. A changed migration needs signing like any
# release (scripts/generate_signed_plans.py) — the controller's helper refuses
# an unsigned plan, local wheel or not.
#
# Cloud registration needs the build secret the release workflow injects. Set
# BONEIO_MASTER_SECRET in the environment to put it into this wheel; without it
# the wheel works, but the device cannot register with the cloud. The secret
# only ever goes into a temporary copy, never into this tree.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(mkdir -p "${1:-$REPO/dist-local}" && cd "${1:-$REPO/dist-local}" && pwd)"
PYTHON="${PYTHON:-python3}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$REPO/boneio/version.py")
revision=$(git -C "$REPO" describe --always --dirty 2>/dev/null || echo unknown)
echo "boneIO ${version} from ${REPO} (${revision})"

echo "== Frontend"
# Built in place: frontend-dist is git-ignored, and node_modules stays for the
# next run instead of being installed again in a copy.
(cd "$REPO/frontend" && pnpm install --frozen-lockfile && pnpm build)

echo "== Copy of the tree"
rsync -a \
    --exclude .git --exclude 'frontend/node_modules' --exclude 'frontend/.claude' \
    --exclude '__pycache__' --exclude '.venv' --exclude 'venv' \
    --exclude 'dist' --exclude 'dist-local' --exclude '.ai-plans' --exclude '*.pkl' \
    "$REPO/" "$WORK/src/"

echo "== JSON schemas"
(cd "$WORK/src" && "$PYTHON" boneio/core/config/schema_converter.py)

if [ -n "${BONEIO_MASTER_SECRET:-}" ]; then
    sed -i "s/__BONEIO_MASTER_SECRET_PLACEHOLDER__/${BONEIO_MASTER_SECRET}/g" \
        "$WORK/src/boneio/core/cloud/secrets.py"
    echo "== Build secret injected (temporary copy only)"
else
    echo "WARNING: BONEIO_MASTER_SECRET not set — cloud registration will not work with this wheel" >&2
fi

echo "== Wheel"
"$PYTHON" -m pip wheel --no-deps --wheel-dir "$WORK/wheel" "$WORK/src" >/dev/null
wheel=$(ls "$WORK"/wheel/boneio-*.whl)

# Same check as the release workflow: without the public key and the .sig
# files the controller's helper refuses every migration.
"$PYTHON" - "$wheel" <<'PY'
import sys, zipfile
names = zipfile.ZipFile(sys.argv[1]).namelist()
sigs = [n for n in names if n.startswith("boneio/migrations/plans/") and n.endswith(".sig")]
missing = [n for n in ("boneio/migrations/plans/manifest.json",
                       "boneio/migrations/plans/manifest.sig",
                       "boneio/migrations/assets/migrations.pem") if n not in names]
dist = [n for n in names if n.startswith("boneio/webui/frontend-dist/")]
if missing or len(sigs) < 2 or not dist:
    sys.exit(f"wheel is incomplete: missing={missing} sigs={len(sigs)} frontend={len(dist)}")
print(f"   {len(sigs)} signatures, {len(dist)} frontend files")
PY

cp "$wheel" "$OUT/"
echo "== Done: $OUT/$(basename "$wheel")"
echo "   boneIO ${version}, tree ${revision}. A test build, not a release."
