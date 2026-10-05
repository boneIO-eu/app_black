#!/usr/bin/env bash
#
# prepare_dev_controller.sh — turn a freshly flashed controller into a dev one.
#
# After this, scripts/remote_test.sh works against it the way it did against
# the old dev controller: the service runs this tree, editable, so a deploy is
# an rsync and a restart.
#
#   1. puts your SSH key on the device (asks the boneio password once)
#   2. builds the frontend and pushes the tree with it to ~/app_black
#   3. installs that tree editable into the production venv (~/boneio/venv),
#      replacing the released wheel, so ExecStart stays as shipped
#   4. once, with the sudo password: adds /etc/sudoers.d/black-dev, a rule for
#      `systemctl restart boneio` alone, so deploys can restart unattended, and
#      a drop-in setting BONEIO_DEV=1 (CORS for the Vite dev server on :5173,
#      /docs, the fake-device routes, no login before the first account). A
#      drop-in, so a migration that reinstalls boneio.service does not drop it
#   5. restarts the service and checks it answers with the tree's version
#
# The black-dev rule and the drop-in are dev conveniences: audit_image.sh flags
# the rule, and neither belongs on a device that leaves the bench.
#
# Usage:
#   scripts/prepare_dev_controller.sh 192.168.50.220
#
set -euo pipefail

HOST="${1:?usage: $0 <device ip or hostname>}"
REMOTE="boneio@$HOST"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUDOERS_RULE="boneio ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart boneio"

step() { printf '\n== %s\n' "$*"; }

step "SSH key"
if ssh -o BatchMode=yes -o ConnectTimeout=10 "$REMOTE" true 2>/dev/null; then
  echo "key already accepted"
else
  ssh-copy-id "$REMOTE"
fi

step "frontend build"
(cd "$REPO_ROOT/frontend" && pnpm build)

step "deploy + editable install into ~/boneio/venv"
export REMOTE
"$REPO_ROOT/scripts/remote_test.sh" deploy --with-frontend deps

step "sudo rule + BONEIO_DEV drop-in (asks the sudo password once)"
# visudo checks the file before it is kept: a broken sudoers fragment locks
# sudo out entirely, which on a device with no root login is a reflash.
ssh -t "$REMOTE" "
  echo '$SUDOERS_RULE' | sudo tee /etc/sudoers.d/black-dev.new >/dev/null &&
  sudo chmod 440 /etc/sudoers.d/black-dev.new &&
  sudo visudo -cf /etc/sudoers.d/black-dev.new &&
  sudo mv /etc/sudoers.d/black-dev.new /etc/sudoers.d/black-dev ||
  { sudo rm -f /etc/sudoers.d/black-dev.new; exit 1; }
  sudo mkdir -p /etc/systemd/system/boneio.service.d &&
  printf '[Service]\nEnvironment=BONEIO_DEV=1\n' | sudo tee /etc/systemd/system/boneio.service.d/dev.conf >/dev/null &&
  sudo systemctl daemon-reload
"

step "restart on this tree"
"$REPO_ROOT/scripts/remote_test.sh" live

cat <<EOF

Done. For later runs against this device:
  REMOTE=$REMOTE scripts/remote_test.sh deploy live
EOF
