#!/usr/bin/env bash
# Demonstrate policy evolution: same deal, different eligibility proofs.
# Escrow contract state is not modified — attester policy packs change outcomes.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/apps/api"

log() { printf '[policy-evolution] %s\n' "$*" >&2; }

log "Running pytest policy evolution simulation…"
uv run pytest -q tests/test_policy_evolution.py tests/test_policy_provenance.py

log "Done. Core principle: migrate eligibility proofs, not escrow state."
log "See docs/POLICY_EVOLUTION.md"
