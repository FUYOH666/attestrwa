#!/usr/bin/env bash
# End-to-end APPROVE path on the local fork:
#
#   deposit -> attester decides -> record verified independently -> release
#
# Needs ./scripts/dev-chain.sh and ./scripts/deploy-contracts.sh first.

set -euo pipefail
SCRIPT_TAG=e2e-approve
# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

require_tools cast curl python3 uv
ensure_api_up

RPC="$DEV_RPC_URL"
ESCROW="$SETTLEMENT_ESCROW_ADDRESS"
TOKEN="$SETTLEMENT_TOKEN_ADDRESS"
BUYER="$(dev_address "$ROLE_BUYER")"
BUYER_KEY="$(dev_key "$ROLE_BUYER")"
PAYEE="$(dev_address "$ROLE_PAYEE")"
AMOUNT=580000000
SALT="$(cast keccak "approve-$(date +%s)-$RANDOM")"
DEADLINE=$(( $(cast block latest --field timestamp --rpc-url "$RPC") + 86400 ))

send() { cast send "$@" --rpc-url "$RPC" >/dev/null; }
balance_of() { cast call "$TOKEN" "balanceOf(address)(uint256)" "$1" --rpc-url "$RPC" | awk '{print $1}'; }

log "1/5 buyer mints demo tokens and deposits $AMOUNT for the registered payee"
send "$TOKEN" "mint(address,uint256)" "$BUYER" "$AMOUNT" --private-key "$BUYER_KEY"
send "$TOKEN" "approve(address,uint256)" "$ESCROW" "$AMOUNT" --private-key "$BUYER_KEY"
send "$ESCROW" "deposit(bytes32,address,address,uint256,uint64)" \
  "$SALT" "$PAYEE" "$TOKEN" "$AMOUNT" "$DEADLINE" --private-key "$BUYER_KEY"
DEAL_ID="$(cast call "$ESCROW" "computeDealId(address,bytes32)(bytes32)" "$BUYER" "$SALT" --rpc-url "$RPC")"
ok "deal $DEAL_ID"

log "2/5 the attester is told which deal to look at, and nothing else"
DEAL_JSON="\"chain_id\": $DEV_CHAIN_ID, \"escrow\": \"$ESCROW\", \"deal_id\": \"$DEAL_ID\""
BODY="{$DEAL_JSON, \"declared\": {\"jurisdiction\": \"TH\"}}"
OTHER_BODY="{$DEAL_JSON, \"declared\": {\"jurisdiction\": \"US\"}}"
RESPONSE="$(curl -fsS -X POST "http://${API_HOST}:${API_PORT}/attest/settlement" \
  -H 'Content-Type: application/json' -H "X-API-Key: ${DEV_API_KEY}" -d "$BODY")"
DECISION="$(printf '%s' "$RESPONSE" | json_field "['decision']")"
UID_="$(printf '%s' "$RESPONSE" | json_field "['attestation_uid']")"
[ "$DECISION" = "approve" ] || fail "expected approve, got $DECISION"
ok "decision APPROVE, attestation $UID_"

log "3/5 anyone can check the record against the chain, the policy and the registry"
mkdir -p "$RUN_DIR"
RECORD="$RUN_DIR/last-approve.json"
curl -fsS "http://${API_HOST}:${API_PORT}/records/${DEAL_ID}" >"$RECORD"
verify_record "$RECORD" --rpc "$RPC" --policy "$POLICY_FILE" --registry "$REGISTRY_FILE" \
  --recheck-inputs --strict
ok "record verified (strict)"

log "4/5 a second request does not create a second decision"
REUSED="$(curl -fsS -X POST "http://${API_HOST}:${API_PORT}/attest/settlement" \
  -H 'Content-Type: application/json' -H "X-API-Key: ${DEV_API_KEY}" -d "$OTHER_BODY" \
  | json_field "['reused']")"
[ "$REUSED" = "True" ] || fail "the attester issued a second decision for the same deal"
ok "the live decision was returned unchanged"

log "5/5 release pays the payee"
BEFORE="$(balance_of "$PAYEE")"
send "$ESCROW" "release(bytes32,bytes32)" "$DEAL_ID" "$UID_" --private-key "$BUYER_KEY"
AFTER="$(balance_of "$PAYEE")"
[ $(( AFTER - BEFORE )) -eq "$AMOUNT" ] || fail "payee received $(( AFTER - BEFORE )), expected $AMOUNT"
ok "payee received $AMOUNT"

cat >&2 <<SUMMARY

  APPROVE path: PASSED
    deal         $DEAL_ID
    attestation  $UID_
    record       ${RECORD#"$ROOT"/}

SUMMARY
