# Production roadmap

Transparent engineering map for banks, RWA platforms, integrators, and grant
reviewers. **Not a delivery commitment** — milestones align with
[`ROADMAP.md`](ROADMAP.md).

Synthetic demo data only until a regulated pilot is contracted.

---

## Current state (OSS v1)

| Capability | Status |
|------------|--------|
| EAS `SettlementApproval` schema + escrow | Shipped, Foundry tested |
| Attester + YAML Compliance DSL | Shipped |
| Policy `pack_id` + `policy_hash` in API / evidence | Shipped |
| Policy evolution simulation | [`POLICY_EVOLUTION.md`](POLICY_EVOLUTION.md) |
| RWA scenario matrix (3 cases) | [`RWA_SCENARIO_REPORT.md`](RWA_SCENARIO_REPORT.md) |
| Mock wallet taint | Shipped; live API stub |
| Multi-attester on escrow | Shipped; ops docs in [`MULTI_ATTESTER.md`](MULTI_ATTESTER.md) |
| Public Base Sepolia deploy scripts | Shipped; requires operator `PROD_*` keys |

---

## Attester service

| Item | Technology / practice | Verification |
|------|---------------------|--------------|
| Key management | HSM or cloud KMS; no demo Anvil keys | Key ceremony doc, rotation runbook |
| Multi-attester | `setAttester` registry + bank-owned EOAs | Foundry + ops checklist |
| Availability | HA deployment, health SLO on `/attest/healthz` | Load test, paging |
| Policy governance | Signed policy packs, `policy_hash` registry | CI verifies signature before deploy |
| Evidence | Immutable audit log + on-chain `evidenceHash` | Replay tests |

---

## Policy layer

| Item | Technology | Verification |
|------|------------|--------------|
| Pack authoring | YAML DSL v1 (`rules[].require`) | `test_policy_packs.py`, peer review |
| Pack promotion | Git tag → attester config rollout | Staged rollout, canary attestations |
| Regulatory change | New pack ID + hash; no escrow migration | `test_policy_evolution.py` |
| Jurisdiction packs | Per-country files under `data/policies/` | Scenario matrix per pack |

---

## Wallet taint

| Stage | Implementation | Verification |
|-------|----------------|--------------|
| Demo | `MockTaintProvider` | `test_wallet_taint.py` |
| Stub | `ChainalysisStubProvider` | Env-gated integration tests |
| Production | Chainalysis or TRM HTTP client | Contract tests with mocked HTTP; no live keys in CI |

---

## Smart contracts

| Item | Scope | Verification |
|------|-------|--------------|
| `SettlementEscrow` v1 | Base Sepolia / mainnet deploy | External audit (Trail of Bits / OZ class) |
| Slither | Zero high/medium | CI |
| Optional `SettlementEscrowV2` | Layered trust / 2-of-2 | Design spike only — see [`LAYERED_TRUST.md`](LAYERED_TRUST.md) |
| Schema versioning | New UID → new escrow lane | Migration doc, no in-place schema swap |

---

## Observability

| Item | Tool | Notes |
|------|------|-------|
| On-chain metrics | Dune ([`DUNE_QUERIES.md`](DUNE_QUERIES.md)) | Good first issue #4 |
| Indexer | EAS subgraph for `SettlementApproval` | Good first issue #5 |
| Public proof | BaseScan + EAS Scan links in README | `./scripts/public-attestation-smoke.sh` |

### Public testnet (operator-run)

Prerequisites in `.env` (never commit):

- `PROD_RPC_URL`, `PROD_ATTESTER_ADDRESS`, `PROD_ATTESTER_PRIVATE_KEY`

```bash
./scripts/deploy-public-testnet.sh
./scripts/public-attestation-smoke.sh
```

Paste resulting escrow and attestation UID into README «Public proof».

---

## Compliance and legal

| Item | Action |
|------|--------|
| Data | Production feeds — not `data/synthetic/` |
| Disclaimer | Attestations are operator-signed opinions, not legal title |
| Pilot | Bank SOW, fee-per-attestation, jurisdiction counsel |
| Security | Pen test before mainnet pilot |

---

## Milestones (from product roadmap)

| When | Target | Engineering focus |
|------|--------|-------------------|
| Q3 2026 | Exchange / RWA platform pilot | Hosted attester, multi-attester registry |
| Q4 2026 | Bank attester pilot (ASEAN) | HSM, live AML/taint, audit |
| 2027 | Multi-jurisdiction mainnet | Audited deploy, attester marketplace |

---

## How to contribute now

- Good first issues: [GitHub Issues](https://github.com/FUYOH666/attestrwa/issues?q=is%3Aissue+label%3A%22good+first+issue%22)
- Integrators: [`FOR_INTEGRATORS.md`](FOR_INTEGRATORS.md)
- Inbound: [`INBOUND_PLAYBOOK.md`](INBOUND_PLAYBOOK.md)
