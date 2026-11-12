#!/usr/bin/env bash
# Start a local Anvil node forked from Base Sepolia.
#
# A fork, not an empty chain: the real EAS contracts (0x4200…0021 / …0020)
# and the real Chainalysis sanctions oracle are already there, so the demo
# attests through production EAS code and screens against production data
# without needing a faucet.
#
# Idempotent. Stop with ./scripts/stop-dev-chain.sh.

set -euo pipefail
SCRIPT_TAG=dev-chain
# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

RPC_PORT="${DEV_ANVIL_PORT:-8545}"
RPC_URL="http://127.0.0.1:${RPC_PORT}"
FORK_URL="${DEV_FORK_URL:-https://sepolia.base.org}"
CHAIN_ID=84532
BLOCK_TIME="${DEV_BLOCK_TIME:-1}"

require_tools anvil cast curl
mkdir -p "$RUN_DIR"

rpc_answers() {
  curl -sf -X POST "$RPC_URL" -H 'Content-Type: application/json' \
    --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' >/dev/null 2>&1
}

FRESH_CHAIN=0
if rpc_answers; then
  if [ -f "$RUN_DIR/anvil.pid" ] && kill -0 "$(cat "$RUN_DIR/anvil.pid")" 2>/dev/null; then
    log "anvil already running on $RPC_URL (pid $(cat "$RUN_DIR/anvil.pid")); reusing"
  else
    fail "port $RPC_PORT is in use by a process this script did not start; set DEV_ANVIL_PORT"
  fi
else
  log "starting anvil fork of $FORK_URL on port $RPC_PORT"
  nohup anvil --fork-url "$FORK_URL" --port "$RPC_PORT" --chain-id "$CHAIN_ID" \
    --block-time "$BLOCK_TIME" >"$RUN_DIR/anvil.log" 2>&1 &
  echo $! >"$RUN_DIR/anvil.pid"
  FRESH_CHAIN=1
  for _ in $(seq 1 30); do
    rpc_answers && break
    sleep 1
  done
  rpc_answers || { tail -30 "$RUN_DIR/anvil.log" >&2; fail "anvil did not start"; }
  ok "anvil up (pid $(cat "$RUN_DIR/anvil.pid"))"
fi

code_size() { cast code "$1" --rpc-url "$RPC_URL" 2>/dev/null | wc -c | tr -d ' '; }
[ "$(code_size "$EAS_ADDRESS")" -gt 100 ] || fail "EAS is not present at $EAS_ADDRESS; the fork failed"
[ "$(code_size "$SANCTIONS_ORACLE_ADDRESS")" -gt 100 ] \
  || fail "the sanctions oracle is not present at $SANCTIONS_ORACLE_ADDRESS"
ok "EAS and the sanctions oracle are present on the fork"

# A reused chain keeps its state file, which also holds the deployed addresses.
if [ "$FRESH_CHAIN" = "1" ] || [ ! -f "$STATE_FILE" ]; then
  cat >"$STATE_FILE" <<STATE
# Local development chain state, written by scripts/dev-chain.sh. Not tracked.
DEV_RPC_URL=$RPC_URL
DEV_CHAIN_ID=$CHAIN_ID
DEV_FORK_URL=$FORK_URL
STATE
fi

cat >&2 <<SUMMARY

  Local chain ready
    RPC              $RPC_URL  (chain $CHAIN_ID, fork of Base Sepolia)
    EAS              $EAS_ADDRESS
    Sanctions oracle $SANCTIONS_ORACLE_ADDRESS
    Next             ./scripts/deploy-contracts.sh

SUMMARY
