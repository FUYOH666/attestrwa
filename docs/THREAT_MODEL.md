# Threat model

What the design guarantees, what it deliberately does not, and what remains open. No professional audit has been performed; this document is the project's own analysis.

## Guarantees

**Funds move only to the payee the buyer named, or back to the buyer.** The escrow has no other transfer path. An attester, the owner, or anyone holding either key can influence *which* of the two happens before the deadline, never the destination. After the deadline the buyer can always refund without anyone's cooperation.

**A decision counts only if it is exact and live.** The escrow acts on an attestation only when it uses the pinned schema, is addressed to this escrow, comes from a currently trusted attester, is neither revoked nor expired, was made after the deposit, and matches the deal's id, payee, token and amount.

**A verified record is the record the attester committed to, and the decision follows from it.** The verifier recomputes the hash, compares it with the on-chain commitment, checks every input against the source the policy declares, and re-runs the rules.

The escrow invariants are tested with the real EAS contracts: the escrow's balance always equals the sum of its open deals, every deposited unit is either held, released or refunded, and releases reach only the payee.

## Closed in version 2

Version 1 was a hackathon prototype. These defects were found by reading its code and are closed, each by a named test.

| Defect in v1 | Closed by | Test |
|---|---|---|
| The attester decided on fields supplied by the caller (buyer, payee, amount, KYC tier). A deal funded from one wallet could be described with another. | The request names a deal; the attester reads it from the escrow. Unknown request fields are rejected. | `test_request_fields_describing_the_deal_are_refused` |
| A buyer could request a decision about a payee of their choosing, receive a rejection for their deal id, and refund before the deadline: `refund` checked only the deal id. | `refund` and `release` share one check that requires an exact match of the deal. | `test_selfserve_rejection_about_another_payee_does_not_refund` |
| A revoked or expired rejection still unlocked an early refund. | Same shared check. | `test_refund_reverts_on_revoked_rejection`, `…_expired_rejection` |
| `release` worked after the deadline, racing the buyer's refund. | `release` is closed from the deadline on. | `test_release_is_closed_from_the_deadline_on` |
| Anyone could occupy a deal id before its buyer. | The id is derived from chain, escrow, buyer and salt. | `test_same_salt_different_buyers_do_not_collide` |
| A decision for one deployment could be used on another. | `recipient` must be the escrow; the id binds chain and escrow. | `test_decision_cannot_be_replayed_on_another_escrow` |
| The write endpoint was unauthenticated and returned HTTP 200 with a "decision" even when the transaction failed. | API key; a failed transaction is a 502 and nothing is stored. | `test_failed_transaction_is_an_error_not_a_decision` |
| One key was deployer, owner and attester. | The constructor takes owner and attesters; the deployer gets nothing. | `test_deployer_gets_no_privileges` |
| Screening was a two-address table; an unconfigured provider answered "clean". | The policy names an on-chain oracle; a failed read makes no decision. | `test_unreadable_screening_source_makes_no_decision` |

An independent review of version 2 by a second model family found no way to move funds or steer a decision, and seven defects in verification and conformance. They are fixed and listed in the [changelog](../CHANGELOG.md).

## Remaining risks

| Risk | Effect | Mitigation today | Later |
|---|---|---|---|
| **Attester key compromise** | The holder can approve deals whose payee should have been rejected, or grant early refunds. It cannot redirect funds. | Owner calls `setAttester(key, false)`; every outstanding decision of that attester stops being accepted. Owner and attester are different keys. | Key in a KMS or HSM; a quorum of attesters; per-deal attester. |
| **Owner key compromise** | The holder can trust a rogue attester, with the same bounded effect. It cannot block refunds after the deadline. | `Ownable2Step`. | Multisig; timelock on attester changes. |
| **Inputs that are not true** | A record proves the decision follows from its inputs, not that a registry entry or a declaration is correct. Address-list screening says nothing about a new wallet. | Every input carries its source; declared inputs are marked as such. | More verifiable sources; signed provider responses. |
| **Record withholding** | The escrow acts on the attestation alone; a verifier without the record cannot check anything. | The verifier reports "not checked", never "verified". | Content-addressed publication of records, or a hash-addressed store operated independently. |
| **Griefing by premature evaluation** | An authenticated integrator could request a decision before the registry is ready and obtain a rejection, letting the buyer exit early. Nothing is seized. | API key; revoke, then decide again. | Evaluation only after a number of confirmations; a dispute window. |
| **Several trusted attesters** | With more than one attester trusted, an approval from one and a rejection from another could both be live; the first transaction wins. | Deploy with one attester. | Per-deal attester; quorum. |
| **A public rejection** | An on-chain "reject" naming a payee address is public information about that address. | The reason stays off-chain. | Approvals only; private anchors. |
| **Token behaviour** | A token that can freeze an address makes a transfer to it revert. A frozen payee blocks release (the buyer refunds after the deadline); a frozen buyer blocks the refund. | Token allowlist; a deposit that does not arrive in full is rejected. | A pull-payment fallback. |
| **Attester gas exhaustion** | Each decision costs gas. | API key; one decision per deal. | Rate limits; fee recovery. |
| **Lost crash window** | If the attester stops between attesting and storing the record, the attestation exists without a stored record. | The next request finds no stored record and decides again. | Write-ahead record store. |
| **Chain history** | On-chain inputs are re-queried at their recorded block; public endpoints may stop serving old state. | The verifier reports that check as skipped. | An archive endpoint for audits. |

## Static analysis

Slither is run in CI and fails on any finding of medium severity or above. One detector is suppressed, with the reason in the source: `reentrancy-balance` on the balance check around the token transfer in `deposit`. Every state-changing function of the contract is `nonReentrant`, so a token callback cannot move the escrow's funds between the two balance reads.

## Reporting

See [SECURITY.md](../SECURITY.md).
