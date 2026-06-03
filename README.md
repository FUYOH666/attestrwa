# AttestRWA

> **Settlement Attestation Layer for RWA** — on-chain compliance bridge that
> turns bank verification rules into machine-verifiable attestations, so
> stablecoin payments for real-world assets release only when the deal is
> bank-grade.

[![CI](https://github.com/FUYOH666/attestrwa/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/FUYOH666/attestrwa/actions/workflows/ci.yml)
[![Foundry tests](https://img.shields.io/badge/forge%20test-34%2F34-success)](contracts/test)
[![pytest](https://img.shields.io/badge/pytest-75%2F75-success)](apps/api/tests)
[![Slither](https://img.shields.io/badge/slither-0%20findings-success)](docs/SECURITY.md)
[![Solidity](https://img.shields.io/badge/solidity-0.8.26-blue)](contracts/foundry.toml)
[![Foundry](https://img.shields.io/badge/foundry-1.7.1-orange)](https://book.getfoundry.sh/)
[![Network](https://img.shields.io/badge/network-Base%20Sepolia-blue)](https://sepolia.basescan.org/)
[![EAS Schema](https://img.shields.io/badge/EAS%20schema-0x1f64ec96%E2%80%A6-7c3aed)](docs/ATTESTATION_SCHEMA.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![Hackathon](https://img.shields.io/badge/hackathon-SEA%20Blockchain%20Week%202026-purple)](https://www.seablockchainweek.org/hackathon)

**Author:** [Aleksandr Mordvinov](https://github.com/FUYOH666) ·
**Repository:** [github.com/FUYOH666/attestrwa](https://github.com/FUYOH666/attestrwa) ·
**85-second demo:** [youtube.com/shorts/BipB2qPzZz0](https://youtube.com/shorts/BipB2qPzZz0) (subtitles toggle-able)

---

## Two generations, one repo

```mermaid
flowchart TB
  subgraph v05 ["archive/v0.5 — Bankable Property Network"]
    thailand["Thailand property B2B settlement"]
    rag05["RAG + Closing Passport + payee mismatch"]
  end

  subgraph v1 ["main v1.0 — AttestRWA"]
    eas["EAS SettlementApproval schema"]
    escrow["SettlementEscrow.sol"]
    attester["FastAPI attester + Compliance DSL"]
  end

  v05 -->|"pivot May 2026, SEABW"| v1
  rag05 -->|"repurposed"| attester
```

Details: [`docs/PIVOT.md`](docs/PIVOT.md) · Ecosystem research:
[`docs/ECOSYSTEM_RESEARCH.md`](docs/ECOSYSTEM_RESEARCH.md) · Integration RFC:
[`docs/rfc/0001-settlement-eligibility-composition.md`](docs/rfc/0001-settlement-eligibility-composition.md)

---

## Hook (one sentence)

> RWA's bottleneck in 2026 is not tokenization — it's compliance.
> We don't compete with Centrifuge or RealT; we're the layer they plug into.

**Integrators:** start at [`docs/FOR_INTEGRATORS.md`](docs/FOR_INTEGRATORS.md) ·
Funding: [`FUNDING.md`](FUNDING.md)

## What you see when you open the demo (90 seconds)

1. **Frame** (10 s): "RWA settlements grew 8x in 2026. Banks still can't participate."
2. **Buyer wallet** (15 s) sends 500K Mock USDC to `SettlementEscrow` on Base Sepolia.
3. **Attester** (FastAPI, 20 s) detects pending settlement, reads developer
   feed, runs Property Shield + RAG-assisted evidence, signs an EAS
   `SettlementApproval` attestation.
4. **Branch A (HAPPY)** — attestation valid → escrow releases USDC to verified
   payee → on-chain Closing Passport hash visible on BaseScan.
   **Branch B (REJECT)** — payee mismatch (`SRL Holding 2026` vs
   `Siam Riverside Living`) → attestation rejected → escrow refunds buyer →
   audit log on-chain.
5. **Story close** (15 s): "One attestation schema. Any RWA. Any bank.
   Stablecoins meet compliance — without trusting either side."

## What's on-chain

### Dev simulation (Anvil fork of Base Sepolia — port 8545, chain 84532)

Spin up the full stack in one command: `./scripts/dev-chain.sh`. See
[`docs/DEV_SIMULATION.md`](DEV_SIMULATION.md).

| Artefact | Address / UID |
|----------|---------------|
| `SettlementApproval` EAS Schema UID | `0x1f64ec96216b0381dc4443b7378c57485f2217656537e8ea36f0b23af047cc96` |
| EAS contract (canonical) | `0x4200000000000000000000000000000000000021` |
| SchemaRegistry (canonical) | `0x4200000000000000000000000000000000000020` |
| Attester EOA (dev) | `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266` (Anvil acc 0) |
| `SettlementEscrow.sol` | `0x54D4962847bf85AB71a1Fc984510dc12D3feA1D8` |
| `MockUSDC.sol` | `0xeba5CEc9257045Df0B44eA784F9a7Fa07DeeF6d4` |

### Distribution channels (live on the dev stack)

| Channel | Where |
|---------|-------|
| Farcaster Frame | `GET /api/frame/attest?deal_id=…&decision=…` returns Frame HTML + inline SVG image; `POST` is the button handler. Local: <http://localhost:8080/api/frame/attest?decision=approve>. |
| Dune Analytics queries | [`docs/DUNE_QUERIES.md`](docs/DUNE_QUERIES.md) — copy-paste into Dune once contracts are public. |
| E2E happy demo | `./scripts/e2e_rwa_flow.sh` — buyer deposits, attester signs EAS attestation, escrow releases to verified payee. |
| E2E reject demo | `./scripts/e2e_rwa_reject.sh` — buyer instructs impostor payee, attester signs reject, escrow refuses release, buyer refunds. |

### Real Base Sepolia (optional — public proof)

Deploy and smoke on real testnet (local Anvil demo unchanged):

```bash
# Configure PROD_* in .env, then:
./scripts/deploy-public-testnet.sh
./scripts/public-attestation-smoke.sh
```

| Artefact | Link |
|----------|------|
| Escrow | Run deploy script → BaseScan link printed |
| Schema | [EAS Scan (deterministic UID)](https://base-sepolia.easscan.org/schema/view/0x1f64ec96216b0381dc4443b7378c57485f2217656537e8ea36f0b23af047cc96) |
| Sample attestation UID | Run `./scripts/public-attestation-smoke.sh` — UID printed for README / Dune |

See [`docs/DEV_SIMULATION.md`](docs/DEV_SIMULATION.md) for env flip between local fork and public testnet.

### Real Base Sepolia (Week 3 — legacy table)

| Artefact | Status |
|----------|--------|
| Schema UID | Same as dev (deterministic) — register on real Base Sepolia in 60 s with `cast send`, see `docs/ATTESTATION_SCHEMA.md` § 2. |
| Attester EOA (real, public address) | Generated via `cast wallet new`, funded via the Alchemy Base Sepolia faucet. |
| BaseScan deploy link | Created when `./scripts/deploy-public-testnet.sh` runs with `PROD_*` in `.env`. |
| EAS Scan schema link | <https://base-sepolia.easscan.org/schema/view/0x1f64ec96216b0381dc4443b7378c57485f2217656537e8ea36f0b23af047cc96> (resolves once registered on the real testnet). |
| Dune dashboard | Created from `docs/DUNE_QUERIES.md` queries once a public-testnet attestation exists. |

## Architecture (minimal)

```text
Buyer wallet  --USDC-->  SettlementEscrow.sol  --reads-->  EAS Registry
                              ^                                ^
                              | release/refund                 | write attestation
                              |                                |
                              +--------- Attester (FastAPI) ---+
                                              |
                                              v
                              Compliance Engine: Property Shield + RAG + Capital Map
                                              |
                                              v
                              Developer Feed (synthetic SSOT)
```

Full diagram: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Why we pivoted (Pivot story)

We started this project as a B2B bank-grade settlement infrastructure for
Thailand property — Closing Passport, payee verification, multi-channel
buyer consult. Before SEABW 2026 we ran a brutal market check and saw that:

1. Bank compliance dashboards are already a saturated category (SAS,
   Quantexa, Actimize).
2. Real growth in 2026 is in RWA stablecoin settlements — and that market
   has no programmable compliance bridge.
3. Our strongest primitives (payee mismatch detection, capital
   classification, evidence attestation) were already pointing toward an
   on-chain layer.

So we pivoted from B2B SaaS to a web3-native attestation primitive:
**Settlement Attestation Layer for RWA**. Same engineering foundation,
sharper edge, broader market. The AttestRWA stack — contracts, attester,
demo scripts, and recorded video — shipped in roughly **four hours** of
AI-assisted development for this hackathon.

The pivot is in this repo — see [`archive/v0.5/`](archive/v0.5/) for the
previous generation. We kept what mattered (payee logic, capital
classification, RAG, FastAPI/Next.js base, 64 pytest baseline), killed what
didn't (buyer consult, WhatsApp bot, 8 panels, 45 docs).

## Why this wins at SEA Blockchain Week 2026

- **Most RWA projects** build tokenization (Centrifuge, Maple, RealT,
  Polytrade) — we don't compete, we're the layer above. Full feature
  comparison: [`docs/COMPARISON.md`](docs/COMPARISON.md).
- **Most compliance projects** are KYC (Sumsub, Persona) — we're on-chain
  attestation primitives, not identity.
- **Most blockchain-property projects** tokenize titles — legal mess. We
  attest settlement evidence, not ownership claims.

**Pitch line:** "We don't tokenize property. We tokenize the fact that a
bank verified the deal."

## Social impact

RWA platforms today let anyone tokenize anything. AttestRWA adds the
missing verifier: developer authenticity, payee authority, capital
cleanliness. Buyers no longer wire stablecoins to unverified payees.
Regulators get audit-grade evidence. Markets get fewer rug pulls.
This is RWA growing up.

## Open source & ecosystem (May 2026)

| Doc | Purpose |
|-----|---------|
| [`docs/ECOSYSTEM_RESEARCH.md`](docs/ECOSYSTEM_RESEARCH.md) | 42-repo GitHub sweep + integration candidates |
| [`docs/QUANTUM_LEAP_BETS.md`](docs/QUANTUM_LEAP_BETS.md) | Top 5 non-linear leverage plays |
| [`docs/OSS_OPERATING_PLAN_90DAY.md`](docs/OSS_OPERATING_PLAN_90DAY.md) | Community, metrics, funding map |
| [`docs/OUTREACH_TARGETS.md`](docs/OUTREACH_TARGETS.md) | Shibui / Centrifuge / EAS outreach drafts |
| [`docs/POLICY_EVOLUTION.md`](docs/POLICY_EVOLUTION.md) | Policy change without escrow migration |
| [`docs/PRODUCTION_ROADMAP.md`](docs/PRODUCTION_ROADMAP.md) | Production engineering map |
| [`examples/integrate-centrifuge-hook/`](examples/integrate-centrifuge-hook/README.md) | Transfer-hook integration cookbook |

## Roadmap

| When | What |
|------|------|
| **May 2026 (hackathon)** | AttestRWA pivot shipped: EAS schema, `SettlementEscrow`, attester service, approve/reject E2E, Farcaster Frame, Dune query pack, demo video, public repo |
| **Q3 2026** | First exchange integration — Binance Settlement / OKX RWA / Bybit RWA pilot |
| **Q4 2026** | First bank attester pilot (Thailand or Singapore) — paid fee per attestation |
| **2027** | Multi-jurisdiction ASEAN expansion, L2 mainnet, compliance DSL marketplace |

## Tech stack

| Layer | Choice |
|-------|--------|
| L2 | Base Sepolia (testnet, fork via Anvil for dev) → Base mainnet (production) |
| Attestations | EAS — canonical at `0x4200000000000000000000000000000000000021` |
| Stablecoin | Mock USDC ERC-20 (demo); USDC / USDT (production) |
| Contracts | Solidity 0.8.26 + Foundry 1.7 (33/33 tests + fuzz; slither clean — 0 findings) |
| Wallet | wagmi + viem + RainbowKit (UI scaffold; CLI e2e demo lives in `scripts/`) |
| Backend | Python 3.12 + FastAPI + uv + web3.py 7 + eth-account + eth-abi |
| Compliance evidence | Qdrant + BGE-M3 + reranker (RAG over synthetic policy corpus) |
| LLM (explainability only, optional) | LM Studio (Qwen-class) — schema-bound, never auto-decides |
| Frontend | Next.js + TypeScript + pnpm |
| Analytics | Dune Analytics — public queries in `docs/DUNE_QUERIES.md` |
| Distribution | Farcaster Frame at `/api/frame/attest` |

## Quickstart — one command, ~2 minutes

```bash
# One-time installs
curl -L https://foundry.paradigm.xyz | bash && source ~/.zshenv && foundryup
curl -LsSf https://astral.sh/uv/install.sh | sh
corepack enable && corepack prepare pnpm@latest --activate

# Boot the entire stack: dev chain + contracts deployed + FastAPI + Next.js web
./scripts/demo-mode.sh
```

Output ends with a `DEMO READY` block listing all addresses + URLs. Then:

```bash
# Two end-to-end smokes (each ~15 s) — happy path and reject path
./scripts/e2e_rwa_flow.sh
./scripts/e2e_rwa_reject.sh

# Cinematic UI: open http://localhost:3000/rwa-settlement-live
# Farcaster Frame preview: open http://localhost:8080/api/frame/attest?decision=approve

# Stop everything
./scripts/stop-demo-mode.sh
```

The full hackathon recording walkthrough (terminal-only **and** UI+wallet
paths) is in [`docs/HACKATHON_RECORDING_GUIDE.md`](docs/HACKATHON_RECORDING_GUIDE.md).

> **Why this works without a faucet:** the dev chain is an Anvil fork of
> real Base Sepolia, so the EAS protocol bytecode at the canonical
> address `0x4200…0021` is the production code (4,121 bytes), not a
> mock. Every attestation in the demo runs through the real EAS
> protocol — only the chain itself is local.

## What we don't build (explicit boundaries)

- We don't tokenize property (legal mess).
- We don't issue our own stablecoin.
- We don't do KYC (integrate Sumsub/Persona later).
- We don't run our own L1/L2.
- AI does not autonomously move money — it helps regulated structures
  review evidence faster, traceably, in a controlled environment.

## License

Apache-2.0. Schema, attester address, and contracts are public.
