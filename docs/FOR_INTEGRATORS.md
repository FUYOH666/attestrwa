# For integrators

One-page guide for RWA platforms, banks, and OSS contributors landing on
[AttestRWA](https://github.com/FUYOH666/attestrwa).

## What this is

**Settlement attestation primitive** — public EAS schema + programmable escrow.
We answer: *is this stablecoin movement to this payee bank-grade?*

We do **not** tokenize property, issue stablecoins, or run KYC. See
[`PRODUCT_THESIS.md`](PRODUCT_THESIS.md).

## On-chain primitives

| Item | Value |
|------|-------|
| EAS (Base / Superchain) | `0x4200000000000000000000000000000000000021` |
| SchemaRegistry | `0x4200000000000000000000000000000000000020` |
| `SettlementApproval` schema UID | `0x1f64ec96216b0381dc4443b7378c57485f2217656537e8ea36f0b23af047cc96` |

Full field list: [`ATTESTATION_SCHEMA.md`](ATTESTATION_SCHEMA.md).

## Run the demo (30 minutes)

```bash
./scripts/demo-mode.sh
./scripts/e2e_rwa_flow.sh    # happy path
./scripts/e2e_rwa_reject.sh    # payee mismatch reject
```

Health check:

```bash
curl -s http://localhost:8080/attest/healthz | jq .
```

## Integrate (read-only)

1. Compute `dealId` from your pool / vault state.
2. Call attester off-chain or read existing EAS attestation on-chain.
3. Gate your settlement on `payeeVerified == true` and `capitalClass < 2`.

Cookbooks:

- [`rfc/0001-settlement-eligibility-composition.md`](rfc/0001-settlement-eligibility-composition.md) — compose with Shibui / Coinbase verify
- [`../examples/integrate-centrifuge-hook/README.md`](../examples/integrate-centrifuge-hook/README.md)
- [`../examples/composed-eligibility-settlement/README.md`](../examples/composed-eligibility-settlement/README.md)

API: [`API_CONTRACT.md`](API_CONTRACT.md) · `POST /attest/settlement`

## Policy packs

Banks fork YAML rules under [`data/policies/`](../data/policies/):

```bash
ATTESTRWA_POLICY_FILE=data/policies/asean-property-settlement-v1.yaml
```

Responses include `policy_pack_id` and `policy_hash` (bound into `evidence_hash`).

**Policy evolution** (regulatory change without escrow migration):

```bash
./scripts/simulate-policy-evolution.sh
uv run --directory apps/api python ../../scripts/run_rwa_scenarios.py --check
```

See [`POLICY_EVOLUTION.md`](POLICY_EVOLUTION.md) and [`PRODUCTION_ROADMAP.md`](PRODUCTION_ROADMAP.md).

## Production blockers

No mainnet deploy without external audit. See [`SECURITY.md`](SECURITY.md):

- Mock wallet taint (not Chainalysis live)
- Single attester demo key (HSM required for production)
- Testnet-only at hackathon stage

## Public testnet (optional)

```bash
# Requires PROD_* keys in .env — see .env.example
./scripts/deploy-public-testnet.sh
./scripts/public-attestation-smoke.sh
```

## Get in touch

Open an issue or discussion on GitHub. For inbound types see
[`INBOUND_PLAYBOOK.md`](INBOUND_PLAYBOOK.md).
