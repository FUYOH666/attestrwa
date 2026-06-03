# Compliance policy packs

YAML rule packs consumed by the AttestRWA attester service via
[`compliance_dsl.py`](../../apps/api/src/app/services/compliance_dsl.py).

## Format (v1)

Only the `rules` list with `require` boolean expressions is parsed today.
Metadata (`pack_id`, `scenarios`) belongs in YAML comments or a separate
`*.meta.yaml` file.

```yaml
rules:
  - id: payee-must-match-developer-feed
    require: payee_verified == true
  - id: capital-not-red
    require: capital_class < 2
```

### Context variables

| Name | Type | Source |
|------|------|--------|
| `payee_verified` | bool | Developer feed lookup |
| `capital_class` | int | 0=green, 1=amber, 2=red |
| `amount_usdc` | int | Settlement amount (base units) |
| `buyer_kyc_tier` | int | Request field (0–4) |
| `jurisdiction` | str | ISO 3166-1 alpha-2 |

See [`default_attestrwa_policy.yaml`](../synthetic/policies/default_attestrwa_policy.yaml)
for the baseline demo policy.

| Pack | File |
|------|------|
| ASEAN v1 | `asean-property-settlement-v1.yaml` |
| ASEAN strict (evolution demo) | `asean-property-settlement-v1-strict.yaml` |

## Selecting a pack

```bash
# In .env
ATTESTRWA_POLICY_FILE=data/policies/asean-property-settlement-v1.yaml
```

Default (if unset): `data/synthetic/policies/default_attestrwa_policy.yaml`.

## Contributing

Submit PRs with new packs under this directory. Each pack needs:

1. Valid `rules[].require` expressions
2. A pytest vector in `apps/api/tests/test_policy_packs.py`

See [`CONTRIBUTING.md`](../../CONTRIBUTING.md).
