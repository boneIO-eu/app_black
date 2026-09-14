#!/usr/bin/env bash
#
# remote_test.sh — deploy app_black to a dev controller and test it there.
#
# Runs the security/onboarding surface against the *real* controller: real ARM
# Python, real scrypt cost, real users.json permissions on the device's own
# filesystem — the things a laptop harness can only fake.
#
# Phases (safe by default):
#   deploy   rsync app_black to the controller (editable install, no reinstall)
#   harness  run the isolated web-UI harness in the device venv on a spare port
#            and assert the auth/onboarding behaviour over HTTP. Does NOT touch
#            the production service, config.yaml or the hardware.
#   pytest   run the auth unit tests in the device venv (real ARM). --full runs
#            the whole suite.
#   live     restart the production boneio service on the new code and confirm
#            it boots and reports the new version. This DOES interrupt the
#            running device, so it is never part of the default run.
#   smoke    just curl the live service's /api/init and print it.
#
#   all      = deploy + harness + pytest   (the safe default)
#
# Usage:
#   scripts/remote_test.sh                    # all (safe)
#   scripts/remote_test.sh deploy harness     # pick phases
#   scripts/remote_test.sh pytest --full      # whole suite on the device
#   scripts/remote_test.sh live               # restart prod + smoke
#   scripts/remote_test.sh deploy --with-frontend  # also push the built UI
#
# The built frontend is NOT pushed by default: these tests are API/pytest only.
# For UI work use the Vite dev server instead of building + rsyncing:
#   cd frontend && VITE_API_URL=http://<device>:8090 pnpm dev   # → localhost:5173
# (the device service must run with BONEIO_DEV set for its CORS to allow :5173).
#
# Override anything via env:
#   REMOTE=boneio@192.168.50.220
#   REMOTE_APP=app_black                       (path under the remote home)
#   SERVICE_CONFIG=/home/boneio/boneio/config.yaml
#   VENV=/home/boneio/venv
#   HARNESS_PORT=8099
#   SERVICE_PORT=8090
#
set -uo pipefail

REMOTE="${REMOTE:-boneio@192.168.50.220}"
REMOTE_HOST="${REMOTE##*@}"
REMOTE_APP="${REMOTE_APP:-app_black}"
VENV="${VENV:-/home/boneio/venv}"
SERVICE_CONFIG="${SERVICE_CONFIG:-/home/boneio/boneio/config.yaml}"
HARNESS_PORT="${HARNESS_PORT:-8099}"
SERVICE_PORT="${SERVICE_PORT:-8090}"
HARNESS_DIR="/tmp/boneio_webui_harness_$$"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SSH=(ssh -o BatchMode=yes -o ConnectTimeout=8)

# ---- pretty output --------------------------------------------------------
if [ -t 1 ]; then C_G=$'\e[32m'; C_R=$'\e[31m'; C_Y=$'\e[33m'; C_B=$'\e[1m'; C_0=$'\e[0m'
else C_G=; C_R=; C_Y=; C_B=; C_0=; fi
PASS=0; FAIL=0
section() { printf '\n%s== %s ==%s\n' "$C_B" "$1" "$C_0"; }
ok()   { printf '  %sPASS%s %s\n' "$C_G" "$C_0" "$1"; PASS=$((PASS+1)); }
bad()  { printf '  %sFAIL%s %s\n' "$C_R" "$C_0" "$1"; FAIL=$((FAIL+1)); }
info() { printf '  %s·%s %s\n' "$C_Y" "$C_0" "$1"; }

# check "label" expected actual
check() {
  if [ "$2" = "$3" ]; then ok "$1 ($3)"; else bad "$1 — expected [$2], got [$3]"; fi
}

# ---- phases ---------------------------------------------------------------

phase_deploy() {
  section "deploy → $REMOTE:$REMOTE_APP"
  # The backend runs editable from this tree, so the Python code has to go over.
  # The built frontend does NOT: these tests are API/pytest only, and UI work is
  # better done with `pnpm dev` (HMR, no build). So frontend-dist is excluded by
  # default — excluding it also shields whatever is already on the device from
  # --delete. Pass --with-frontend to push the current build when you want the
  # device itself to serve the up-to-date UI.
  local dist_exclude=(--exclude 'boneio/webui/frontend-dist')
  if [ "${WITH_FRONTEND:-0}" = "1" ]; then
    dist_exclude=()
    if [ -f "$REPO_ROOT/boneio/webui/frontend-dist/index.html" ]; then
      info "pushing the built frontend (--with-frontend)"
    else
      info "--with-frontend given but no build found; run (cd frontend && pnpm build) first"
    fi
  else
    info "skipping the built frontend (use pnpm dev for UI; --with-frontend to push it)"
  fi
  rsync -a --delete \
    --exclude 'graft' --exclude '.git' --exclude '.venv' --exclude 'venv' \
    --exclude '.github' --exclude 'frontend/node_modules' \
    --exclude '__pycache__' --exclude '.vscode' --exclude '__pypackages__' \
    --exclude '*.egg-info' "${dist_exclude[@]}" \
    "$REPO_ROOT/" "$REMOTE:$REMOTE_APP/"
  local rc=$?
  if [ $rc -eq 0 ]; then ok "rsync complete"; else bad "rsync failed (rc=$rc)"; fi
  local ver
  ver=$("${SSH[@]}" "$REMOTE" "$VENV/bin/python -c 'from boneio.version import __version__;print(__version__)'" 2>/dev/null | tr -d '\r')
  info "editable boneio now resolves to version: ${ver:-unknown}"
}

phase_harness() {
  section "harness → isolated web UI in the device venv (localhost:$HARNESS_PORT)"
  # The harness port is not reachable from off the controller (only the service
  # port is), so everything runs on the device over localhost and streams back
  # RESULT lines that we tally here. Nothing here touches the production
  # service, config.yaml or the hardware.
  local remote_out
  remote_out=$("${SSH[@]}" "$REMOTE" bash -s -- "$VENV" "$REMOTE_APP" "$HARNESS_DIR" "$HARNESS_PORT" <<'REMOTE_HARNESS' 2>&1
set -u
VENV="$1"; APP="$2"; DIR="$3"; PORT="$4"
BASE="http://127.0.0.1:$PORT"
emit() { printf 'RESULT %s\t%s\n' "$1" "$2"; }        # PASS|FAIL|INFO <text>
chk()  { if [ "$2" = "$3" ]; then emit PASS "$1 ($3)"; else emit FAIL "$1 — expected [$2] got [$3]"; fi; }
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$@"; }
field(){ python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: sys.exit(0)
v=d.get('$1'); print('' if v is None else ('true' if v is True else ('false' if v is False else v)))"; }

cleanup() { [ -f "$DIR/harness.pid" ] && kill "$(cat "$DIR/harness.pid")" 2>/dev/null; sleep 1; rm -rf "$DIR"; }
trap cleanup EXIT

# Kill any orphan harness from an earlier run that a local timeout could not
# reach (timeout kills the ssh client, not the remote setsid process), so a
# stale instance on this port never poisons the results.
pkill -f "remote_webui_harness:app" 2>/dev/null && sleep 1 || true

rm -rf "$DIR"; mkdir -p "$DIR"
cd "$HOME/$APP" || { emit FAIL "cannot cd to $HOME/$APP"; exit 1; }

WEBUI_HARNESS_DIR="$DIR" WEBUI_HARNESS_PORT="$PORT" \
  setsid nohup "$VENV/bin/hypercorn" --bind "127.0.0.1:$PORT" \
  scripts.remote_webui_harness:app > "$DIR/harness.log" 2>&1 < /dev/null &
echo $! > "$DIR/harness.pid"

up=""
# The first import after an rsync recompiles every .pyc while the production
# service is competing for a small amount of RAM, so cold start on a BBB is
# ~30s. Give it 90s before giving up.
for _ in $(seq 1 180); do
  curl -fsS -o /dev/null --max-time 5 "$BASE/api/init" 2>/dev/null && { up=1; break; }
  sleep 0.5
done
if [ -z "$up" ]; then emit FAIL "harness did not come up on $BASE"; sed 's/^/    LOG /' "$DIR/harness.log"; exit 1; fi
emit PASS "harness is up ($($VENV/bin/python -c 'from boneio.version import __version__;print(__version__)'))"

# fresh device: no accounts yet
chk "init.needs_onboarding on a fresh device" "true"  "$(curl -fsS --max-time 15 "$BASE/api/init" | field needs_onboarding)"
# F-02: before 1.6 an unprovisioned device served this to anyone.
chk "unprovisioned device refuses the API" "403" "$(code "$BASE/api/harness/protected")"
chk "  ...with a setup_required code" "setup_required" \
  "$(curl -s --max-time 15 "$BASE/api/harness/protected" | field code)"

# create the first admin — times scrypt on real ARM
t0=$(date +%s.%N)
adm=$(curl -s --max-time 30 -w '\n%{http_code}' -X POST "$BASE/api/onboarding/admin" \
       -H 'Content-Type: application/json' -d '{"username":"pawel","password":"dobre-haslo-123"}')
t1=$(date +%s.%N)
body=$(printf '%s' "$adm" | sed '$d'); ac=$(printf '%s' "$adm" | tail -1)
chk "create first admin → 201" "201" "$ac"
emit INFO "scrypt on this controller: $(awk "BEGIN{printf \"%.0f ms\",($t1-$t0)*1000}") per create round-trip"
tok=$(printf '%s' "$body" | field token)
[ -n "$tok" ] && emit PASS "wizard returned a token" || emit FAIL "wizard returned no token"

# device is now locked down
chk "protected route now needs a token" "401" "$(code "$BASE/api/harness/protected")"
chk "protected route accepts the token" "200" "$(code -H "Authorization: Bearer $tok" "$BASE/api/harness/protected")"
chk "init.auth_required flips to true"  "true" "$(curl -fsS --max-time 15 "$BASE/api/init" | field auth_required)"

# takeover attempt is refused (F-14)
chk "second admin creation → 409" "409" \
  "$(code -X POST "$BASE/api/onboarding/admin" -H 'Content-Type: application/json' -d '{"username":"x","password":"y-dlugie-haslo"}')"

# login: right / wrong / unknown (F-08)
chk "login correct → 200"  "200" "$(code -X POST "$BASE/api/login" -H 'Content-Type: application/json' -d '{"username":"pawel","password":"dobre-haslo-123"}')"
chk "login wrong pw → 401" "401" "$(code -X POST "$BASE/api/login" -H 'Content-Type: application/json' -d '{"username":"pawel","password":"zle"}')"
chk "login unknown → 401"  "401" "$(code -X POST "$BASE/api/login" -H 'Content-Type: application/json' -d '{"username":"nikt","password":"cokolwiek"}')"
chk "login role is admin"  "admin" "$(curl -fsS --max-time 15 -X POST "$BASE/api/login" -H 'Content-Type: application/json' -d '{"username":"pawel","password":"dobre-haslo-123"}' | field role)"

# --- roles: a viewer operates, an admin configures --------------------
vcode=$(code -X POST "$BASE/api/accounts" -H "Authorization: Bearer $tok" \
  -H 'Content-Type: application/json' \
  -d '{"username":"gosc","password":"haslo-goscia","role":"viewer"}')
chk "admin creates a viewer account" "201" "$vcode"

vtok=$(curl -fsS --max-time 30 -X POST "$BASE/api/login" -H 'Content-Type: application/json' \
  -d '{"username":"gosc","password":"haslo-goscia"}' | field token)
[ -n "$vtok" ] && emit PASS "viewer can sign in" || emit FAIL "viewer could not sign in"
VH="Authorization: Bearer $vtok"

chk "viewer may operate an output" "200" \
  "$(code -X POST "$BASE/api/outputs/relay_01/toggle" -H "$VH")"
chk "viewer may read state" "200" "$(code -H "$VH" "$BASE/api/harness/protected")"
chk "viewer may NOT restart the device" "403" "$(code -X POST "$BASE/api/restart" -H "$VH")"
chk "viewer may NOT list accounts" "403" "$(code -H "$VH" "$BASE/api/accounts")"
chk "viewer may NOT create an account" "403" \
  "$(code -X POST "$BASE/api/accounts" -H "$VH" -H 'Content-Type: application/json' \
     -d '{"username":"wlasny","password":"dobre-haslo","role":"admin"}')"
chk "viewer MAY change their own password" "200" \
  "$(code -X PUT "$BASE/api/account/password" -H "$VH" -H 'Content-Type: application/json' \
     -d '{"current_password":"haslo-goscia","new_password":"nowe-haslo-123"}')"
chk "admin may restart" "200" \
  "$(code -X POST "$BASE/api/restart" -H "Authorization: Bearer $tok")"

# users.json on the device's own filesystem
chk "users.json is 0600" "600" "$(stat -c %a "$DIR/users.json" 2>/dev/null)"
# grep -c always prints a count for an existing file (0 when no match) and
# exits 1 on no match; take the first line so a chained fallback can't double it.
chk "plaintext password absent from users.json" "0" \
  "$(grep -c 'dobre-haslo-123' "$DIR/users.json" 2>/dev/null | head -1)"
REMOTE_HARNESS
)
  # Tally the RESULT lines; pass INFO/LOG lines through.
  while IFS= read -r line; do
    case "$line" in
      "RESULT PASS	"*) ok  "${line#RESULT PASS	}" ;;
      "RESULT FAIL	"*) bad "${line#RESULT FAIL	}" ;;
      "RESULT INFO	"*) info "${line#RESULT INFO	}" ;;
      "    LOG "*)       printf '      %s\n' "${line#    LOG }" ;;
    esac
  done <<< "$remote_out"
}

phase_pytest() {
  section "pytest → device venv (real ARM)"
  # Make sure the test deps are present. They are read out of the rsynced
  # pyproject.toml rather than named here, so pyproject stays the single source
  # of truth and a freshly flashed dev controller gets the same versions CI and
  # the laptop use. tomllib is stdlib on the 3.13 the device runs.
  "${SSH[@]}" "$REMOTE" "$VENV/bin/python -c 'import pytest, httpx' 2>/dev/null" || {
    info "installing the pyproject 'test' group into the device venv (one-off)"
    "${SSH[@]}" "$REMOTE" "REMOTE_APP='$REMOTE_APP' $VENV/bin/python - " <<'REMOTE_DEPS' \
      && ok "test deps installed from pyproject" || { bad "could not install test deps"; return; }
import os, pathlib, subprocess, sys, tomllib

pyproject = pathlib.Path.home() / os.environ["REMOTE_APP"] / "pyproject.toml"
specs = tomllib.loads(pyproject.read_text())["tool"]["pdm"]["dev-dependencies"]["test"]
print("installing:", " ".join(specs))
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *specs])
REMOTE_DEPS
  }
  # The auth/authz suites. Listed by directory glob rather than by file so a
  # new test in these areas is picked up without editing this script.
  local target="tests/unit/core/test_auth_*.py tests/unit/core/test_setup_required_notice.py tests/unit/webui/test_auth*.py tests/unit/webui/test_account*.py tests/unit/webui/test_onboarding_*.py"
  if [ "${FULL:-0}" = "1" ]; then target="tests"; info "running the FULL suite (slow on a BBB)"; fi
  local out
  out=$("${SSH[@]}" "$REMOTE" "cd $REMOTE_APP && $VENV/bin/python -m pytest $target -q 2>&1" )
  echo "$out" | tail -8 | sed 's/^/      /'
  if echo "$out" | grep -qE "[0-9]+ passed" && ! echo "$out" | grep -qE "failed|error"; then
    ok "device pytest passed"
  else
    bad "device pytest reported failures"
  fi
}

phase_live() {
  section "live → restart the production service on the new code"
  info "this interrupts the running device for a few seconds"
  "${SSH[@]}" "$REMOTE" "sudo -n /usr/bin/systemctl restart boneio" \
    && ok "restart issued" || { bad "restart failed"; return; }
  local base="http://$REMOTE_HOST:$SERVICE_PORT" up=""
  # A cold start on a BBB imports a lot before the real server replaces the
  # loading screen; allow for that plus a slow first .pyc pass after an rsync.
  for _ in $(seq 1 120); do
    if curl -fsS -o /dev/null --max-time 5 "$base/api/init" 2>/dev/null; then up=1; break; fi
    sleep 1
  done
  if [ -z "$up" ]; then
    bad "service did not answer on $base after restart"
    # Print why, instead of leaving the reader to go and look. A crash loop is
    # the usual cause and the traceback says so in one line.
    info "restart count: $("${SSH[@]}" "$REMOTE" 'systemctl show boneio -p NRestarts --value' 2>/dev/null | tr -d '\r')"
    info "recent errors from the service:"
    "${SSH[@]}" "$REMOTE" \
      'journalctl -u boneio -n 60 --no-pager 2>/dev/null | grep -iE "error|traceback|exception|critical" | tail -8' \
      2>/dev/null | sed 's/^/      /'
    return
  fi
  ok "service is back up"
  local ver auth need
  ver=$(curl -fsS "$base/api/init" | _json version)
  auth=$(curl -fsS "$base/api/init" | _json auth_required)
  need=$(curl -fsS "$base/api/init" | _json needs_onboarding)
  info "live /api/init → version=$ver auth_required=$auth needs_onboarding=$need"
  case "$ver" in
    1.6.*) ok "running the 1.6 line" ;;
    *)     bad "expected a 1.6.x version, got $ver" ;;
  esac
}

phase_smoke() {
  section "smoke → live /api/init"
  curl -fsS "http://$REMOTE_HOST:$SERVICE_PORT/api/init" | sed 's/^/      /' || bad "no response"
  echo
}

# tiny JSON field reader (value of a top-level "key")
_json() {
  local key="$1"
  python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: sys.exit(0)
v=d.get('$key')
print('' if v is None else ('true' if v is True else ('false' if v is False else v)))"
}

# ---- dispatch -------------------------------------------------------------
PHASES=(); FULL=0; WITH_FRONTEND="${WITH_FRONTEND:-0}"
for a in "$@"; do
  case "$a" in
    --full) FULL=1 ;;
    --with-frontend) WITH_FRONTEND=1 ;;
    deploy|harness|pytest|live|smoke|all) PHASES+=("$a") ;;
    *) echo "unknown argument: $a" >&2; exit 2 ;;
  esac
done
[ ${#PHASES[@]} -eq 0 ] && PHASES=(all)

printf '%sremote-test%s  target=%s  app=%s  venv=%s\n' "$C_B" "$C_0" "$REMOTE" "$REMOTE_APP" "$VENV"
for p in "${PHASES[@]}"; do
  case "$p" in
    all)     phase_deploy; phase_harness; phase_pytest ;;
    deploy)  phase_deploy ;;
    harness) phase_harness ;;
    pytest)  phase_pytest ;;
    live)    phase_live ;;
    smoke)   phase_smoke ;;
  esac
done

section "summary"
printf '  %s%d passed%s, %s%d failed%s\n' "$C_G" "$PASS" "$C_0" \
  "$([ $FAIL -gt 0 ] && echo "$C_R" || echo "$C_G")" "$FAIL" "$C_0"
[ $FAIL -eq 0 ]
