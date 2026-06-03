# RWA Scenario Simulation Report

Generated: 2026-06-03T05:09:53.043014+00:00

**Result:** 3/3 scenarios matched expected attester outcomes.

Source: [`data/synthetic/rwa/scenarios.json`](../data/synthetic/rwa/scenarios.json)

Regenerate:

```bash
uv run --directory apps/api python ../../scripts/run_rwa_scenarios.py
```

## `happy-bangkok-condo` — PASS

**Bangkok Landmark — clean USDC settlement**

| Field | Expected | Actual |
|-------|----------|--------|
| decision | approve | approve |
| capital_class | 0 | 0 |
| payee_verified | True | True |
| policy_pack_id | — | default-attestrwa-policy |

## `payee-mismatch-srl` — PASS

**Siam Riverside anchor case — payee mismatch reject**

| Field | Expected | Actual |
|-------|----------|--------|
| decision | reject | reject |
| capital_class | 0 | 0 |
| payee_verified | False | False |
| policy_pack_id | — | default-attestrwa-policy |

## `capital-red-mixer-touch` — PASS

**Off-platform buyer wallet with mixer history**

| Field | Expected | Actual |
|-------|----------|--------|
| decision | reject | reject |
| capital_class | 2 | 2 |
| payee_verified | True | True |
| policy_pack_id | — | default-attestrwa-policy |

