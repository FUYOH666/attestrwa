#!/usr/bin/env bash
# Install the Solidity dependencies at pinned versions into contracts/lib.
# contracts/lib is not tracked; this script is the single source of the pins
# (local development and CI both call it).
set -euo pipefail

export PATH="$HOME/.foundry/bin:$PATH"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/contracts"

FORGE_STD_TAG="v1.17.0"
OPENZEPPELIN_TAG="v5.0.2"
EAS_CONTRACTS_TAG="v1.4.0"

install() {
  local repo="$1" tag="$2" dir="$3"
  if [ -d "lib/$dir" ] && [ -f "lib/$dir/.attestrwa-pin" ] && [ "$(cat "lib/$dir/.attestrwa-pin")" = "$tag" ]; then
    echo "[deps] $dir already at $tag"
    return
  fi
  rm -rf "lib/$dir"
  echo "[deps] installing $repo@$tag"
  forge install "$repo@$tag" --no-git --shallow
  echo "$tag" > "lib/$dir/.attestrwa-pin"
}

mkdir -p lib
install foundry-rs/forge-std "$FORGE_STD_TAG" forge-std
install OpenZeppelin/openzeppelin-contracts "$OPENZEPPELIN_TAG" openzeppelin-contracts
install ethereum-attestation-service/eas-contracts "$EAS_CONTRACTS_TAG" eas-contracts

echo "[deps] done"
