#!/usr/bin/env bash
# Revoke a decision on the local fork (only the attester that made it can).
# After a revocation the attester may be asked to decide again; the new
# record names the revoked attestation in `supersedes`.
#
#   ./scripts/revoke-attestation.sh 0x<attestation uid>

set -euo pipefail
SCRIPT_TAG=revoke
# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

[ $# -eq 1 ] || fail "usage: $0 0x<attestation uid>"
require_deployment

cast send "$EAS_ADDRESS" "revoke((bytes32,(bytes32,uint256)))" "($EAS_SCHEMA_UID,($1,0))" \
  --rpc-url "$DEV_RPC_URL" --private-key "$(dev_key "$ROLE_ATTESTER")" >/dev/null
ok "revoked $1"
