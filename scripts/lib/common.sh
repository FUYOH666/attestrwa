# Shared helpers for the AttestRWA scripts. Source this file; do not run it.
# shellcheck shell=bash

export PATH="$HOME/.foundry/bin:$PATH"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

RUN_DIR="$ROOT/.run"
STATE_FILE="${ATTESTRWA_STATE_FILE:-$ROOT/.dev-chain.state}"

EAS_ADDRESS="0x4200000000000000000000000000000000000021"
EAS_SCHEMA_REGISTRY_ADDRESS="0x4200000000000000000000000000000000000020"
# Chainalysis sanctions oracle on Base Sepolia (inherited by the fork).
SANCTIONS_ORACLE_ADDRESS="0x40C57923924B5c5c5455c48D93317139ADDaC8fb"

# The publicly known Foundry/Hardhat development mnemonic. These accounts are
# for the local fork only and must never hold value on a real network.
DEV_MNEMONIC="test test test test test test test test test test test junk"
DEV_API_KEY="local-demo-key"

API_HOST=127.0.0.1
API_PORT="${ATTESTRWA_API_PORT:-8080}"
WEB_PORT="${ATTESTRWA_WEB_PORT:-3000}"

POLICY_FILE="data/policies/settlement-demo-v2.yaml"
REGISTRY_FILE="data/registry/payees.json"

log()  { printf '\033[1;36m[%s]\033[0m %s\n' "${SCRIPT_TAG:-attestrwa}" "$*" >&2; }
ok()   { printf '\033[1;32m[ok]\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

require_tools() {
  local tool
  for tool in "$@"; do
    command -v "$tool" >/dev/null 2>&1 || fail "'$tool' is not on PATH"
  done
}

dev_key() { cast wallet private-key --mnemonic "$DEV_MNEMONIC" --mnemonic-index "$1"; }
dev_address() { cast wallet address "$(dev_key "$1")"; }

# Role -> account index in the development mnemonic.
ROLE_DEPLOYER=0
ROLE_BUYER=1
ROLE_PAYEE=2      # listed in data/registry/payees.json
ROLE_IMPOSTOR=3   # not listed: the "wrong payee" of the reject scenario
ROLE_ATTESTER=4
ROLE_OWNER=5

load_state() {
  [ -f "$STATE_FILE" ] || fail "$STATE_FILE not found. Run ./scripts/dev-chain.sh first."
  # shellcheck disable=SC1090
  source "$STATE_FILE"
}

require_deployment() {
  load_state
  : "${SETTLEMENT_ESCROW_ADDRESS:?contracts not deployed; run ./scripts/deploy-contracts.sh}"
  : "${SETTLEMENT_TOKEN_ADDRESS:?contracts not deployed; run ./scripts/deploy-contracts.sh}"
}

api_healthy() { curl -fsS "http://${API_HOST}:${API_PORT}/healthz" >/dev/null 2>&1; }

# Start the attester against the local fork unless one already answers.
ensure_api_up() {
  require_deployment
  if api_healthy; then
    local served
    served="$(curl -fsS "http://${API_HOST}:${API_PORT}/attest/healthz" | json_field "['escrow']" || true)"
    if [ "$served" = "$(printf '%s' "$SETTLEMENT_ESCROW_ADDRESS" | tr 'A-F' 'a-f')" ]; then
      ok "attester already answering on :${API_PORT}"
      return 0
    fi
    [ -f "$RUN_DIR/api.pid" ] \
      || fail "port ${API_PORT} is used by a service this script did not start; set ATTESTRWA_API_PORT"
    log "the running attester serves another escrow; restarting it"
    stop_pid_file "$RUN_DIR/api.pid" "attester"
    rm -rf "$RUN_DIR/records"
  fi
  mkdir -p "$RUN_DIR"
  log "starting the attester on :${API_PORT} (log: .run/api.log)"
  (
    cd "$ROOT/apps/api"
    ATTESTRWA_RPC_URL="$DEV_RPC_URL" \
    ATTESTRWA_CHAIN_ID="$DEV_CHAIN_ID" \
    ATTESTRWA_NETWORK="anvil-fork" \
    ATTESTRWA_ESCROW_ADDRESS="$SETTLEMENT_ESCROW_ADDRESS" \
    ATTESTRWA_SANCTIONS_ORACLE="$SANCTIONS_ORACLE_ADDRESS" \
    ATTESTRWA_ATTESTER_PRIVATE_KEY="$(dev_key "$ROLE_ATTESTER")" \
    ATTESTRWA_API_KEYS="local-demo:${DEV_API_KEY}" \
    ATTESTRWA_RECORDS_DIR="$RUN_DIR/records" \
    nohup uv run uvicorn app.main:app --app-dir src --host "$API_HOST" --port "$API_PORT" \
      >"$RUN_DIR/api.log" 2>&1 &
    echo $! >"$RUN_DIR/api.pid"
  )
  local _
  for _ in $(seq 1 40); do
    if api_healthy; then
      ok "attester healthy (pid $(cat "$RUN_DIR/api.pid"))"
      return 0
    fi
    sleep 1
  done
  tail -20 "$RUN_DIR/api.log" >&2
  fail "the attester did not become healthy"
}

stop_pid_file() {
  local file="$1" label="$2" pid
  [ -f "$file" ] || return 0
  pid="$(cat "$file")"
  if kill -0 "$pid" 2>/dev/null; then
    log "stopping $label (pid $pid)"
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$file"
}

# Run the reference verifier from the repository checkout.
verify_record() {
  uv run --project "$ROOT/packages/attestrwa" attestrwa verify "$@"
}

json_field() { python3 -c 'import json,sys; print(json.load(sys.stdin)'"$1"')'; }
