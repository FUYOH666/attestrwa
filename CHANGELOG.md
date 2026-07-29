# Changelog

## Unreleased

### Added
- Policy Evolution Proof Pack:
  `policy_pack_id` + `policy_hash` on `POST /attest/settlement` (included in
  `evidence_hash`), `docs/POLICY_EVOLUTION.md`, `docs/PRODUCTION_ROADMAP.md`,
  `data/policies/asean-property-settlement-v1-strict.yaml`,
  `scripts/simulate-policy-evolution.sh`, `scripts/run_rwa_scenarios.py`,
  `docs/RWA_SCENARIO_REPORT.md`, tests `test_policy_provenance.py` /
  `test_policy_evolution.py`.
- Life-flow readiness (May 2026):
  `docs/FOR_INTEGRATORS.md`, `docs/INBOUND_PLAYBOOK.md`, `docs/LAYERED_TRUST.md`,
  `docs/MULTI_ATTESTER.md`, `FUNDING.md`.
- `scripts/deploy-public-testnet.sh`, `scripts/public-attestation-smoke.sh`,
  `scripts/demo-composed-flow.sh`.
- `examples/composed-eligibility-settlement/` — mock eligibility + settlement demo.
- `apps/api/tests/test_policy_packs.py` — ASEAN policy pack vectors.
- `TaintProvider` protocol + `ChainalysisStubProvider` in `wallet_taint.py`.
- Extended `GET /attest/healthz` with `policy_file`, `repo_version`, `dev_chain_reachable`.
- `docs/outreach/linkedin-redwan-issue-97.md` — LinkedIn follow-up after EEA issue #97.

### Changed
- EEA Shibui outreach: issue #97 response logged; draft issue in
  `docs/OUTREACH_TARGETS.md` no longer asks to register settlement topics in
  Shibui repo; `docs/STANDARDS_ALIGNMENT.md` Action 1 marked closed/follow-up.
- `.env.example` rebranded to `ATTESTRWA_*` (legacy `BANKABLE_*` aliases in config).
- `data/policies/asean-property-settlement-v1.yaml` — valid Compliance DSL (`rules[].require`).
- README: integrator link, public testnet proof section.
- URL hygiene: active docs use `attestrwa` repo name (not `bankable-property-network`).
- Ecosystem research pack (May 2026 OSS strategy execution):
  `docs/INTEGRATION_OPPORTUNITY_MATRIX.md`, `docs/ECOSYSTEM_RESEARCH.md` (42
  repo cards), `docs/STANDARDS_ALIGNMENT.md`, `docs/COMPARISON_EVIDENCE.md`,
  `docs/QUANTUM_LEAP_BETS.md`, `docs/OSS_OPERATING_PLAN_90DAY.md`,
  `docs/PIVOT.md`, `docs/OUTREACH_TARGETS.md`,
  `docs/rfc/0001-settlement-eligibility-composition.md`.
- `examples/integrate-centrifuge-hook/README.md` — Centrifuge hook cookbook.
- `data/policies/asean-property-settlement-v1.yaml` — first Compliance DSL
  policy pack (ASEAN property vertical).
- README pivot diagram + links to ecosystem docs.
- `docs/PITCH_CHEATSHEET.md` — one-page printable stage / hallway pitch (prior unreleased).
- `docs/PROJECT_DESCRIPTION.md` — hackathon registration / project summary (prior unreleased).
- `docs/pitch-deck.html` + `docs/AttestRWA-PITCH-DECK.pdf` — 7-slide pitch deck (prior unreleased).

### Changed
- `docs/COMPARISON.md` — cross-link to empirical evidence doc.
- GitHub repository renamed to [`FUYOH666/attestrwa`](https://github.com/FUYOH666/attestrwa);
  topics updated (`settlement-attestation`, `attestrwa`, …).
- Timeline copy: removed fictional "six weeks" / Week 0–3 planning labels
  from README, web UI, demo script, and project description (prior unreleased).

## v1.0.0-polish.2 — 2026-05-21 (branch `v1/attestation-layer`)

**Hackathon mode: self-contained demo, no faucet dependency.** When the
public Base Sepolia faucets gated us out (Coinbase signup broken,
QuickNode requires mainnet balance), we pivoted to a fully reproducible
local demo that still runs the **real EAS protocol bytecode** from the
Anvil fork of Base Sepolia. Recording-ready in two paths.

### Added
- `scripts/demo-mode.sh` — one-command stack boot. Composes
  `dev-chain.sh` + `deploy-contracts.sh` + FastAPI uvicorn + Next.js
  dev server. Idempotent across restarts. Prints a colourful
  `DEMO READY` block listing every address and URL the recording needs.
- `scripts/stop-demo-mode.sh` — clean shutdown of all four background
  processes (web, API, contracts/anvil are torn down via the existing
  `stop-dev-chain.sh`).
- `docs/HACKATHON_RECORDING_GUIDE.md` (~280 LOC) — two recording paths:
  - **Path B (recommended)**: terminal-only 60 s record. Two e2e
    scripts + one `cast code` proof + `git log`. Zero browser variables.
  - **Path A (cinematic)**: 90 s UI + MetaMask + wallet flow. Includes
    one-time MetaMask network + buyer-account import.
  Each path has a per-second timing table, voiceover lines, and a
  one-liner backup if anything misbehaves mid-recording.

### Updated
- `scripts/deploy-contracts.sh` — removed `--silent` from the
  `forge script` call. The script parses `MockUSDC: 0x…` and
  `SettlementEscrow: 0x…` lines from stdout; `--silent` was suppressing
  exactly those lines, so the wrapper failed to capture addresses.
- `scripts/stop-dev-chain.sh` — replaced the `…` ellipsis (U+2026) in
  log strings with ASCII `...`. Bash on macOS misparsed `$pid…` under
  `set -u` and aborted with `pid: unbound variable`. ASCII keeps the
  scripts portable across shells.
- `README.md` — quickstart section rewritten around `./scripts/demo-mode.sh`
  + the recording guide pointer. New explainer block: "Why this works
  without a faucet" — Anvil fork inherits real EAS bytecode (4,121 bytes)
  at `0x4200…0021`.
- Archived three legacy v0.5 artefacts that referenced the WhatsApp
  bridge (now in `archive/v0.5/`):
  `scripts/docker-up.sh`, `scripts/docker-smoke.sh`, the entire `infra/`
  folder (`docker-compose.yml`).

### Verified end-to-end on a fresh `demo-mode.sh` boot
- Happy path  — UID `0x42dfd8f7a368c8ac50a863bcea8f651d4f05fbffe2dd97384dce9f031b70be3c`
  - tx `0x888af9edfb74fa70cf36451180ffe2dc1c40f7583183fbdd7e0150d1aee16830`
  - Payee final balance **580,000,000 mUSDC base units (580 USDC)**
- Reject path — UID `0xd32db699e19025594ef92fa8b3d147602cd04ed7dc0d4bbc8cc51666fa6a31a6`
  - tx `0x638fe5840f57c6c93034e481aaadde76ad5795557c1f28586027f892a2b8bf21`
  - Impostor balance **0**, buyer refund **280,000,000 base units**
- `forge test` = 33/33; `uv run pytest -q` = 62/62; slither 0 findings
  (CI confirms on every push to `v1/attestation-layer`).

### Hackathon submission posture
- **Live recorded demo (85 seconds, vertical, English captions):**
  <https://youtube.com/shorts/BipB2qPzZz0>. Walks the full
  `demo-mode.sh` boot, the happy-path E2E (attestation UID
  `0x6d60c402…`), the reject-path E2E (attestation UID `0xf235c4eb…`),
  the `cast code` proof of real EAS bytecode at `0x4200…0021`
  (4,121 bytes), and the 8-commit pivot history with the `v1.0.0` tag.
- Local demo: `./scripts/demo-mode.sh` reproduces every frame of the
  recording on any laptop in ~35 s.
- Real-testnet deploy (Phase 3): deferred until any Base Sepolia faucet
  cooperates. README + ATTESTATION_SCHEMA + ROADMAP all already explain
  this is a one-line env-var flip.
- Public Vercel + Render deploys (Phase 4): scoped out of v1.0.0;
  re-enter as Q3 2026 issues post-hackathon.

## v1.0.0-polish.1 — 2026-05-20 (branch `v1/attestation-layer`)

Finalization polish on top of the `v1.0.0` tag. No tag bump yet — these
commits become `v1.0.0-final` once Phase 3 (real-testnet deploy) and
Phase 4 (Vercel + Render) land. All previous green states preserved.

### Added — Phase 1 (CI) + Phase 2 (OSS hygiene) — commit `74236ca`

- `.github/workflows/ci.yml`: three parallel jobs — `contracts` (forge
  build + test + gas report), `backend` (uv sync + pytest), `slither`
  (crytic/slither-action with our remappings, fail-on=medium).
- `.github/PULL_REQUEST_TEMPLATE.md`: structured checkboxes (forge,
  pytest, slither, e2e, CHANGELOG, no-secrets).
- `.github/ISSUE_TEMPLATE/bug.yml` + `feature.yml`: structured forms with
  area dropdown, repro, env, non-goals reminder.
- `.github/CODEOWNERS`: `* @FUYOH666`.
- Root `CONTRIBUTING.md`: quickstart + verification checklist + commit
  conventions + accepted/rejected change types.
- Root `CODE_OF_CONDUCT.md`: Contributor Covenant 2.1.
- Root `SECURITY.md`: pointer to `docs/SECURITY.md`, GitHub Security
  Advisory link, response process, explicit out-of-scope list.
- `README.md`: replaced v1.0.0-rc placeholder badge with ten content-
  bearing badges (CI status, forge 33/33, pytest 62/62, slither 0,
  solidity 0.8.26, foundry 1.7.1, network, EAS schema, license,
  hackathon).

### Added — Phase 5 (wallet UI) + Phase 9 prep (comparison)

- `docs/COMPARISON.md`: full feature comparison vs Centrifuge, Maple,
  RealT, Ondo, Polytrade — explicit "we are the layer above tokenization"
  positioning. Includes honest weakness section.
- `apps/web` web3 dependencies: `wagmi@^2`, `viem@^2`,
  `@rainbow-me/rainbowkit@^2`, `@tanstack/react-query@^5` (+ ~140 transitive deps).
- `apps/web/src/lib/contracts.ts`: minimal ABIs for MockUSDC + Settlement
  Escrow, default addresses from the dev fork deployment (overridable via
  `NEXT_PUBLIC_*` env), two named scenarios (`happy`, `rejectPayee`).
- `apps/web/src/app/providers.tsx`: RainbowKit + wagmi + react-query
  providers, baseSepolia chain config, SSR-safe.
- `apps/web/src/app/layout.tsx`: AttestRWA metadata, OpenGraph, providers
  wrapping.
- `apps/web/src/app/rwa-settlement-live/page.tsx` (~340 LOC): single
  cinematic demo screen with `ConnectButton`, scenario selector, six-step
  action row (mint / approve / deposit / attest / release / refund),
  live buyer & payee balances (4 s refetch), decision panel with EAS
  Scan + BaseScan deep links, compliance rule table, activity log.
- `apps/web/src/app/globals.css`: appended `.live`, `.scenario-grid`,
  `.action-row`, `.decision-*`, `.rules`, `.logs` block (~150 LOC).
- `apps/web/src/app/page.tsx`: hero now includes a CTA button to
  `/rwa-settlement-live`.
- `apps/web/tsconfig.json`: `paths` mapping for `@/*` (no deprecated
  `baseUrl`).

### Verified
- `pnpm run typecheck` (apps/web): clean.
- `pnpm run build` (apps/web): compiled successfully, 2 static routes
  (`/`, `/rwa-settlement-live`) prerendered.
- `forge test` (contracts): 33/33 still green.
- `uv run pytest -q` (apps/api): 62/62 still green.
- No secrets in any commit.

## v1.0.0 — 2026-05-20 (branch `v1/attestation-layer`)

**Hackathon-ready: Week 3 done.** Reject-path end-to-end flow, Farcaster
Frame distribution surface, Slither audit pass (0 findings), Dune query
pack, expanded threat model, and README quickstart. All previous green
states preserved.

### Added
- `scripts/e2e_rwa_reject.sh` — reject path end-to-end: buyer points to
  the impostor `SRL Holding 2026` wallet, attester signs the EAS
  attestation with `payeeVerified=false`, escrow refuses release, buyer
  refunds via the attester-signed reject branch. First live run:
  - Attestation UID: `0x03bc365481566847b6bcb8730e20f4d018a0abdf513b1531d89edaca80daa8b2`
  - Attest tx: `0x06948da4a96edf5c5a9707a73178cb51c11ca6928d84afd758b8ca6b4ba7e010`
  - Impostor balance after refund: 0 (verified protection works)
- `apps/api/src/app/services/farcaster_frame.py` — Frame HTML wrapper +
  inline SVG status image (no external image host needed).
- 3 new FastAPI endpoints:
  - `GET /api/frame/attest` — Frame HTML with `fc:frame:*` meta tags
  - `POST /api/frame/attest` — button handler (bounces to GET)
  - `GET /api/frame/image` — dynamic SVG status (APPROVE / REJECT / PENDING)
- `apps/api/tests/test_farcaster_frame.py` — 5 tests for the Frame surface.
- `docs/DUNE_QUERIES.md` — 6 ready-to-paste SQL queries for the public
  `attestrwa-public` dashboard (attestations/day, decision split, top
  attesters, USDC volume released, refunds by reason, attestation-to-
  release latency).
- `docs/SECURITY.md` — full audit posture section: Slither command +
  result (**0 findings**), Foundry test summary, backend pytest summary,
  E2E happy/reject script outcomes. Deferred items list (formal STRIDE,
  HSM keys, multi-sig attester) made explicit.

### Updated
- `contracts/src/SettlementEscrow.sol` — initialize `reason` in `refund()`
  to satisfy Slither's `uninitialized-local` detector. Logic unchanged.
- `README.md` — full rewrite of distribution-channels block (live Frame
  URL, Dune query pack pointer, both E2E scripts) and a new 6-step
  quickstart that goes from `foundryup` to running both demos in two
  minutes.

### Verified
- `uv run pytest -q` → **62 passed** (was 57; +5 Frame tests).
- `forge test -q` → **33 passed** (unchanged from alpha.2).
- `slither src/SettlementEscrow.sol` (low/medium/high severity) → **0 findings**.
- `./scripts/e2e_rwa_flow.sh` → exits 0, payee receives released funds.
- `./scripts/e2e_rwa_reject.sh` → exits 0, escrow refuses release, buyer
  refund balance asserted.

### Tag
- `v1.0.0` — first release of AttestRWA. The hackathon-ready demo runs
  fully autonomously on a local Anvil fork of Base Sepolia with real EAS
  protocol bytecode at the canonical addresses. Real-testnet deploy is a
  single env-var flip plus an optional 60-second faucet step (see
  `docs/DEV_SIMULATION.md` § "Switching to real Base Sepolia").

## v1.0.0-alpha.2 — 2026-05-20 (branch `v1/attestation-layer`)

**Week 2.3 — end-to-end on-chain settlement works.** Buyer deposits to
`SettlementEscrow`, off-chain attester decides + signs + broadcasts an EAS
`SettlementApproval` attestation, escrow verifies and releases to the
authorized payee — every step on the dev fork of Base Sepolia with the
real EAS protocol bytecode at the canonical addresses.

### Added
- `scripts/e2e_rwa_flow.sh` (idempotent, ANSI-coloured output):
  ensures `./scripts/dev-chain.sh` is running, ensures contracts are
  deployed, starts the FastAPI attester if not up (with env from
  `.dev-chain.state`), then walks the whole 5-step flow:
    1. Mint mUSDC to the buyer EOA.
    2. Buyer approves escrow.
    3. Buyer deposits with a fresh deterministic `dealId`.
    4. `POST /attest/settlement` → backend signs + broadcasts EAS attestation.
    5. `cast send escrow.release(dealId, uid)` → payee receives funds.

### First live happy-path run (audit trail)
- Deal id          : `0xf429b5fd03631715bcbcb70af36e6035b873fc0afa93b5ba3d1196aa8db46569`
- Buyer            : `0x70997970C51812dc3A010C7d01b50e0d17dc79C8` (Anvil #1)
- Payee            : `0x976EA74026E726554dB657fA54763abd0C3a0aa9` (Anvil #6, Bangkok Landmark)
- Amount           : 580 mUSDC (580,000,000 base units)
- Attestation UID  : `0xf34d952dbcb2c58fc762666b26adccd87c89c2fbf47ffea8c9567ac5a559057c`
- Attest tx        : `0x9aa60282dfb475426b983b461a6df34a52a12491049eda84dd639c32021364d4`
- Attest block     : 41,755,438
- Attest gas       : 433,971
- Final payee bal  : 580,000,000 mUSDC base units (580 USDC equivalent)

### Verified
- E2E script exits 0; payee balance assertion passes.
- 4-rule DSL policy evaluation logged in the attest response with
  per-rule explanations (`payee-must-match-developer-feed`,
  `capital-not-red`, `kyc-tier-by-amount`, `only-supported-jurisdictions`).
- Backend `web3.py` correctly encoded the 10-field SettlementApproval
  payload; the EAS contract accepted the schema-bound attestation.
- Escrow contract verified all 7 attestation requirements (schema pin,
  revocation, expiration, attester whitelist, dealId match, payee match,
  capital class, payee verified) and transferred the stablecoin.

### Tag
- `v1.0.0-alpha.2` — Week 2 closeout. Week 3 starts with Farcaster Frame,
  Dune dashboard, UI polish, and the optional real-testnet deploy.

## v1.0.0-alpha.2.w2.2 — 2026-05-20 (branch `v1/attestation-layer`)

**Week 2.2 — attester service shipped.** Off-chain compliance engine plus
EAS client now expose the full attestation path. Pytest 34 → 57 (23 new
tests across taint, DSL, attester service, and HTTP).

### Added
- Backend dependencies: `web3>=7.6`, `eth-account>=0.13`, `eth-abi>=5.1`
  (pulled into `uv.lock`).
- `data/synthetic/policies/default_attestrwa_policy.yaml` — baseline
  compliance policy as YAML DSL (4 rules: payee-must-match-developer-feed,
  capital-not-red, kyc-tier-by-amount, only-supported-jurisdictions).
- `apps/api/src/app/services/wallet_taint.py` — deterministic Chainalysis-
  style classifier (green / amber / red) keyed off
  `data/synthetic/rwa/wallets.json`. Pure function, no I/O.
- `apps/api/src/app/services/compliance_dsl.py` — tiny YAML rule DSL with
  AST-validated boolean expressions (AND/OR/NOT, comparisons, literals,
  identifiers; no function calls, no attribute access, no walrus).
  YAML-style aliases `true` / `false` / `null` for ergonomic policy
  authoring. Short-circuit evaluation: first failed rule stops the chain.
- `apps/api/src/app/services/eas_client.py` — thin web3.py wrapper over
  the EAS contract at the canonical Base address `0x4200…0021`. Provides
  `attest`, `get_attestation`, `health`, plus an ABI-encoder helper for
  the 10-field `SettlementApproval` payload.
- `apps/api/src/app/services/attester_service.py` — orchestrator: loads
  the developer feed, runs `wallet_taint` + DSL evaluation, builds a
  deterministic evidence hash, and (when EAS is reachable) signs and
  submits the on-chain `SettlementApproval` attestation.
- `apps/api/src/app/schemas/attester.py` — Pydantic v2 schemas:
  `AttestRequest`, `AttestResponse`, `AttesterHealthResponse`,
  `AttestationLookupResponse` with hex / length validators.
- Three new FastAPI endpoints:
  - `POST /attest/settlement` — decision + on-chain attestation
  - `GET /attest/healthz` — RPC + attester balance
  - `GET /attest/{dealId}` — placeholder lookup (Week 3 wires the EAS indexer)
- Tests (23 new): `test_wallet_taint.py` (4), `test_compliance_dsl.py`
  (7), `test_attester_service.py` (6), `test_attester_api.py` (6).

### Updated
- `apps/api/pyproject.toml` — dependencies block expanded for web3 stack.
- `apps/api/src/app/main.py` — imports + 3 attester endpoints; on-chain
  attestation submission is best-effort (warning + decision-only response
  when EAS RPC is unreachable, so the API stays usable without the dev
  chain).

### Verified
- `uv run pytest -q` → **57 passed in 0.74s** (was 34 in alpha.1).

### Next (Week 2.3)
- Single-screen UI (`apps/web/src/app/rwa-settlement-live.tsx`):
  wagmi + viem + RainbowKit wallet connect, escrow event watcher,
  attester poll, cinematic transitions.
- `scripts/e2e_rwa_flow.sh`: buyer → escrow.deposit → attester →
  EAS.attest → escrow.release end-to-end smoke against the dev fork.
- Tag `v1.0.0-alpha.2`.

## v1.0.0-alpha.2.w2.1 — 2026-05-20 (branch `v1/attestation-layer`)

**Week 2.1 — Foundry contracts shipped and deployed to dev fork.** Pivot
core primitives now exist on-chain (on the local fork of Base Sepolia)
with full Foundry unit + fuzz coverage.

### Added
- `contracts/foundry.toml`, `contracts/remappings.txt`,
  `contracts/slither.config.json`, `contracts/.gitignore` — Foundry
  workspace with solc 0.8.26, 1M-run optimizer, default fuzz 256 runs.
- `contracts/lib/` (gitignored, populated via `forge install --no-git`):
  forge-std, OpenZeppelin v5.0.2, ethereum-attestation-service eas-contracts.
- `contracts/src/MockUSDC.sol` — minimal ERC-20 with 6 decimals + public
  `mint`. Demo-only token; never deploys on mainnet.
- `contracts/src/SettlementEscrow.sol` (~280 LOC, full NatSpec):
  - `deposit / release / refund` workflow with `ReentrancyGuard` + `Ownable`
  - `Deal` struct keyed by `dealId`; one deposit per id
  - EAS attestation verification: schema pin, revocation check,
    expiration check, attester whitelist, payee/token/amount cross-check
    against deposit, payee-verified flag, capital-class threshold
  - Refund paths: deadline expiry, attester-signed reject (payeeVerified
    false or capitalClass red)
  - Events: `Deposited`, `SettlementReleased`, `SettlementRefunded`,
    `AttesterTrustChanged`
  - 20+ custom errors for gas-efficient revert reasons
- `contracts/test/MockUSDC.t.sol` — 4 tests incl. one fuzz.
- `contracts/test/MockEAS.sol` — IEAS stub for tests (lets us seed
  arbitrary `Attestation` records into `getAttestation`).
- `contracts/test/SettlementEscrow.t.sol` — 29 tests:
  - 3 constructor paths
  - 2 admin paths
  - 8 deposit paths (happy + 7 reverts)
  - 8 release paths (happy + 7 reject branches: wrong schema, revoked,
    expired, untrusted attester, payee mismatch, capital red, payee not
    verified, replay across deals; plus dup-release)
  - 4 refund paths (deadline expiry, before-deadline revert, payee-bad
    refund, capital-red refund) + caller-not-buyer
  - 1 fuzz on amount and deadline (256 runs)
- `contracts/script/Deploy.s.sol` — deploy script reading `PRIVATE_KEY`,
  `EAS_SCHEMA_UID_SETTLEMENT_APPROVAL`, `ATTESTER_ADDRESS` env vars.
  Wires the attester whitelist and pre-mints 1,000,000 mUSDC to the
  deployer for booth flow.
- `scripts/deploy-contracts.sh` — idempotent wrapper that reads
  `.dev-chain.state`, runs the deploy script, parses addresses, and
  appends them back into the state file.

### Deployed (dev fork of Base Sepolia)
- `MockUSDC` = `0xeba5CEc9257045Df0B44eA784F9a7Fa07DeeF6d4`
- `SettlementEscrow` = `0x54D4962847bf85AB71a1Fc984510dc12D3feA1D8`
- Trusted attester whitelisted at deploy: `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`
- Deployer pre-balance: 1,000,000 mUSDC

### Verified
- `forge build` clean (4 `block-timestamp` warnings — acceptable for
  hour-scale deadlines; documented in `docs/SECURITY.md`).
- `forge test --gas-report`: **33/33 passed** in 45 ms.
- Gas budgets (max):
  - `release()` = 118,733 (< 120k target ✓)
  - `refund()` = 102,176
  - `deposit()` = 176,087
  - `setAttester()` = 47,626
- Live deploy via `forge script script/Deploy.s.sol --broadcast` against
  Anvil fork succeeded (chain 84532, deterministic addresses captured).

### Propagated
- `README.md` on-chain artefact table updated with contract addresses.
- `docs/ARCHITECTURE.md` contracts table updated.
- `apps/web/src/app/page.tsx` v1 hero stub updated with addresses.
- `.env.example` now lists `MOCK_USDC_ADDRESS` + `SETTLEMENT_ESCROW_ADDRESS`.

### Next (Week 2.2)
- Attester service: `eas_client.py`, `wallet_taint.py`,
  `compliance_dsl.py`, `attester_service.py`, `POST /attest/settlement`.

## v1.0.0-alpha.1 — 2026-05-20 (branch `v1/attestation-layer`)

**Week 1 complete: surgery, rebrand, slim docs.** Foundation ready for the
Week 2 web3 core build (Foundry contracts + attester service + single-screen
UI). 64 → 34 tests, all green; 53 → 8 docs; one consolidated brand
(AttestRWA).

### Week 1.1 — Archive surgery (commit `e799c43`)

Moved 35 legacy files into `archive/v0.5/` via `git mv` (history preserved).
Cleaned `main.py`, `rag.py`, `paths.py`, `schemas/demo.py`, `test_api.py`,
`test_rag.py` of dangling consult / yield / guided-simulation references.
Replaced `apps/web/src/app/page.tsx` with a v1 hero stub showing the
dev-fork on-chain artefact table and the pivot story.

Archived in this step:

- 5 backend consult services + 1 yield service + 1 consult schema
- 4 consult tests (consultation, retrieval, dialogue_matrix, knowledge)
- 8 React panels (buyer-consultation, closing-passport, developer-knowledge,
  guided-deal, pitch-screen, post-closing-yield, scenario-simulator,
  supplier-contrast)
- 7 consult-KB markdown files + dialogue matrix YAML
- whatsapp-bridge Go service (5 files)
- 4 consult / WhatsApp / AI-contour scripts

`pytest`: 34 passed (was 64; 30 archived with their features).

### Week 1.2 — Rebrand to AttestRWA

- `apps/api/pyproject.toml`: name `bankable-property-os-api` →
  `attestrwa-api`; version → `1.0.0-alpha.1`.
- `apps/web/package.json`: same shape.
- `apps/api/src/app/main.py`: FastAPI `title` → `AttestRWA API`;
  `description` rewritten around attestation primitive; `/healthz`
  service tag → `attestrwa-api`.
- `README.md`: replaced with the v1 hero (formerly `docs/v1/README_DRAFT.md`).
  Old README moved to `archive/v0.5/README.v0.5.md`.
- `AGENTS.md`: rewritten compact AttestRWA-first; old AGENTS to
  `archive/v0.5/AGENTS.v0.5.md`.

Environment variable names (`BANKABLE_*`) intentionally kept for backward
compatibility — they are not jury-visible and renaming risks deploy config
drift. The visible brand is unified.

### Week 1.3 — Slim docs (53 → 8)

`docs/` now contains exactly 8 files:

1. `PRODUCT_THESIS.md` — problem, solution, primary customers, non-goals
2. `ARCHITECTURE.md` — layers, data flow, design decisions, mermaid diagrams
3. `ATTESTATION_SCHEMA.md` — EAS `SettlementApproval` 10-field schema
4. `API_CONTRACT.md` — REST endpoints (current + Week 2 planned)
5. `DEMO_SCRIPT.md` — 90 s and 3 min pitches, backup video script, Q&A bridges
6. `DEV_SIMULATION.md` — Anvil fork runbook
7. `ROADMAP.md` — Week 0 to 2027 plan, explicit non-goals
8. `SECURITY.md` — 12 threat scenarios + mitigations (Week 3 expands with
   slither / Foundry fuzz results)

54 legacy docs archived to `archive/v0.5/docs/` (53 from v0.5 + 1
Week 0 bootstrap doc that became historical).

Dead `docs/v1/...` link references cleaned across `README.md`, `AGENTS.md`,
`docs/ATTESTATION_SCHEMA.md`.

### Week 1.4 — Synthetic data extension

- Created `data/synthetic/rwa/wallets.json` — canonical map of Anvil
  default accounts to AttestRWA demo roles (attester, buyer, two
  developer treasuries, one wrong-payee, one mixer-tainted buyer).
- Extended `data/synthetic/developers/siam-riverside-feed.json` with
  `authorized_payee_wallets` (Anvil acc 2) and `known_impostor_payees`
  (Anvil acc 3 wearing `SRL Holding 2026` label, captured from anchor
  case agent payment instruction).
- Extended `data/synthetic/developers/bangkok-landmark-feed.json` with
  `authorized_payee_wallets` (Anvil acc 6).
- Extended `data/synthetic/developers/shadow-bay-feed.json` with
  `authorized_payee_wallets: []` and `marketing_payee_wallet_claimed`
  (Anvil acc 7) to make the off-platform reject path explicit.
- Created `data/synthetic/rwa/scenarios.json` with three end-to-end RWA
  flow scenarios:
  - `happy-bangkok-condo` — clean Dubai buyer, verified Bangkok Landmark
    payee, capital green → expect `SettlementReleased`.
  - `payee-mismatch-srl` — same Dubai buyer, instruction points to the
    `SRL Holding 2026` impostor wallet → expect `payeeVerified=false`
    attestation and `SettlementRefunded`.
  - `capital-red-mixer-touch` — fresh wallet with Tornado-Cash two-hop
    exposure (synthetic mock), valid payee instruction → expect
    `capitalClass=2 (red)` attestation and `SettlementRefunded`.

### Verified Week 1 closeout

- `uv run pytest -q` → 34 passed.
- All 5 modified / new JSON files validate with `json.load`.
- Dev chain (`./scripts/dev-chain.sh`) still up; EAS schema UID still
  resolves on the fork via `getSchema` readback.

## v1.0.0-pivot.w0.sim — 2026-05-20 (branch `v1/attestation-layer`)

**Full local simulation unlocks autonomous Week 1.** No faucet, no manual
schema registration needed. Everything runs on an Anvil fork of Base
Sepolia that inherits real EAS protocol bytecode at canonical addresses.

### What changed

- Installed Foundry 1.7.1 (forge / cast / anvil / chisel).
- Authored `scripts/dev-chain.sh` (idempotent) — spins up Anvil fork of
  Base Sepolia on port 8545, verifies EAS contract, registers the
  `SettlementApproval` schema via SchemaRegistry, writes `.dev-chain.state`.
- Authored `scripts/stop-dev-chain.sh` — clean shutdown by pid file or
  port lookup.
- Documented full simulation in `docs/v1/DEV_SIMULATION.md` (Anvil default
  account map, architecture diagram, smoke test, switch to real testnet
  in Week 3).
- Verified end-to-end: stop → start cycle = ~19 s, schema verified via
  `getSchema(uid)` readback, deterministic UID
  `0x1f64ec96216b0381dc4443b7378c57485f2217656537e8ea36f0b23af047cc96`.
- Updated `.env.example` with dev + production mode blocks. Dev attester
  key explicitly marked as the public Anvil test key (never use on
  mainnet).
- Updated `.gitignore` for `.dev-chain.state`, `.env.dev`, Foundry build
  artefacts, and Anvil logs.
- Marked the previous "manual blocker" in `WEEK0_BOOTSTRAP.md` as no
  longer blocking. The faucet step survives only as an optional Week 3
  task for public-testnet visibility (or skipped entirely with a recorded
  demo).
- Filled live registration data in `docs/v1/ATTESTATION_SCHEMA.md` §3a
  (dev fork) and §3b placeholder (real Base Sepolia Week 3).

### Why fork-not-mock

A pure Anvil node would have required us to deploy mock EAS / SchemaRegistry
contracts ourselves. Forking Base Sepolia gives us the real protocol bytecode
at the canonical addresses (`0x4200…0021`, `0x4200…0020`), so all behaviour —
event topics, gas, revert messages, ABI — is identical to production. The
escrow contract we build in Week 2 will not need any code path changes when
we switch from local fork to real testnet in Week 3.

## v1.0.0-pivot.w0 — 2026-05-20 (branch `v1/attestation-layer`)

**GODMODE pivot — Week 0 bootstrap.** This is the start of a radical
repositioning from "Bankable Property Network" (B2B bank settlement
infrastructure for Thailand property) to **AttestRWA** (Settlement
Attestation Layer for RWA) — a web3-native on-chain compliance bridge for
stablecoin real-world-asset settlements, targeting SEA Blockchain Week
2026.

Full plan: `.cursor/plans/godmode-pivot-attestation-layer_*.plan.md`.

### What changed

- Branched `v1/attestation-layer` from `main@7148ac5` (v0.5.13). `main`
  stays as safety until `v1.0.0` is ready to merge.
- Created `archive/v0.5/` scaffold; legacy modules will be moved here in
  Week 1 via `git mv` (commit history preserved).
- Created `contracts/` Foundry workspace skeleton (Week 2 fills in
  `SettlementEscrow.sol` + `MockUSDC.sol` + fuzz tests).
- Drafted new root README in `docs/v1/README_DRAFT.md` with the AttestRWA
  hook, pivot story, on-chain artefact table, and Week 0–3 roadmap.
- Defined EAS Schema `SettlementApproval` in
  `docs/v1/ATTESTATION_SCHEMA.md` — schema string, field semantics,
  threat model stub, registration instructions, escrow integration sketch.
- Documented Week 0 bootstrap state and the single manual step
  (generate attester EOA, fund on Base Sepolia, register schema) in
  `docs/v1/WEEK0_BOOTSTRAP.md`.

### Decisions locked (Week 0)

| Slot | Value |
|------|-------|
| Brand | AttestRWA |
| Network | Base Sepolia (chainId 84532) |
| Stablecoin | Mock USDC ERC-20 (own deployment) |
| Contracts | Foundry (fuzz + invariants + slither) |
| Wallet stack | wagmi + viem + RainbowKit |
| Buyer consult fate | Archive to `archive/v0.5/` |
| Timeline | 1–3 weeks "divine" mode |
| Demo | Live testnet + 3 pre-funded deals + 60s backup video |

### Next (blocking Week 1)

User must complete manual steps in `docs/v1/WEEK0_BOOTSTRAP.md` §A–D:

1. Generate attester EOA (`cast wallet new`).
2. Fund on Base Sepolia (Alchemy / QuickNode faucet).
3. Register `SettlementApproval` schema on Base Sepolia EAS.
4. Report Schema UID + attester address back.

After that: Week 1 surgery (archive legacy, rebrand, slim docs, extend
synthetic data) starts.

## 0.5.13 - 2026-05-20

- Full project audit: [`docs/PROJECT_AUDIT_REPORT.md`](docs/PROJECT_AUDIT_REPORT.md) — system map, LIVE vs ROADMAP, effectiveness re-score, P0/P1/P2 backlog.
- Tier A doc sync to 0.5.13: AI_AUDIT_INDEX, VALIDATION_REPORT, FINAL_STATUS, PROJECT_DESCRIPTION, DOCS_AUDIT, runbooks, scorecard, NEXT_BUILD_PRIORITY; REPRODUCTION_GUIDE version section.
- `developer_knowledge` channel_roadmap: WhatsApp and web → `live`.
- Scenario/dialogue report scripts stamp API v0.5.13.

## 0.5.12 - 2026-05-20

- Fix SYSTEM_PROMPT leak in WhatsApp consult: rewritten prompt, `_is_prompt_leak` sanitizer, deterministic `_purchase_pitch_reply` for USDT/cash/mixed capital questions.
- Synthetic RAG: `capital_routes_buyer_pitch.md`, `thailand_property_reference_links.md`; extended `Buyer_Settlement_Bridge.md` with Landmark → bank rails pitch.
- Dialogue matrix +3 scripts (`usdt_buyer_ru`, `cash_buyer_ru`, `mixed_capital_en`); pytest for prompt-leak and purchase pitch fallback.
- `WHATSAPP_CONSULT_DEMO.md` 4-turn jury arc including USDT product pitch turn.

## 0.5.11 - 2026-05-20

- Consult KB pivot: removed legacy Karon/TEST DEVELOPER 1 corpus; replaced with slim **Landmark Sukhumvit Tower** KB (Bangkok Landmark Group, 18.5–24.8M THB).
- Aligned WhatsApp demo narrative with settlement/supplier contrast (Bangkok tier-1, not Phuket).
- Updated `buyer_consultation.py` anchors, greetings, villa handler, scenario strip regex; dialogue matrix 14/14 (offline uses keyword mode for CI determinism).
- Docs: `WHATSAPP_CONSULT_DEMO.md` 3-turn distribution script; `CONSULT_KNOWLEDGE_DEMO.md` without RealEstate-AI import.

## 0.5.10 - 2026-05-20

- Documentation sync: Tier A docs aligned to v0.5.10 (58+ pytest, 14/14 dialogue matrix, consult live LLM).
- Multi-channel narrative: `docs/DISTRIBUTION_CHANNELS.md` — one `POST /api/consult/message`, WhatsApp live; Telegram, Line, email, voice roadmap.
- Consult KB bridge: `Buyer_Settlement_Bridge.md`, `FAQ_TH.md`; policy `consult_channel_policy.md`; extended dialogue matrix (`mixed_project_settlement`, `follow_up_context`).
- Intent fix: strip `TEST DEVELOPER` before scenario keyword detection; FET template snippet for Russian/English FAQ turns.
- Cross-links: PITCH, RUNBOOK, ARCHITECTURE, BUYER_CONSULTATION_AGENT, DEMO_CHECKLIST, SYNTHETIC_CORPUS.

## 0.5.9 - 2026-05-20

- Consult dialogue simulation: `scripts/run_consult_dialogue_matrix.py` + `data/consult_dialogues/dialogue_matrix.yaml` (offline + live API modes).
- Agent tuning: expanded project intent (villa/buy/where), consult_kb-only RAG filter, session-aware retrieval, structured LLM context, WhatsApp reply sanitization.
- Qwen 3.6 in LM Studio: `LOCAL_AI_LLM_ENABLE_THINKING=false` (default) + `chat_template_kwargs` for direct `content` replies.
- Demo anchor: TEST DEVELOPER 1 / Karon Phuket enforced in prompts; villa requests get honest condo inventory answer.
- Report: `docs/CONSULT_DIALOGUE_SIMULATION_REPORT.md`; tests in `test_consult_dialogue_matrix.py`.

## 0.5.8 - 2026-05-20

- Full local AI contour for buyer consult: Qdrant + BGE embed/rerank + LM Studio wired in Docker via `host.docker.internal`.
- RAG ingest includes `data/consult_knowledge/realestate-demo/` alongside synthetic corpus; `consult_retrieval.py` with `CONSULT_RETRIEVAL_MODE` (`auto` | `keyword` | `rag`).
- Buyer consultation uses RAG pipeline with explicit keyword fallback; citations include `retrieval_mode` and `rerank_score`.
- API: `GET /api/consult/contour/healthz`; `scripts/start-full-ai-contour.sh`; docker-smoke checks contour + LLM configured.
- Docs: updated `LOCAL_AI_CONTOUR.md`, `CONSULT_KNOWLEDGE_DEMO.md`, `HACKATHON_RUNBOOK.md`, `AI_AUDIT_INDEX.md`, `DOCKER_QUICKSTART.md`.

## 0.5.7 - 2026-05-20

- WhatsApp bridge: message ID dedup (fixes duplicate replies); `/pair` auto-refresh QR page.
- Consult knowledge: import RealEstate-AI `knowledge_base` → `data/consult_knowledge/realestate-demo/`; `consult_knowledge.py` keyword chunk search (no Qdrant).
- Buyer consultation: intent routing (greeting / project_faq / settlement / mixed), multilingual greetings, conditional bank tools.
- API: `GET /api/consult/knowledge/healthz`; consult response includes `intent`.
- Docs: `docs/CONSULT_KNOWLEDGE_DEMO.md`; ASR voice roadmap; `scripts/import_realestate_knowledge.sh`.

## 0.5.6 - 2026-05-20

- Added batch scenario simulation: `scripts/run_scenario_matrix.py` → `docs/SCENARIO_SIMULATION_REPORT.md` (all 8 scenarios, judge-ready grouping).
- Buyer Consultation API: `POST /api/consult/message`, `GET /api/consult/healthz`; `buyer_consultation.py` with internal tools, LM Studio instruct path, explicit template fallback.
- WhatsApp bridge MVP: `services/whatsapp-bridge/` (Go + whatsmeow), QR pairing on `:8020`, wired to consult API; `infra/docker-compose.yml` services `bankable-api` + `whatsapp-bridge`.
- UI: `buyer-consultation-panel.tsx` web fallback chat.
- Docs: `docs/WHATSAPP_CONSULT_DEMO.md`; runbook/checklist WhatsApp steps; `AI_AUDIT_INDEX` buyer consult partial live.

## 0.5.5 - 2026-05-20

- Added Developer Supply Demo: Shadow Bay prelaunch (off-platform) vs Bangkok Landmark Group (fictional tier-1 on-network).
- Synthetic feeds, policies, RAG docs, and `project-landmark-tower`; enriched `project-shadow-red`.
- New scenarios: `prelaunch-off-platform-route`, `tier-one-landmark-route`; `supply_risk_signals` on scenario runs.
- New API: `GET /api/demo/supplier-contrast`; refactored `developer_knowledge.py` for parameterized feed paths.
- UI: Supplier Contrast panel (`supplier-contrast-demo.tsx`), pitch card «Why Developers Join», scenario simulator labels.
- Docs: `docs/DEVELOPER_SUPPLY_DEMO.md`; cross-links in PITCH_SCRIPT, DEMO_CHECKLIST, HACKATHON_RUNBOOK, SCENARIO_MATRIX, SYNTHETIC_CORPUS, README, HANDOFF.
- Added `docs/PROJECT_DESCRIPTION.md` for hackathon registration; synced doc drift (8 scenarios, v0.5.5) across AGENTS, FINAL_STATUS, REPRODUCTION_GUIDE, VALIDATION_REPORT, DOCS_AUDIT, PUBLISH.
- Added `docs/AI_AUDIT_INDEX.md` for automated/hackathon project review; aligned DEMO_SCRIPT, DEMO_REHEARSAL_REPORT, SYNTHETIC_DATA_GUIDE, JOURNEY_DEVELOPER_AGENT, ARCHITECTURE.
- Published public repository: https://github.com/FUYOH666/bankable-property-network (Apache-2.0).
- Hackathon demo vitrine: https://scanovich.ai/seablockchainweek/ (static showcase; removable post-event).

## 0.5.4 - 2026-05-20

- Added agent architecture documentation: `docs/NONLINEAR_DECISION_GRAPH.md` (Settlement Branch Explorer), `docs/BUYER_CONSULTATION_AGENT.md` (LangGraph.js buyer layer), `docs/AGENT_STACK_EVALUATION.md` (framework filter).
- Cross-linked README, AGENTS.md, ARCHITECTURE, LOCAL_AI_CONTOUR, AI_SERVICE_TIERS, THESIS, journeys, ROADMAP, REPRODUCTION_GUIDE (Phase J buyer agent), HANDOFF, HACKATHON_RUNBOOK, PITCH_SCRIPT, DOCS_AUDIT, FINAL_STATUS.
- Documented LangGraph.js as primary orchestration; buyer agent and settlement graph as roadmap (doc-first, no code scaffold yet).
- **Verification pass:** 33 pytest, frontend build, 10/10 API smoke; `docs/STAFF_REVIEW_0.5.4.md`; aligned API version to 0.5.4 in `config.py` and `.env.example`; updated VALIDATION_REPORT, DEMO_CHECKLIST, REPRODUCTION_GUIDE.

## 0.5.3 - 2026-05-20

- Added local AI contour documentation: `docs/LOCAL_AI_CONTOUR.md` (Qdrant + BGE + LM Studio runbook) and `docs/AI_SERVICE_TIERS.md` (demo vs enterprise matrix: vLLM, Qwen-class embeddings).
- Extended `GET /api/rag/health` with tier metadata (`deployment_tier`, `embedding_tier`, `llm_tier`, `production_note`).
- Updated `.env.example`, `config/default.yaml`, Developer Knowledge Hub `ai_stack`, and cross-links across README, ARCHITECTURE, REAL_RAG_DEMO, THESIS, REPRODUCTION, HANDOFF, DEPLOY, HACKATHON_RUNBOOK.

## 0.5.2 - 2026-05-20

- Verified stack end-to-end: 33 pytest, frontend build, all demo endpoints smoke OK.
- Added agent handoff package: `AGENTS.md`, `docs/HANDOFF.md`, `.cursor/rules/bankable-project.mdc`.
- Added `docs/REPRODUCTION_GUIDE.md` — single-file rebuild playbook with phase order and per-module expansion matrix.
- Updated VALIDATION_REPORT, PUBLISH_SEABLOCKCHAINWEEK, DOCS_AUDIT, JOURNEY_BUYER, JOURNEY_DEVELOPER_AGENT, `.env.example`.

## 0.5.1 - 2026-05-20

- Staff review polish: shared `paths.py` + `data_loader`, routing invariant fix, structured logging, Pydantic settings/schemas, API version 0.5.0.
- Settlement Flow panel replaces static capital/route/passport cards; `useDemoFetch` hook; demo flow aligned across README, runbooks, and UI.
- Added tests for routing edge cases, paths, data loader, scenario 404s, developer hub aligned payee (33 tests total).

## 0.5.0 - 2026-05-20

- Added Verified Developer Knowledge Layer: synthetic developer feed, policy doc, `GET /api/demo/developer-knowledge-hub`, Developer Knowledge Hub vision screen.
- Documented upstream SSOT model in `docs/DEVELOPER_KNOWLEDGE_LAYER.md`; updated thesis, README network layers, ROADMAP, and PITCH_SCRIPT.
- Pitch screen card for Developer Knowledge Hub; payee mismatch vs anchor case in demo.

## 0.4.0 - 2026-05-20

- Added commission model synthetic policy doc for RAG corpus.
- Added API `infrastructure_context` on demo endpoints; production CORS for scanovich.ai via `BANKABLE_CORS_ORIGINS`.
- Reframed `page.tsx` hero and anchor case under money infrastructure thesis.
- Aligned DEMO_SCRIPT, JOURNEY_BUYER, DEMO_CHECKLIST, FINAL_STATUS, VALIDATION_REPORT, ROADMAP.
- Added DEPLOY.md, PUBLISH_SEABLOCKCHAINWEEK.md, Dockerfile, render.yaml; `NEXT_PUBLIC_SEABW_API_URL` env alias.

## 0.3.0 - 2026-05-20

- Reframed project narrative around money infrastructure thesis: banks and regulated structures as primary customers, buyer protection as social bonus.
- Added `docs/MONEY_INFRASTRUCTURE_THESIS.md` with commission-model root problem, brand gap, and AI operational layer.
- Updated NETWORK_POSITIONING, PITCH_SCRIPT, STAKEHOLDER_PERSPECTIVES, ARCHITECTURE, README, HACKATHON_RUNBOOK, and Pitch Screen UI.

## 0.2.0 - 2026-05-20

- Added Post-Closing Yield Plan strategic extension: `GET /api/demo/post-closing-yield-plan`, web vision screen, synthetic rental managers and building restrictions.
- Documented Bankable Property & Yield OS in README and pitch script.

## 0.1.0 - 2026-05-19

- Created Bankable Property OS hackathon MVP scaffold.
- Added Closing Passport backend demo endpoint.
- Added Property Shield, Capital Bankability Map, route comparison, and evidence pack hashing.
- Added synthetic anchor case for risky property deposit with legal entity mismatch.
- Added demo UI, documentation pack, Qdrant compose file, and environment template.
- Reframed the project as Bankable Property Network with Bankable Property OS as the operating layer and Closing Passport as the first module.
- Added production roadmap, scenario matrix, role journeys, and synthetic corpus for SWIFT, USDT, cash/P2P, mixed capital, developer risk, and agent risk scenarios.
- Added Scenario API, deterministic RAG trace stub, frontend scenario simulator, pitch docs, synthetic evidence documents, rehearsal report, and hackathon runbook.
- Added real RAG integration with Qdrant REST, local embedding/reranker services, retrieved evidence UI, explicit fallback mode, and live RAG run report.
- Added polished web pitch screen and updated demo runbook/checklist/status documentation for final judging flow.
