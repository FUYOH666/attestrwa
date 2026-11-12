#!/usr/bin/env bash
# Boot the whole local demo: forked chain, contracts, attester, web UI.
# Idempotent; stop with ./scripts/stop-demo-mode.sh.

set -euo pipefail
SCRIPT_TAG=demo
# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

require_tools anvil forge cast uv pnpm curl python3

./scripts/dev-chain.sh
load_state
if [ -z "${SETTLEMENT_ESCROW_ADDRESS:-}" ] \
  || [ "$(cast code "$SETTLEMENT_ESCROW_ADDRESS" --rpc-url "$DEV_RPC_URL" | wc -c | tr -d ' ')" -lt 100 ]; then
  ./scripts/deploy-contracts.sh
fi
ensure_api_up

web_answers() { curl -fsS "http://${API_HOST}:${WEB_PORT}/" >/dev/null 2>&1; }
if web_answers; then
  ok "web already answering on :${WEB_PORT}"
else
  log "starting the web UI on :${WEB_PORT} (log: .run/web.log)"
  [ -d apps/web/node_modules ] || (cd apps/web && pnpm install --frozen-lockfile)
  (
    cd apps/web
    NEXT_PUBLIC_NETWORK="anvil-fork" \
    NEXT_PUBLIC_RPC_URL="$DEV_RPC_URL" \
    NEXT_PUBLIC_ESCROW_ADDRESS="$SETTLEMENT_ESCROW_ADDRESS" \
    NEXT_PUBLIC_TOKEN_ADDRESS="$SETTLEMENT_TOKEN_ADDRESS" \
    ATTESTER_API_URL="http://${API_HOST}:${API_PORT}" \
    ATTESTER_API_KEY="$DEV_API_KEY" \
    nohup pnpm dev --port "$WEB_PORT" >"$RUN_DIR/web.log" 2>&1 &
    echo $! >"$RUN_DIR/web.pid"
  )
  for _ in $(seq 1 60); do
    web_answers && break
    sleep 1
  done
  web_answers || { tail -20 "$RUN_DIR/web.log" >&2; fail "the web UI did not start"; }
  ok "web up (pid $(cat "$RUN_DIR/web.pid"))"
fi

cat >&2 <<SUMMARY

  AttestRWA local demo is running
    Live settlement   http://localhost:${WEB_PORT}/settle
    Verify a record   http://localhost:${WEB_PORT}/verify
    Attester API      http://${API_HOST}:${API_PORT}/docs
    Chain             $DEV_RPC_URL  (fork of Base Sepolia)
    Escrow            $SETTLEMENT_ESCROW_ADDRESS

    Approve path      ./scripts/e2e_rwa_flow.sh
    Reject path       ./scripts/e2e_rwa_reject.sh
    Stop              ./scripts/stop-demo-mode.sh

SUMMARY
