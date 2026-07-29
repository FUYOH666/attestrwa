# Standards Alignment Memo

How AttestRWA maps to open standards, institutions, and funding tracks — with
three concrete outreach actions.

Last updated: **2026-05-31**.

---

## 1. Enterprise Ethereum Alliance — Shibui

**Repo:** [EntEthAlliance/rnd-rwa-erc3643-eas](https://github.com/EntEthAlliance/rnd-rwa-erc3643-eas)  
**Standard:** ERC-3643 security tokens + EAS attestations  
**Release:** v0.4.0-rc1 (2026-04-20), Apache-2.0

### Alignment

| Layer | Shibui | AttestRWA |
|-------|--------|-----------|
| Question answered | Is wallet **eligible** to hold/receive security? | Is stablecoin **settlement** to payee bank-grade? |
| EAS usage | Multi-topic policy modules per claim topic | Single `SettlementApproval` schema per deal |
| On-chain consumer | `EASClaimVerifier.isVerified(wallet)` | `SettlementEscrow.release()` reads attestation |
| Attester model | Multiple trusted attesters per topic | Bank/regulated structure as attester |

**Conclusion:** Orthogonal, composable. Not competitive.

### Schema compatibility notes

- Shibui topics are **wallet-scoped**; AttestRWA fields are **deal-scoped**
  (`dealId`, `payeeAddress`, `payeeVerified`, `evidenceHash`).
- Recommended composition flow:
  1. Shibui verifies buyer/recipient wallet eligibility (KYC/AML topic).
  2. AttestRWA attests deal-specific payee authority and capital class.
  3. Escrow requires **both** (see RFC-0001).

### Action 1 — EEA / Shibui

**Status (2026-07-28):** [Issue #97](https://github.com/EntEthAlliance/rnd-rwa-erc3643-eas/issues/97) closed by @Redoudou — Shibui stays eligibility-only; AttestRWA composes externally (RFC-0001, `demo-composed-flow.sh`). **Do not reopen** or ask to register settlement topics in their repo.

**Follow-up:** LinkedIn acknowledgment — [`docs/outreach/linkedin-redwan-issue-97.md`](outreach/linkedin-redwan-issue-97.md).

**Future agents:** Use updated draft in [`OUTREACH_TARGETS.md`](OUTREACH_TARGETS.md) (no topic registration ask).

---

## 2. ERC-3643 Association

**Context:** [Ethereum Magicians — Improved ERC3643 with EAS](https://ethereum-magicians.org/t/erc-xxxx-improved-erc3643-with-eas/22463)  
**Members (2026):** DTCC, Fireblocks, Deloitte, Chainlink Labs, Ava Labs,
OpenZeppelin (per RedStone RWA Standards Report 2026).

### Alignment

ERC-3643+EAS proposals focus on **hierarchical bank-to-user attestations**
for cross-border RWA access. AttestRWA adds **deal settlement evidence**
without claiming token ownership.

| ERC-3643+EAS concept | AttestRWA mapping |
|----------------------|-------------------|
| Referenced attestations (bank → user) | Bank attester signs `SettlementApproval` |
| Reusable credentials | Closing Passport hash portable across platforms |
| Privacy-preserving verification | Off-chain evidence pack, on-chain `evidenceHash` |

### Open-source compliance modules

| Member | OSS signal | Settlement attestation? |
|--------|------------|-------------------------|
| OpenZeppelin | Contracts libraries | No public settlement schema found |
| Fireblocks | SDK/docs (mixed OSS) | Custody-focused, not EAS settlement |
| Shibui (EEA) | Full OSS verifier | Eligibility only |
| Centrifuge | GPL-2.0 protocol | Transfer hooks, no public EAS schema |

**Conclusion:** No published **settlement attestation** standard exists in
ERC-3643 OSS today. AttestRWA can propose a companion schema, not a fork
of ERC-3643.

### Action 2 — Centrifuge

**Type:** GitHub Discussion  
**Target:** [centrifuge/protocol discussions](https://github.com/centrifuge/protocol/discussions)  
**Title:** `Integration pattern: EAS SettlementApproval as transfer-hook input`  
**Body outline:** Point to `examples/integrate-centrifuge-hook/`, describe
read-only integration (no fork of Centrifuge core).

---

## 3. Ethereum Attestation Service

**Canonical contracts (Base / Superchain):**

| Contract | Address |
|----------|---------|
| SchemaRegistry | `0x4200000000000000000000000000000000000020` |
| EAS | `0x4200000000000000000000000000000000000021` |

**AttestRWA schema UID:** `0x1f64ec96216b0381dc4443b7378c57485f2217656537e8ea36f0b23af047cc96`

### Registry / indexing

- EAS Scan (Base Sepolia): schema view once registered on testnet
- Official indexer: `0x37AC6006646f2e687B7fB379F549Dc7634dF5b84` (Base)
- Custom fields require off-chain decode or custom indexer
  ([Builder Guide](https://mirror.xyz/0xeee68aECeB4A9e9f328a46c39F50d83fA0239cDF/doCr8LbTnKjiVlRHItbwAlmuGuw20oY1xKEANfPgi7U))

### Similar schemas in wild

Search did not surface a public **settlement payee verification** schema.
Closest: Coinbase verification schemas (identity), Shibui claim topics
(eligibility), credit rating experiments (`3c-financial-data-eas`).

### PayingResolver opportunity

[EAS PayingResolver example](https://github.com/ethereum-attestation-service/eas-contracts/blob/master/contracts/resolver/examples/PayingResolver.sol)
enables attester incentives on-chain. Maps to bank **fee per attestation**
without AttestRWA rent-seeking.

### Action 3 — EAS

**Type:** PR to eas-docs-site or eas-contracts-example  
**Target:** [ethereum-attestation-service/eas-contracts-example](https://github.com/ethereum-attestation-service/eas-contracts-example)  
**Title:** `Example: RWA settlement attestation + escrow release`  
**Body outline:** Minimal port of `SettlementEscrow` + schema registration
script; link to AttestRWA as reference implementation.

---

## 4. Base ecosystem

| Resource | Relevance |
|----------|-----------|
| [Base contracts docs](https://docs.base.org/base-chain/network-information/base-contracts) | Predeployed EAS addresses |
| [spire-labs/base-eas-contracts](https://github.com/spire-labs/base-eas-contracts) | L3 reads Coinbase attestations from L2 |
| [coinbase/verifications](https://github.com/coinbase/verifications) | Identity attestations on Base |

**Layered trust pattern:** Coinbase Account verification (who) + AttestRWA
SettlementApproval (deal) = programmable 2-of-2 for high-value RWA wires.

### Base grants (research — verify before apply)

| Program | Fit | Notes |
|---------|-----|-------|
| Base Builder Grants / ecosystem funds | High | Attestation infra on Base Sepolia |
| Base Batches / hackathon follow-on | Medium | SEABW 2026 momentum |
| Coinbase Developer Platform | Medium | Verifications composition |

Check current RFPs at [base.org/build](https://www.base.org/build) — URLs and
criteria change; do not cite stale amounts in public docs.

---

## 5. Regulators (narrative alignment only)

Public language from MAS, BoT, SFC on **permissioned DeFi** and
**tokenized deposits** aligns with machine-readable evidence trails —
not with AttestRWA claiming regulatory endorsement.

Use in narrative: AttestRWA provides **audit-grade on-chain evidence hash**;
banks remain decision authority.

---

## Summary: three concrete actions

| # | Target | Action | Owner | Due |
|---|--------|--------|-------|-----|
| 1 | EEA / Shibui | Issue: Settlement vs Eligibility composition | AttestRWA | Week 1 |
| 2 | Centrifuge | Discussion: EAS hook integration pattern | AttestRWA | Week 2 |
| 3 | EAS | PR: contracts-example RWA settlement | AttestRWA | Week 3–4 |

Draft messages: [`OUTREACH_TARGETS.md`](OUTREACH_TARGETS.md).
