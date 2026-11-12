# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, Cursor, Copilot, …) working in this repository. Humans: see [CONTRIBUTING.md](CONTRIBUTING.md).

## What this is

AttestRWA is a format and a verifier for **decision records**: why a compliance decision about a stablecoin settlement was made, anchored on-chain with EAS. The repository holds the specification, the reference library and verifier, a reference escrow contract, a reference attester service and a web UI. Everything is testnet-only; nothing here is audited or deployed to mainnet.

## Layout

| Path | What |
|---|---|
| `spec/` | Decision Record v0.1: normative text, JSON Schema, EAS schema string, test vectors. |
| `packages/attestrwa/` | Python library and the `attestrwa` command (canonical JSON, policy packs, records, verifier). |
| `contracts/` | Foundry project: `SettlementEscrow.sol`, `MockUSDC.sol`, tests against the real EAS contracts. |
| `apps/api/` | FastAPI attester: reads a deal from the escrow, builds and anchors the record. |
| `apps/web/` | Next.js UI: `/settle` (live flow) and `/verify` (browser verifier). |
| `data/policies/`, `data/registry/` | Demo policy packs and the demo payee registry (synthetic). |
| `scripts/` | Local fork, deployment, end-to-end paths, public testnet publishing. |
| `docs/` | Architecture, API, threat model, policy packs, landscape, roadmap. |

## Commands

```bash
# Library and verifier
cd packages/attestrwa && uv sync && uv run pytest -q
uvx ruff@0.17.4 check . && uvx ruff@0.17.4 format --check .

# Attester
cd apps/api && uv sync && uv run pytest -q

# Contracts (dependencies are pinned by the script, not vendored)
./scripts/install-contract-deps.sh
cd contracts && forge fmt --check && forge test

# Web
cd apps/web && pnpm install --frozen-lockfile && pnpm test && pnpm run typecheck && pnpm run build

# End to end on a local fork of Base Sepolia
./scripts/dev-chain.sh && ./scripts/deploy-contracts.sh
./scripts/e2e_rwa_flow.sh && ./scripts/e2e_rwa_reject.sh
./scripts/stop-demo-mode.sh
```

CI (`.github/workflows/ci.yml`) runs a secret and personal-path scan, the contract tests and Slither, both Python suites with ruff, and the web build. The end-to-end paths run in `.github/workflows/e2e.yml` on demand and weekly, because they need the public RPC.

Unit tests must not reach the network. Only the scripts and the `e2e` workflow do.

## Rules

- **The record format is a contract.** A change that alters the canonical bytes of an existing record, the meaning of a member or the rule semantics needs a new spec version. `spec/test-vectors/` pins the bytes; regenerate them with `scripts/make-test-vectors.py` only when the format or the demo policy changes on purpose, and say so in the changelog.
- **One schema string.** `spec/eas-schema.txt` is the source; the library, the Foundry tests and the deploy script check or read it. Do not copy the string elsewhere.
- **The decision is a pure function of policy and inputs.** Do not add decision logic to the attester. If an outcome must change, it changes in the policy or in `attestrwa.record.build_record`, and the verifier must reproduce it.
- **The attester never takes facts about a deal from the caller.** Buyer, payee, token and amount come from the escrow. Inputs come from the source the policy declares.
- **Fail closed.** An unreadable source or a failed transaction is an error, never a default value or a decision.
- **The escrow moves funds only to the deal's payee or its buyer.** Any contract change must keep the invariants in `contracts/test/SettlementEscrow.invariants.t.sol` and Slither clean at medium and above.
- **Records are untrusted input.** The verifier and `POST /verify` must report a malformed record as not verified; they must not raise.
- Use `uv` for Python and `pnpm` for the web app. Do not vendor `contracts/lib`.
- Do not stop or restart services the user is running. The scripts keep their own pids in `.run/` and touch only those; use `DEV_ANVIL_PORT`, `ATTESTRWA_API_PORT` and `ATTESTRWA_WEB_PORT` if the default ports are taken.
- No secrets, private keys, absolute personal paths or internal addresses in tracked files (CI greps for them). The only key material in the repository is the publicly known Foundry development mnemonic, used for the local fork.
- Do not claim an audit, a mainnet deployment, a partnership or regulatory acceptance in any document.
- Keep `CHANGELOG.md` updated for user-visible changes. Documentation is in English; `README.ru.md` mirrors the README in Russian.
