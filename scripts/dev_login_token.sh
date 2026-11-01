#!/usr/bin/env bash
# Print a panel login token for an account on a dev controller, signed on the
# controller itself over SSH, so nobody has to remember its password.
#
#   scripts/dev_login_token.sh 192.168.50.134 [admin]
#
# Put it in the browser with  localStorage.setItem('token', '<token>')  and
# reload. Anyone with the boneio SSH key can already read the token secret,
# so this opens nothing new; it is still a full admin login for 30 days —
# dev controllers only.
set -euo pipefail

host=${1:?usage: $0 <controller-ip> [username]}
user=${2:-admin}

ssh -o LogLevel=ERROR "boneio@$host" /home/boneio/boneio/venv/bin/python - "$user" <<'EOF' | tail -n 1
import sys
from boneio.core.auth.jwt_secret import load_or_create_jwt_secret
from boneio.core.auth.store import UserStore
from boneio.webui.middleware.auth import issue_token, set_jwt_secret

store = UserStore.for_config_file("/home/boneio/boneio/config.yaml")
store.load()
account = store.get_user(sys.argv[1])
if account is None:
    sys.exit(f"No account {sys.argv[1]!r}; have: {[u.username for u in store.list_users()]}")
set_jwt_secret(load_or_create_jwt_secret(store.path.parent))
print(issue_token(account))
EOF
