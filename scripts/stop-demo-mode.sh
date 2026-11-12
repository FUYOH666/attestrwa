#!/usr/bin/env bash
# Stop what ./scripts/demo-mode.sh (or the e2e scripts) started. Only the
# processes recorded in .run/ are stopped.

set -euo pipefail
SCRIPT_TAG=stop-demo
# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

stop_pid_file "$RUN_DIR/web.pid" "web UI"
stop_pid_file "$RUN_DIR/api.pid" "attester"
./scripts/stop-dev-chain.sh
rm -rf "$RUN_DIR/records"
log "demo stopped"
