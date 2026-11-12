#!/usr/bin/env bash
# End-to-end REJECT path on the local fork, including the attacks the v1
# design allowed:
#
#   deposit for an unregistered payee
#   -> the caller tries to describe the deal or declare screening results (refused)
#   -> the buyer tries to refund early without a decision (reverts)
#   -> attester rejects -> record verified -> release reverts -> buyer refunds
#
# Needs ./scripts/dev-chain.sh and ./scripts/deploy-contracts.sh first.

set -euo pipefail
SCRIPT_TAG=e2e-reject
# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

require_tools cast curl python3 uv
ensure_api_up

RPC="$DEV_RPC_URL"
ESCROW="$SETTLEMENT_ESCROW_ADDRESS"
TOKEN="$SETTLEMENT_TOKEN_ADDRESS"
BUYER="$(dev_address "$ROLE_BUYER")"
BUYER_KEY="$(dev_key "$ROLE_BUYER")"
IMPOSTOR="$(dev_address "$ROLE_IMPOSTOR")"
AMOUNT=580000000
SALT="$(cast keccak "reject-$(date +%s)-$RANDOM")"
DEADLINE=$(( $(cast block latest --field timestamp --rpc-url "$RPC") + 86400 ))

send() { cast send "$@" --rpc-url "$RPC" >/dev/null; }
must_revert() {
  local label="$1"; shift
  if cast send "$@" --rpc-url "$RPC" >/dev/null 2>&1; then
    fail "$label succeeded but must revert"
  fi
  ok "$label reverted"
}
balance_of() { cast call "$TOKEN" "balanceOf(address)(uint256)" "$1" --rpc-url "$RPC" | awk '{print $1}'; }
post_status() {
  curl -s -o /dev/null -w '%{http_code}' -X POST "http://${API_HOST}:${API_PORT}/attest/settlement" \
    -H 'Content-Type: application/json' -H "X-API-Key: $2" -d "$1"
}

log "1/6 buyer deposits $AMOUNT naming a payee that is not in the registry"
send "$TOKEN" "mint(address,uint256)" "$BUYER" "$AMOUNT" --private-key "$BUYER_KEY"
send "$TOKEN" "approve(address,uint256)" "$ESCROW" "$AMOUNT" --private-key "$BUYER_KEY"
BEFORE="$(balance_of "$BUYER")"
send "$ESCROW" "deposit(bytes32,address,address,uint256,uint64)" \
  "$SALT" "$IMPOSTOR" "$TOKEN" "$AMOUNT" "$DEADLINE" --private-key "$BUYER_KEY"
DEAL_ID="$(cast call "$ESCROW" "computeDealId(address,bytes32)(bytes32)" "$BUYER" "$SALT" --rpc-url "$RPC")"
ok "deal $DEAL_ID"

DEAL_JSON="\"chain_id\": $DEV_CHAIN_ID, \"escrow\": \"$ESCROW\", \"deal_id\": \"$DEAL_ID\""
HONEST_BODY="{$DEAL_JSON, \"declared\": {\"jurisdiction\": \"TH\"}}"
PAYEE_BODY="{$DEAL_JSON, \"payee_wallet\": \"$(dev_address "$ROLE_PAYEE")\", \"declared\": {\"jurisdiction\": \"TH\"}}"
DECLARED_BODY="{$DEAL_JSON, \"declared\": {\"jurisdiction\": \"TH\", \"payee_registered\": true}}"

expect_status() {
  local label="$1" expected="$2" body="$3" key="${4:-$DEV_API_KEY}" status
  status="$(post_status "$body" "$key")"
  [ "$status" = "$expected" ] || fail "$label: expected HTTP $expected, got $status"
  ok "$label -> $expected"
}

log "2/6 the attester refuses requests that try to steer it"
expect_status "request without a valid API key" 401 "$HONEST_BODY" wrong-key
expect_status "caller-supplied payee" 422 "$PAYEE_BODY"
expect_status "declared registry result" 422 "$DECLARED_BODY"

log "3/6 without a decision the buyer cannot take the deposit back before the deadline"
must_revert "early refund without a decision" "$ESCROW" "refund(bytes32,bytes32)" "$DEAL_ID" \
  0x0000000000000000000000000000000000000000000000000000000000000000 --private-key "$BUYER_KEY"

log "4/6 the attester decides from what the escrow, the registry and the oracle say"
RESPONSE="$(curl -fsS -X POST "http://${API_HOST}:${API_PORT}/attest/settlement" \
  -H 'Content-Type: application/json' -H "X-API-Key: ${DEV_API_KEY}" \
  -d "$HONEST_BODY")"
DECISION="$(printf '%s' "$RESPONSE" | json_field "['decision']")"
FAILED="$(printf '%s' "$RESPONSE" | json_field "['failed_rules']")"
UID_="$(printf '%s' "$RESPONSE" | json_field "['attestation_uid']")"
[ "$DECISION" = "reject" ] || fail "expected reject, got $DECISION"
ok "decision REJECT, failed rules $FAILED, attestation $UID_"

log "5/6 the rejection is as verifiable as an approval"
mkdir -p "$RUN_DIR"
RECORD="$RUN_DIR/last-reject.json"
curl -fsS "http://${API_HOST}:${API_PORT}/records/${DEAL_ID}" >"$RECORD"
verify_record "$RECORD" --rpc "$RPC" --policy "$POLICY_FILE" --registry "$REGISTRY_FILE" \
  --recheck-inputs --strict
ok "record verified (strict)"

log "6/6 the rejection cannot release the funds, and lets the buyer refund"
must_revert "release on a REJECT decision" "$ESCROW" "release(bytes32,bytes32)" "$DEAL_ID" "$UID_" \
  --private-key "$BUYER_KEY"
send "$ESCROW" "refund(bytes32,bytes32)" "$DEAL_ID" "$UID_" --private-key "$BUYER_KEY"
AFTER="$(balance_of "$BUYER")"
[ "$AFTER" = "$BEFORE" ] || fail "buyer balance is $AFTER, expected $BEFORE"
[ "$(balance_of "$IMPOSTOR")" = "0" ] || fail "the unregistered payee received funds"
ok "buyer refunded in full; the unregistered payee received nothing"

cat >&2 <<SUMMARY

  REJECT path: PASSED
    deal         $DEAL_ID
    attestation  $UID_
    record       ${RECORD#"$ROOT"/}

SUMMARY
