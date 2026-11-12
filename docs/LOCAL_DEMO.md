# Local demo

Everything runs on your machine against a fork of Base Sepolia. A fork rather than an empty chain, because the real EAS contracts and the real Chainalysis sanctions oracle are already there: attestations go through production EAS code and screening reads production data, with no faucet and no wallet.

## Requirements

- [Foundry](https://book.getfoundry.sh/getting-started/installation) 1.7 (`anvil`, `forge`, `cast`)
- [uv](https://docs.astral.sh/uv/) with Python 3.12 or newer
- [pnpm](https://pnpm.io/installation) with Node 22.18 or newer (only for the web UI)
- Network access to `https://sepolia.base.org` (the fork's upstream)

## Run

```bash
./scripts/demo-mode.sh
```

| What | Where |
|---|---|
| Chain | `http://127.0.0.1:8545`, chain id 84532 |
| Attester | `http://127.0.0.1:8080` (OpenAPI at `/docs`) |
| Web UI | `http://localhost:3000` |
| Logs, pids, records | `.run/` (not tracked) |
| Chain and deployment state | `.dev-chain.state`, `deployments/anvil-fork.json` (not tracked) |

The script is idempotent: it reuses a running chain, keeps its deployment, and restarts the attester only if it serves another escrow. Stop with `./scripts/stop-demo-mode.sh`, which stops only the processes it started.

Ports can be changed with `DEV_ANVIL_PORT`, `ATTESTRWA_API_PORT` and `ATTESTRWA_WEB_PORT`.

## The two paths

```bash
./scripts/e2e_rwa_flow.sh
```

1. The buyer mints demo tokens and deposits 580 mUSDC for the registered payee.
2. The attester is asked about the deal and decides APPROVE.
3. The record is fetched and verified in strict mode against the chain, the policy file and the registry file.
4. A second request returns the same decision.
5. `release` pays the payee.

```bash
./scripts/e2e_rwa_reject.sh
```

1. The buyer deposits for a payee that is not in the registry.
2. Three attempts to steer the attester are refused: no API key (401), a caller-supplied payee (422), a declared registry result (422).
3. An early refund without a decision reverts.
4. The attester decides REJECT, naming the failed rule.
5. The record is verified in strict mode.
6. `release` with the rejection reverts; `refund` returns the deposit.

Both scripts use only `cast`, `curl` and the verifier, so they double as a transcript of the protocol.

## By hand

Open <http://localhost:3000/settle>, choose a deal, deposit, request a decision, and settle. On the fork the page signs with the public development account, so there is nothing to install. The decision record appears with every input next to its source, followed by the verifier's report.

Open <http://localhost:3000/verify> and paste a record file, for example `.run/last-approve.json`. The page checks it using your browser and the RPC endpoint only.

## Roles

The scripts use accounts of the publicly known Foundry development mnemonic. They exist for the fork only.

| Index | Role |
|---|---|
| 0 | Deployer. Receives no privileges. |
| 1 | Buyer. |
| 2 | Payee, listed in `data/registry/payees.json`. |
| 3 | A payee that is not listed. |
| 4 | Attester. |
| 5 | Escrow owner. |

## Revoking and deciding again

```bash
./scripts/revoke-attestation.sh 0x<attestation uid>
```

After a revocation the next request for that deal is evaluated again. The new record's `supersedes` names the revoked attestation, the new attestation's `refUID` references it, and the old record no longer verifies.

## Notes

- The first decision on a fresh fork takes about ten seconds: Anvil fetches the EAS contract's storage from the public RPC on first use.
- The fork has the same chain id as Base Sepolia. Records made on it carry `"network": "anvil-fork"` in their envelope and verify only against the fork.

## Public testnet

```bash
./scripts/deploy-public-testnet.sh
```

deploys to Base Sepolia from keys in `.env` (see [`.env.example`](../.env.example)), runs one approval and one rejection, and writes `deployments/base-sepolia.json` and `examples/records/base-sepolia/`. It needs a funded testnet account and has not been run yet.
