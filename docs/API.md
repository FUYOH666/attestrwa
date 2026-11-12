# Attester API

The reference attester is a FastAPI service. Locally it listens on `http://127.0.0.1:8080`; interactive OpenAPI documentation is at `/docs`.

It serves **one** escrow on **one** chain, set by `ATTESTRWA_ESCROW_ADDRESS` and `ATTESTRWA_CHAIN_ID`. Requests about any other escrow or chain are refused.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/attest/settlement` | `X-API-Key` | Decide about one deal and anchor the decision. |
| `GET` | `/attest/{deal_id}` | — | Decisions made about a deal, with their live on-chain state. |
| `GET` | `/records/{deal_id}` | — | The latest decision record for a deal. |
| `GET` | `/records/by-hash/{record_hash}` | — | A record by its hash. |
| `POST` | `/verify` | — | Run the reference verifier on a record. |
| `GET` | `/attest/healthz` | — | Readiness: chain, escrow wiring, attester trust. |
| `GET` | `/healthz` | — | Liveness. Does not touch the chain. |

## POST /attest/settlement

The request names a deal. It cannot describe one: unknown fields are rejected.

| Field | Type | Meaning |
|---|---|---|
| `chain_id` | integer | Chain the escrow lives on. |
| `escrow` | address | Escrow contract. |
| `deal_id` | bytes32 | Identifier returned by `deposit()`. |
| `declared` | object | Values for the inputs the policy accepts as declarations. Optional. |

```bash
curl -s http://127.0.0.1:8080/attest/settlement \
  -H 'Content-Type: application/json' -H 'X-API-Key: local-demo-key' \
  -d '{
        "chain_id": 84532,
        "escrow": "0x2100fcdb4ba229e717dfba29cb21114e0f592c67",
        "deal_id": "0xe6d632bca96bf38c6f51d8c0128ac9674cf5a54a27bd3a3f9972b2913e4d4ab1",
        "declared": {"jurisdiction": "TH"}
      }'
```

Response:

| Field | Meaning |
|---|---|
| `decision`, `decision_code` | `approve` (1) or `reject` (2). |
| `failed_rules` | Ids of the rules that did not hold. |
| `record_hash` | Hash of the record, as anchored. |
| `attestation_uid`, `tx_hash` | The EAS attestation. |
| `reused` | `true` when a live decision already existed and was returned unchanged. |
| `envelope` | The decision record file ([format](../spec/DECISION_RECORD_v0.1.md)). |

The call is idempotent per deal. While a decision is live on-chain, the stored record is returned and nothing is attested. After the attestation has been revoked, the next call evaluates again and the new record's `supersedes` names the revoked attestation.

`declared` values are recorded as declared by the caller (`integrator:<name>`, from the API key) and are not verified. Only inputs the policy declares with `source: declared` may be supplied this way.

### Errors

| Status | When |
|---|---|
| `401` | Missing or invalid `X-API-Key`. |
| `404` | The escrow has no such deal. |
| `409` | The deal is already settled, or is at or within 30 seconds of its deadline. |
| `422` | Unknown request field; another escrow or chain; a declaration the policy does not accept from a caller; a missing or mistyped declaration. |
| `502` | The chain or a data source could not be read, or the attestation transaction failed. No decision is made. |
| `503` | The instance has no API keys, no attester key, or an inconsistent configuration. |

Error bodies are `{"detail": "…"}`.

## GET /attest/{deal_id}

```json
{
  "deal_id": "0x…",
  "deal_status": "open",
  "decisions": [
    {
      "attestation_uid": "0x…",
      "record_hash": "0x…",
      "decision": "reject",
      "on_chain": true,
      "attester": "0x…",
      "time": 1794459321,
      "expiration_time": 1794545711,
      "revoked": false,
      "decision_code": 2
    }
  ]
}
```

`deal_status` is `none`, `open`, `released` or `refunded`, read from the escrow now.

## POST /verify

The body is a record file. It is parsed strictly: duplicate keys, floats and invalid UTF-8 are answered with `422`, a body over 256 KB with `413`. Anything else returns `200` with a report, including records that fail:

```json
{
  "ok": true,
  "anchored": true,
  "verdict": "VERIFIED",
  "record_hash": "0x…",
  "counts": {"pass": 24, "fail": 0, "skip": 0},
  "checks": [{"id": "record.hash", "group": "Record", "status": "pass", "detail": "…"}]
}
```

The checks are those of `attestrwa verify`, run with this instance's RPC endpoint, policy file and registry file, with on-chain inputs re-queried.

## GET /attest/healthz

Reports `status` (`ok` or `degraded`), the escrow, EAS and schema UID, the policy and registry identities and hashes, the attester address, and whether the chain id matches, the escrow uses the expected schema and the escrow trusts the attester. It never returns the RPC URL or any key.

## Configuration

All settings are environment variables with the prefix `ATTESTRWA_`; [`.env.example`](../.env.example) lists them.

| Variable | Default | Meaning |
|---|---|---|
| `RPC_URL` | `http://127.0.0.1:8545` | JSON-RPC endpoint. |
| `CHAIN_ID` | `84532` | Chain id the attester serves. |
| `NETWORK` | `anvil-fork` | Label written into record files. |
| `ESCROW_ADDRESS` | — | The escrow the attester serves. Required. |
| `EAS_ADDRESS` | OP-stack predeploy | EAS contract. |
| `ATTESTER_PRIVATE_KEY` | — | Key that attests. Without it the instance is read-only. |
| `API_KEYS` | — | Comma-separated `name:key` pairs allowed to request decisions. |
| `POLICY_FILE` | `data/policies/settlement-demo-v2.yaml` | Policy pack. |
| `REGISTRY_FILE` | `data/registry/payees.json` | Payee registry. |
| `RECORDS_DIR` | `records` | Record store. |
| `ATTESTATION_TTL_SECONDS` | `86400` | Attestation lifetime; never beyond the deal's deadline. |

On-chain data sources, such as the sanctions oracle, are named by the policy pack and are not configured here.
