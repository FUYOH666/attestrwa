# Changelog

All notable changes to this project. Versions follow [Semantic Versioning](https://semver.org); the record format has its own version, stated in every record.

## 2.1.0 — unreleased

Decision records for decisions that have no escrow and no chain: the same record, signed with a key, with inputs that may come from documents, from the output of an AI model and from a named reviewer. Format 0.1, the contracts, the EAS schema and the attester are unchanged.

### Added

- **Decision Record v0.2** (`spec/DECISION_RECORD_v0.2.md`, `spec/decision-record-0.2.schema.json`). A second subject, `case`, anchored by an Ed25519 signature over the record hash; three source kinds, `document` (a count of documents cited by hash, or a value extracted from one), `model` (a value from a named field of a model output, cited by the hashes of the prompt and of the output) and `human` (a named person's statement). An escrowed deal may also be written as a 0.2 record.
- **Verifier**: for a signed record, `attestrwa verify --public-key KEY --document FILE --document-dir DIR`. New check groups: Documents (`documents.match`, `model.output`) and Signature (`signature.valid`, `signature.signer`). A record is verified only when the signature is valid and the signer is the key the caller trusts; without a trusted key the result is "consistent and signed". A file the caller names that the record does not cite is a failure.
- **Command line**: `attestrwa keygen` (the key file is created owner-only and never overwritten), `attestrwa public-key`, `attestrwa sign` (the key is read from `--key-file` or `ATTESTRWA_SIGNING_KEY` and is never printed).
- **Library**: `build_case_record`, `cited_files`, `attestrwa.signing`; `verify(..., documents=..., public_key=...)`.
- **Worked example** `examples/ai-classification/`: a customs classification proposed by two models, with a policy, the cited documents, an approving and a rejecting record, and the script that builds and signs them.
- **Test vectors** `spec/test-vectors/case-approve.json` and `case-reject.json`, signed with the public test key of RFC 8032, which the verifier reports as such.
- Tests pin the published 0.1 schema and vectors by hash, so a change to a published format cannot go unnoticed.

### Changed

- The check `record.structure` names the version it validated. For an escrowed deal the list of checks and the verdicts are the same as in 2.0.0.
- `.gitignore`: only the attester's own record store is ignored. The pattern `records/` also matched `examples/records/`, where published records belong.

### Fixed

In code that 2.0.0 already had:

- `decision.code` written as JSON `true` was accepted by the validator, although the specification and the schema require the integer.
- A deeply nested JSON body, or one with an integer of thousands of digits, made the strict loader raise: a traceback from the command line and a `500` from `POST /verify`. It is now an invalid record (`422`, exit code 2).

Found by an independent review of this version before release, and fixed:

- A record could name the identity point (or another point of small order) as its public key. No private key exists for it, yet one constant signature then passes for every record. Such keys are now refused in a record, as a signature key and as the trusted key.
- `attestrwa sign --out` could be pointed at the key file and replace the key with the signed record.
- An unreadable `--document-dir` raised instead of being reported as a usage error.
- A stray `signature` member in the envelope of an escrowed deal changed how that deal was checked.
- A model output containing `NaN` or `Infinity`, which are not JSON, was read as if it were.

## 2.0.0 — 2026-11-12

The project is rebuilt around the **decision record**. Version 1 was a hackathon prototype of an escrow gated by an attester; a review of its code and of the market showed that the gate already exists elsewhere, that the missing piece is a verifiable record of *why* a decision was made, and that the prototype's attester trusted its caller. Nothing from version 1 is compatible with version 2.

### Added

- **Decision Record v0.1** (`spec/`): normative specification, JSON Schema, canonicalisation and record test vectors.
- **`attestrwa` library and verifier** (`packages/attestrwa`): canonical JSON (a strict RFC 8785 subset), policy packs with a typed rule language that is never `eval`-ed, record construction and validation, and `attestrwa verify`, which recomputes the hash, compares the record with the EAS attestation and the escrow's state, checks policy and registry files, replays the rules and re-queries on-chain inputs. Two runtime dependencies.
- **`SettlementDecision` EAS schema**: `bytes32 dealId, address payee, address token, uint256 amount, uint8 decision, bytes32 policyHash, bytes32 recordHash`.
- **Policy packs that declare their sources**: for every input, its type, the kind of source and the source itself (subject field, contract call with arguments and per-chain contract, registry and party).
- **A real screening source**: the demo policy reads the Chainalysis sanctions oracle on Base at the evaluation block.
- **Attester routes** `GET /records/{deal_id}`, `GET /records/by-hash/{hash}`, `GET /attest/{deal_id}` (live on-chain state), `POST /verify`, and a readiness report at `GET /attest/healthz`.
- **Web UI**: `/settle` (live flow with the record and the verifier's report) and `/verify` (verification in the browser, with no server).
- **Scripts**: pinned contract dependencies, a fork-based local chain, end-to-end approve and reject paths that verify each record in strict mode, revocation, and publishing to Base Sepolia.
- **CI**: contract tests against the real EAS contracts, Slither, both Python suites with ruff, the web build, a scan for secrets and personal paths; a separate workflow for the fork-based end-to-end paths.
- Documentation rewritten: architecture, API, attestation schema, policy packs, threat model, landscape, roadmap, local demo, history; README in English and Russian.

### Changed

- **Escrow**: one check for `release` and `refund` (schema, recipient, trusted attester, not revoked, not expired, not older than the deposit, exact deal, expected decision). Deal ids are derived from chain, escrow, buyer and salt. `release` closes at the deadline. Token allowlist with a received-amount check. `Ownable2Step`; the constructor takes the owner and the attesters, and the deployer receives no privileges. Solidity 0.8.28.
- **Attester**: a request names a deal (chain, escrow, deal id) and nothing else; the deal is read from the escrow at a fixed block and inputs from the sources the policy declares. The decision is a pure function of policy and inputs. One live decision per deal; a new one only after revocation, naming what it replaces. API key on the write route. A failed transaction is an error.
- **Web**: dependencies reduced to Next.js, React and viem, all pinned. No wallet is needed on the local fork.
- Settings use the `ATTESTRWA_` prefix only.

### Fixed

Defects of version 1, each closed by a named test (see `docs/THREAT_MODEL.md`):

- The attester decided on caller-supplied facts, so screening could be bypassed.
- A buyer could obtain a rejection about a payee of their choosing and refund before the deadline.
- A revoked or expired rejection still unlocked an early refund.
- `release` and `refund` raced after the deadline.
- Deal ids could be occupied by someone else; decisions could be replayed across deployments.
- The write endpoint was unauthenticated and answered HTTP 200 when the transaction failed.
- An unconfigured screening provider answered "clean".
- A public-testnet script wrote a private key to a file that was not ignored by git.

Found by an independent review of version 2 before release, and fixed:

- The verifier checked the kind of an input's source but not the source itself.
- On-chain inputs were not required to belong to the evaluation block.
- `POST /verify` accepted records with duplicate JSON keys.
- Malformed records could raise instead of being reported as not verified.
- `supersedes` was not compared with the attestation's `refUID`.
- The rule parser accepted syntax of its host language beyond the published grammar.

### Removed

- The first prototype under `archive/v0.5/`, the `/api/demo/*` and `/api/scenarios/*` routes, the retrieval module, the Farcaster Frame, and the pitch, recording and outreach documents. They remain available at the tag `v1.1.0-hackathon-final`.
- The `SettlementApproval` schema of version 1 (it was never registered on a public network).

## Earlier versions

Versions 0.5 to 1.0.0 were the hackathon line. Their changelog and code are preserved at the tag [`v1.1.0-hackathon-final`](https://github.com/FUYOH666/attestrwa/blob/v1.1.0-hackathon-final/CHANGELOG.md).
