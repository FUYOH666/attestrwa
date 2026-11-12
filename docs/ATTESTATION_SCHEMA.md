# The on-chain anchor: `SettlementDecision`

A decision record is anchored by an [EAS](https://attest.org) attestation. The attestation carries what the escrow must enforce and two hashes that commit to everything else.

## Schema

The schema string is kept in one file, [`spec/eas-schema.txt`](../spec/eas-schema.txt); the library, the contract tests and the deploy script all read or check it.

```
bytes32 dealId, address payee, address token, uint256 amount, uint8 decision, bytes32 policyHash, bytes32 recordHash
```

| Field | Meaning |
|---|---|
| `dealId` | The deal, as the escrow identifies it. |
| `payee`, `token`, `amount` | The deal's terms, as held by the escrow. |
| `decision` | 1 approve, 2 reject. Any other value is never acted on. |
| `policyHash` | SHA-256 of the policy pack's bytes. |
| `recordHash` | keccak256 of the canonical bytes of the decision record. |

Schema UID, with no resolver and revocable:

```
0x1a86145e70ac5055683604a56201574b2c9edf0512ad08fc1368a9e7cb565135
```

It is `keccak256(abi.encodePacked(schema, address(0), true))`, the formula of the EAS SchemaRegistry, and is the same on every chain. Print it with `attestrwa schema-uid`.

Fields of the EAS envelope:

| EAS field | Value |
|---|---|
| `recipient` | The escrow contract. |
| `expirationTime` | Evaluation time plus the attester's TTL, never later than the deal's deadline. |
| `revocable` | `true`. |
| `refUID` | The attestation this decision replaces, or zero. |

## What the escrow checks

`release(dealId, uid)` and `refund(dealId, uid)` call one internal function, `_checkDecision`, which reverts unless all of the following hold, in this order:

| Check | Error on failure |
|---|---|
| The attestation exists | `AttestationNotFound` |
| It uses the `SettlementDecision` schema | `AttestationWrongSchema` |
| It is addressed to this escrow | `AttestationWrongRecipient` |
| Its attester is trusted now | `AttesterNotTrusted` |
| It has not been revoked | `AttestationRevoked` |
| It has not expired | `AttestationExpired` |
| It was made no earlier than the deposit | `AttestationPredatesDeposit` |
| Its data is exactly seven words | `AttestationMalformed` |
| `dealId`, `payee`, `token` and `amount` equal the deal's | `Attestation…Mismatch` |
| `decision` is the one this path needs | `AttestationDecisionMismatch` |

`release` needs `decision == 1` and is closed from the deadline on. `refund` is callable by the buyer only: with `uid == 0` once the deadline has passed, or at any time with a decision of 2.

The contract does not read `policyHash` or `recordHash`. They exist for verifiers.

## Deal identifiers

```
dealId = keccak256(abi.encode(block.chainid, address(escrow), buyer, salt))
```

`deposit(salt, …)` derives the id and returns it; `computeDealId(buyer, salt)` gives it in advance. Binding the id to the buyer means nobody else can occupy it. Binding it to the chain and the escrow means a decision cannot be replayed on another deployment.

## Deployments

| Network | Status |
|---|---|
| Local fork of Base Sepolia | `./scripts/dev-chain.sh && ./scripts/deploy-contracts.sh` registers the schema through the real SchemaRegistry and deploys the escrow. |
| Base Sepolia | Not deployed yet. `./scripts/deploy-public-testnet.sh` does it and writes `deployments/base-sepolia.json`. |
| Mainnet | None, by design, until the contract has been audited. |

Schema registration is permissionless and idempotent: the deploy script registers the schema only if the registry does not already have it.
