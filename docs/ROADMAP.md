# Roadmap

No dates. Items move up when they are done, not when a quarter ends.

## Now — version 2.1

- Decision Record v0.1: specification, JSON Schema, test vectors.
- `attestrwa` library and verifier.
- `SettlementEscrow` v2 with one decision gate, tested against the real EAS contracts.
- Reference attester that reads the deal from chain and its inputs from declared sources.
- Local demo on a fork of Base Sepolia; web UI with a browser verifier.
- Decision Record v0.2: records for decisions that have no escrow, signed with Ed25519 instead of attested on-chain, with inputs from documents, from the output of an AI model and from a named reviewer. `attestrwa sign` and `keygen`; a [worked example](../examples/ai-classification) on a customs classification.

## Next

- **Public Base Sepolia deployment.** Register the schema, deploy the escrow, run one approval and one rejection, and publish their records under `examples/records/base-sepolia/`, so that the verifier can be tried against a public chain with one command. `scripts/deploy-public-testnet.sh` is ready; it needs a funded testnet account.
- **Hosted verifier page.** Serve `/verify` statically with the published records preloaded.
- **Co-signatures.** A reviewer signs their own sign-off with their own key, so that a `human` input stops being only the statement of the pipeline that wrote the record.
- **A time anchor for signed records.** Publish the hash of a signed record in an EAS attestation or a transparency log, so that "this record existed by then" and "it has since been replaced" can be checked. Today both are the signer's word.
- **Key publication.** A documented way to state which key signs for whom: a well-known file, a DNS record, an attestation.
- **Signed model outputs.** Check a provider's own signature over a model output where one exists, so that "a model produced this" is no longer only a statement of the signer.
- **More input sources.** [ERC-7943](https://eips.ethereum.org/EIPS/eip-7943) `canTransfer`, EAS attestations held by a party (for example identity attestations), and a signed-response format for off-chain providers.
- **Rule replay and signed records in the browser.** A second implementation of the rule language and of the signature check, tested against shared vectors. The browser verifier handles format 0.1 only.
- **PyPI release** of `attestrwa`.

## Later

- Attester key in a KMS; a quorum of attesters; a per-deal attester.
- Private or selectively disclosed records: commit to a salted tree of inputs rather than to one hash.
- An evaluation trigger that waits for confirmations instead of an API call.
- A professional audit of the escrow. No mainnet deployment before it.
- Inputs that are present only under a condition (a sign-off required above a threshold and absent below it).

## Not planned

- Performing KYC or supplying screening data.
- Issuing tokens or a stablecoin.
- Operating a custody service.
