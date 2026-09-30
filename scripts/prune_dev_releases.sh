#!/usr/bin/env bash
# Delete GitHub *releases* of superseded dev builds, keeping their git tags.
#
#   prune_dev_releases.sh 1.5.0            # dry run: list what would go
#   prune_dev_releases.sh 1.5.0 --delete   # actually delete
#
# Matches tags like v1.5.0dev7 and v1.5.0.dev41 (drafts included — they are
# visible because gh is authenticated). Stable releases never match: the
# pattern requires "dev<N>". Deleting via the releases API removes only the
# release entry and its assets; the tag stays, so `git checkout v1.5.0dev7`
# keeps working.
set -euo pipefail

REPO="boneIO-eu/app_black"
BASE="${1:?usage: $0 <base-version, e.g. 1.5.0> [--delete]}"
MODE="${2:-}"

# 1.5.0 → 1\.5\.0 for the regex
BASE_RE="${BASE//./\\.}"
PATTERN="^v?${BASE_RE}\\.?dev[0-9]+$"

mapfile -t ROWS < <(
  gh api --paginate "repos/${REPO}/releases?per_page=100" \
    --jq '.[] | [.id, .tag_name, (.draft|tostring), (.prerelease|tostring), .created_at[:10]] | @tsv' \
  | PAT="$PATTERN" awk -F'\t' '$2 ~ ENVIRON["PAT"]' \
  | sort -t$'\t' -k5
)

if [ "${#ROWS[@]}" -eq 0 ]; then
  echo "No dev releases match ${PATTERN}."
  exit 0
fi

printf '%-12s %-18s %-6s %-11s %s\n' ID TAG DRAFT PRERELEASE CREATED
for row in "${ROWS[@]}"; do
  IFS=$'\t' read -r id tag draft pre created <<<"$row"
  printf '%-12s %-18s %-6s %-11s %s\n' "$id" "$tag" "$draft" "$pre" "$created"
done
echo "Total: ${#ROWS[@]} release(s) matching ${PATTERN}"

if [ "$MODE" != "--delete" ]; then
  echo
  echo "Dry run — nothing deleted. Re-run with --delete to remove these releases (tags are kept)."
  exit 0
fi

for row in "${ROWS[@]}"; do
  IFS=$'\t' read -r id tag _ <<<"$row"
  gh api -X DELETE "repos/${REPO}/releases/${id}" >/dev/null
  echo "deleted release ${tag} (id ${id}), tag kept"
done
