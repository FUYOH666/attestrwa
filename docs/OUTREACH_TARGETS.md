# Outreach Targets

Three primary outreach actions from [`STANDARDS_ALIGNMENT.md`](STANDARDS_ALIGNMENT.md),
plus repo hygiene checklist.

Draft messages — customize before send. Link always: `./scripts/e2e_rwa_flow.sh`,
schema UID, RFC-0001.

---

## Target 1 — EEA / Shibui

| Field | Value |
|-------|-------|
| Repo | https://github.com/EntEthAlliance/rnd-rwa-erc3643-eas |
| Action | New Issue |
| Title | Proposal: composable Settlement + Eligibility EAS topics for RWA |
| Priority | P0 |

### Draft issue body

```markdown
## Context

AttestRWA (Apache-2.0) implements a **SettlementApproval** EAS schema +
programmable escrow for stablecoin RWA settlement on Base Sepolia. Shibui answers
*wallet eligibility* for ERC-3643; we answer *deal payee verification* — orthogonal layers.

RFC: https://github.com/FUYOH666/attestrwa/blob/main/docs/rfc/0001-settlement-eligibility-composition.md

## Proposal

1. Document composition: `isVerified(wallet)` + `SettlementApproval(dealId)`.
2. Point to external Apache-2.0 reference: `./scripts/demo-composed-flow.sh` and
   `examples/composed-eligibility-settlement/` in AttestRWA (no in-repo registration).

## Do not propose (learned from issue #97 closure)

- Registering settlement schemas or topics **inside** Shibui / rnd-rwa-erc3643-eas.
- Asking Shibui to host other teams' attester relationships or escrow layers.

Integration = call `isVerified()` and build settlement attestation **on top**.

## Evidence

- E2E: `./scripts/e2e_rwa_flow.sh` and `./scripts/e2e_rwa_reject.sh`
- Composed: `./scripts/demo-composed-flow.sh`
- Schema UID: `0x1f64ec96216b0381dc4443b7378c57485f2217656537e8ea36f0b23af047cc96`
- 85s demo: https://youtube.com/shorts/BipB2qPzZz0

## Non-goals

We are not proposing changes to ERC-3643 core or Shibui scope — only external
composition documentation.
```

---

## Target 2 — Centrifuge

| Field | Value |
|-------|-------|
| Repo | https://github.com/centrifuge/protocol |
| Action | New Discussion |
| Title | Integration pattern: read EAS SettlementApproval in transfer hook |
| Priority | P1 |

### Draft discussion body

```markdown
## Summary

AttestRWA provides a public EAS schema for **settlement decisions** (payee verified,
capital class, evidence hash) — not tokenization. We'd like to document a
**read-only** integration: Centrifuge transfer hook checks for a valid
SettlementApproval before processing async vault epochs.

## Cookbook

We added a minimal pattern (pseudocode + interface):

https://github.com/FUYOH666/attestrwa/tree/main/examples/integrate-centrifuge-hook

## Ask

- Feedback on hook placement (ERC-7540 deposit vs transfer hook).
- Interest in listing this as an external compliance module in Centrifuge docs.

No request to fork protocol core — attestation is consumed via EAS canonical contract on Base.
```

---

## Target 3 — Ethereum Attestation Service

| Field | Value |
|-------|-------|
| Repo | https://github.com/ethereum-attestation-service/eas-contracts-example |
| Action | Pull Request |
| Title | Example: RWA settlement attestation with escrow release |
| Priority | P1 |

### Draft PR outline

| File | Content |
|------|---------|
| `examples/rwa-settlement/README.md` | Flow diagram, link to AttestRWA as reference |
| `examples/rwa-settlement/SettlementEscrow.sol` | Minimal escrow (or submodule pointer) |
| `script/RegisterSchema.s.sol` | SettlementApproval schema registration |

**Note:** PR not opened from this research pass — branch ready for maintainer
submission when fork is prepared.

---

## Repo hygiene checklist

Execute on GitHub (owner: `FUYOH666`):

| Step | Command / UI | Status |
|------|--------------|--------|
| Rename repo to `attestrwa` | `gh repo rename attestrwa` | **Done** (2026-05-31) |
| Update description | "Settlement Attestation Layer for RWA — EAS + escrow on Base" | **Done** (2026-05-31) |
| Topics | `attestrwa`, `settlement-attestation`, … | **Done** (2026-05-31) |
| README pivot diagram | See [`PIVOT.md`](PIVOT.md) linked from README | **Done** |
| Enable GitHub Sponsors | Profile → Sponsors | Optional |
| Create good first issues | From [`OSS_OPERATING_PLAN_90DAY.md`](OSS_OPERATING_PLAN_90DAY.md) | **Done** ([#2–#6](https://github.com/FUYOH666/attestrwa/issues)) |

### Rename side effects

After rename, update:

- CI badge URLs in README
- `render.yaml` service name (if linked to repo)
- Hackathon submission links
- YouTube video description (optional)

GitHub redirects `bankable-property-network` → `attestrwa` automatically for a period.

---

## Contact log

| Date | Target | Action | Response |
|------|--------|--------|----------|
| 2026-05-31 | Shibui / EEA | [Issue #97](https://github.com/EntEthAlliance/rnd-rwa-erc3643-eas/issues/97) opened | **2026-07-28** @Redoudou closed out of scope — eligibility vs settlement boundary; compose via `isVerified()`, do not register our schemas in Shibui repo. **Do not reopen** unless they ask. |
| 2026-07-29 | Redwan Meslem | LinkedIn follow-up draft | [`docs/outreach/linkedin-redwan-issue-97.md`](outreach/linkedin-redwan-issue-97.md) — send manually; acknowledge + RFC-0001 link |
| 2026-05-31 | Centrifuge | [Issue #828](https://github.com/centrifuge/protocol/issues/828) (discussions disabled) | Awaiting response |
| — | EAS | PR | — |

Update this table when outreach is sent.
