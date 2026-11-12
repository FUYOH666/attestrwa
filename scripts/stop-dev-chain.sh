#!/usr/bin/env bash
# Stop the Anvil node started by scripts/dev-chain.sh. Only that process is
# touched; anything else listening on the port is left alone.

set -euo pipefail
SCRIPT_TAG=stop-dev-chain
# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

stop_pid_file "$RUN_DIR/anvil.pid" "anvil"
rm -f "$STATE_FILE" "$ROOT/deployments/anvil-fork.json"
log "local chain stopped"
