#!/usr/bin/env bash
# Deploy the demo token and the escrow to the local fork, registering the
# SettlementDecision schema if the chain does not have it yet.
#
# Three different development accounts are used on purpose: the deployer gets
# no privileges, the owner manages the attester list, the attester only attests.

set -euo pipefail
SCRIPT_TAG=deploy
# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

require_tools forge cast python3
load_state
[ -d contracts/lib/forge-std ] || ./scripts/install-contract-deps.sh

log "deploying to $DEV_RPC_URL"
OUTPUT="$(
  cd contracts
  DEPLOYER_PRIVATE_KEY="$(dev_key "$ROLE_DEPLOYER")" \
  ESCROW_OWNER_ADDRESS="$(dev_address "$ROLE_OWNER")" \
  ATTESTER_ADDRESS="$(dev_address "$ROLE_ATTESTER")" \
    forge script script/Deploy.s.sol --rpc-url "$DEV_RPC_URL" --broadcast 2>&1
)" || { printf '%s\n' "$OUTPUT" >&2; fail "forge script failed"; }

value_of() { printf '%s\n' "$OUTPUT" | sed -n "s/^ *$1=//p" | tail -1; }
ESCROW="$(value_of SETTLEMENT_ESCROW_ADDRESS)"
TOKEN="$(value_of SETTLEMENT_TOKEN_ADDRESS)"
SCHEMA_UID="$(value_of EAS_SCHEMA_UID)"
[ -n "$ESCROW" ] && [ -n "$TOKEN" ] && [ -n "$SCHEMA_UID" ] \
  || { printf '%s\n' "$OUTPUT" >&2; fail "could not read the deployed addresses"; }

# Drop any addresses from an earlier deployment, then record the new ones.
grep -v -E '^(SETTLEMENT_ESCROW_ADDRESS|SETTLEMENT_TOKEN_ADDRESS|EAS_SCHEMA_UID)=' "$STATE_FILE" \
  >"$STATE_FILE.tmp" || true
{
  cat "$STATE_FILE.tmp"
  echo "SETTLEMENT_ESCROW_ADDRESS=$ESCROW"
  echo "SETTLEMENT_TOKEN_ADDRESS=$TOKEN"
  echo "EAS_SCHEMA_UID=$SCHEMA_UID"
} >"$STATE_FILE"
rm -f "$STATE_FILE.tmp"

mkdir -p deployments
python3 - "$ESCROW" "$TOKEN" "$SCHEMA_UID" "$(dev_address "$ROLE_OWNER")" \
  "$(dev_address "$ROLE_ATTESTER")" <<'PY'
import json, sys
escrow, token, schema_uid, owner, attester = sys.argv[1:6]
json.dump(
    {
        "network": "anvil-fork",
        "chain_id": 84532,
        "eas": "0x4200000000000000000000000000000000000021",
        "schema_uid": schema_uid,
        "escrow": escrow.lower(),
        "token": token.lower(),
        "token_symbol": "mUSDC",
        "token_decimals": 6,
        "owner": owner.lower(),
        "attester": attester.lower(),
        "sanctions_oracle": "0x40c57923924b5c5c5455c48d93317139addac8fb",
    },
    open("deployments/anvil-fork.json", "w"),
    indent=2,
)
open("deployments/anvil-fork.json", "a").write("\n")
PY

cat >&2 <<SUMMARY

  Contracts deployed
    SettlementEscrow $ESCROW
    Demo token       $TOKEN  (mUSDC, anyone can mint)
    Schema UID       $SCHEMA_UID
    Owner            $(dev_address "$ROLE_OWNER")
    Attester         $(dev_address "$ROLE_ATTESTER")
    Next             ./scripts/e2e_rwa_flow.sh  or  ./scripts/demo-mode.sh

SUMMARY
