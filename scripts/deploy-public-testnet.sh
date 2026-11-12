#!/usr/bin/env bash
# Deploy to Base Sepolia and publish two verifiable decision records.
#
#   1. registers the SettlementDecision schema if the chain does not have it
#   2. deploys a demo token and the escrow (deployer, owner and attester differ)
#   3. runs one approval and one rejection through a temporary local attester
#   4. writes deployments/<network>.json and examples/records/<network>/*.json
#   5. verifies both records against the public RPC in strict mode
#
# Keys are read from the environment or from .env and are never written to
# any file. See .env.example for the variables:
#
#   PUBLIC_DEPLOYER_PRIVATE_KEY   pays for deployment; receives no privileges
#   PUBLIC_OWNER_ADDRESS          escrow owner (address only)
#   PUBLIC_ATTESTER_PRIVATE_KEY   signs the two attestations
#   PUBLIC_BUYER_PRIVATE_KEY      deposits the demo tokens
#   PUBLIC_RPC_URL                optional, default https://sepolia.base.org
#
# Only the deployer needs testnet ETH: the script tops up the attester and
# the buyer from it when they are low.

set -euo pipefail
SCRIPT_TAG=public-testnet
# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

require_tools forge cast curl python3 uv

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

RPC="${PUBLIC_RPC_URL:-https://sepolia.base.org}"
NETWORK="${PUBLIC_NETWORK:-base-sepolia}"
: "${PUBLIC_DEPLOYER_PRIVATE_KEY:?set PUBLIC_DEPLOYER_PRIVATE_KEY}"
: "${PUBLIC_OWNER_ADDRESS:?set PUBLIC_OWNER_ADDRESS}"
: "${PUBLIC_ATTESTER_PRIVATE_KEY:?set PUBLIC_ATTESTER_PRIVATE_KEY}"
: "${PUBLIC_BUYER_PRIVATE_KEY:?set PUBLIC_BUYER_PRIVATE_KEY}"

DEPLOYER="$(cast wallet address "$PUBLIC_DEPLOYER_PRIVATE_KEY")"
ATTESTER="$(cast wallet address "$PUBLIC_ATTESTER_PRIVATE_KEY")"
BUYER="$(cast wallet address "$PUBLIC_BUYER_PRIVATE_KEY")"
OWNER="$PUBLIC_OWNER_ADDRESS"
REGISTERED_PAYEE="$(dev_address "$ROLE_PAYEE")"
UNREGISTERED_PAYEE="$(dev_address "$ROLE_IMPOSTOR")"

lower() { printf '%s' "$1" | tr 'A-F' 'a-f'; }
[ "$(lower "$OWNER")" != "$(lower "$ATTESTER")" ] || fail "owner and attester must be different addresses"
[ "$(lower "$OWNER")" != "$(lower "$DEPLOYER")" ] || fail "owner and deployer must be different addresses"

CHAIN_ID="$(cast chain-id --rpc-url "$RPC")"
[ "$CHAIN_ID" = "84532" ] || fail "expected Base Sepolia (84532), the RPC serves chain $CHAIN_ID"

MIN_WEI=2000000000000000      # 0.002 ETH per signing account
TOPUP_WEI=4000000000000000    # 0.004 ETH
NEED_WEI=20000000000000000    # 0.02 ETH on the deployer
balance() { cast balance "$1" --rpc-url "$RPC"; }
less_than() { python3 -c 'import sys; sys.exit(0 if int(sys.argv[1]) < int(sys.argv[2]) else 1)' "$1" "$2"; }

if less_than "$(balance "$DEPLOYER")" "$NEED_WEI"; then
  fail "the deployer $DEPLOYER holds less than 0.02 ETH on Base Sepolia; fund it from a faucet and run again"
fi
for account in "$ATTESTER" "$BUYER"; do
  if less_than "$(balance "$account")" "$MIN_WEI"; then
    log "topping up $account from the deployer"
    cast send "$account" --value "$TOPUP_WEI" --private-key "$PUBLIC_DEPLOYER_PRIVATE_KEY" \
      --rpc-url "$RPC" >/dev/null
  fi
done

[ -d contracts/lib/forge-std ] || ./scripts/install-contract-deps.sh

log "deploying to $NETWORK ($RPC)"
OUTPUT="$(
  cd contracts
  DEPLOYER_PRIVATE_KEY="$PUBLIC_DEPLOYER_PRIVATE_KEY" \
  ESCROW_OWNER_ADDRESS="$OWNER" \
  ATTESTER_ADDRESS="$ATTESTER" \
    forge script script/Deploy.s.sol --rpc-url "$RPC" --broadcast 2>&1
)" || { printf '%s\n' "$OUTPUT" >&2; fail "forge script failed"; }
value_of() { printf '%s\n' "$OUTPUT" | sed -n "s/^ *$1=//p" | tail -1; }
ESCROW="$(value_of SETTLEMENT_ESCROW_ADDRESS)"
TOKEN="$(value_of SETTLEMENT_TOKEN_ADDRESS)"
SCHEMA_UID="$(value_of EAS_SCHEMA_UID)"
[ -n "$ESCROW" ] && [ -n "$TOKEN" ] || { printf '%s\n' "$OUTPUT" >&2; fail "could not read the deployed addresses"; }
ok "escrow $ESCROW, token $TOKEN"

mkdir -p deployments "examples/records/$NETWORK" "$RUN_DIR"
python3 - "$NETWORK" "$ESCROW" "$TOKEN" "$SCHEMA_UID" "$OWNER" "$ATTESTER" <<'PY'
import json, sys
network, escrow, token, schema_uid, owner, attester = sys.argv[1:7]
explorer = "https://sepolia.basescan.org/address/" if network == "base-sepolia" else None
doc = {
    "network": network,
    "chain_id": 84532,
    "eas": "0x4200000000000000000000000000000000000021",
    "schema_uid": schema_uid,
    "escrow": escrow.lower(),
    "token": token.lower(),
    "token_symbol": "mUSDC",
    "token_decimals": 6,
    "owner": owner.lower(),
    "attester": attester.lower(),
}
if explorer:
    doc["links"] = {
        "escrow": explorer + escrow,
        "token": explorer + token,
        "schema": "https://base-sepolia.easscan.org/schema/view/" + schema_uid,
    }
with open(f"deployments/{network}.json", "w") as handle:
    json.dump(doc, handle, indent=2)
    handle.write("\n")
PY

# ---- a temporary attester for this deployment -------------------------------
PUBLIC_API_PORT="${PUBLIC_API_PORT:-8089}"
API="http://127.0.0.1:${PUBLIC_API_PORT}"
API_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
RECORDS="$RUN_DIR/public-records"
rm -rf "$RECORDS"
(
  cd apps/api
  ATTESTRWA_RPC_URL="$RPC" ATTESTRWA_CHAIN_ID=84532 ATTESTRWA_NETWORK="$NETWORK" \
  ATTESTRWA_ESCROW_ADDRESS="$ESCROW" \
  ATTESTRWA_ATTESTER_PRIVATE_KEY="$PUBLIC_ATTESTER_PRIVATE_KEY" \
  ATTESTRWA_API_KEYS="publisher:${API_KEY}" ATTESTRWA_RECORDS_DIR="$RECORDS" \
  nohup uv run uvicorn app.main:app --app-dir src --host 127.0.0.1 --port "$PUBLIC_API_PORT" \
    >"$RUN_DIR/public-api.log" 2>&1 &
  echo $! >"$RUN_DIR/public-api.pid"
)
trap 'stop_pid_file "$RUN_DIR/public-api.pid" "temporary attester"' EXIT
for _ in $(seq 1 40); do
  curl -fsS "$API/healthz" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "$API/healthz" >/dev/null 2>&1 || { tail -20 "$RUN_DIR/public-api.log" >&2; fail "the attester did not start"; }
[ "$(curl -fsS "$API/attest/healthz" | json_field "['status']")" = "ok" ] \
  || fail "the attester is not ready: $(curl -fsS "$API/attest/healthz")"

send() { cast send "$@" --rpc-url "$RPC" >/dev/null; }
AMOUNT=580000000

settle() { # name payee expected-decision
  local name="$1" payee="$2" expected="$3" salt deadline deal body response decision uid record
  salt="$(cast keccak "$NETWORK-$name-$(date +%s)-$RANDOM")"
  deadline=$(( $(cast block latest --field timestamp --rpc-url "$RPC") + 7 * 86400 ))
  log "$name: deposit for $payee"
  send "$TOKEN" "mint(address,uint256)" "$BUYER" "$AMOUNT" --private-key "$PUBLIC_BUYER_PRIVATE_KEY"
  send "$TOKEN" "approve(address,uint256)" "$ESCROW" "$AMOUNT" --private-key "$PUBLIC_BUYER_PRIVATE_KEY"
  send "$ESCROW" "deposit(bytes32,address,address,uint256,uint64)" \
    "$salt" "$payee" "$TOKEN" "$AMOUNT" "$deadline" --private-key "$PUBLIC_BUYER_PRIVATE_KEY"
  deal="$(cast call "$ESCROW" "computeDealId(address,bytes32)(bytes32)" "$BUYER" "$salt" --rpc-url "$RPC")"
  body="{\"chain_id\": 84532, \"escrow\": \"$ESCROW\", \"deal_id\": \"$deal\", \"declared\": {\"jurisdiction\": \"TH\"}}"
  response="$(curl -fsS -X POST "$API/attest/settlement" -H 'Content-Type: application/json' \
    -H "X-API-Key: $API_KEY" -d "$body")"
  decision="$(printf '%s' "$response" | json_field "['decision']")"
  uid="$(printf '%s' "$response" | json_field "['attestation_uid']")"
  [ "$decision" = "$expected" ] || fail "$name: expected $expected, got $decision"
  record="examples/records/$NETWORK/$name.json"
  curl -fsS "$API/records/$deal" | python3 -c 'import json,sys; json.dump(json.load(sys.stdin), sys.stdout, indent=2); print()' >"$record"
  if [ "$expected" = "approve" ]; then
    send "$ESCROW" "release(bytes32,bytes32)" "$deal" "$uid" --private-key "$PUBLIC_BUYER_PRIVATE_KEY"
  else
    send "$ESCROW" "refund(bytes32,bytes32)" "$deal" "$uid" --private-key "$PUBLIC_BUYER_PRIVATE_KEY"
  fi
  ok "$name: $decision, attestation $uid, settled, record $record"
}

settle approve "$REGISTERED_PAYEE" approve
settle reject "$UNREGISTERED_PAYEE" reject

log "verifying the published records against $RPC"
for record in "examples/records/$NETWORK"/*.json; do
  verify_record "$record" --rpc "$RPC" --policy "$POLICY_FILE" --registry "$REGISTRY_FILE" \
    --recheck-inputs --strict >/dev/null || fail "$record does not verify"
  ok "$record verified (strict)"
done

cat >&2 <<SUMMARY

  Published on $NETWORK
    Escrow       $ESCROW
    Token        $TOKEN
    Schema UID   $SCHEMA_UID
    Deployment   deployments/$NETWORK.json
    Records      examples/records/$NETWORK/approve.json, reject.json

  Anyone can now run:
    attestrwa verify examples/records/$NETWORK/approve.json --rpc $RPC

SUMMARY
