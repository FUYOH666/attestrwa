# Roadmap

No dates. Items move up when they are done, not when a quarter ends.

## Now — version 2.0

- Decision Record v0.1: specification, JSON Schema, test vectors.
- `attestrwa` library and verifier.
- `SettlementEscrow` v2 with one decision gate, tested against the real EAS contracts.
- Reference attester that reads the deal from chain and its inputs from declared sources.
- Local demo on a fork of Base Sepolia; web UI with a browser verifier.

## Next

- **Public Base Sepolia deployment.** Register the schema, deploy the escrow, run one approval and one rejection, and publish their records under `examples/records/base-sepolia/`, so that the verifier can be tried against a public chain with one command. `scripts/deploy-public-testnet.sh` is ready; it needs a funded testnet account.
- **Hosted verifier page.** Serve `/verify` statically with the published records preloaded.
- **More input sources.** [ERC-7943](https://eips.ethereum.org/EIPS/eip-7943) `canTransfer`, EAS attestations held by a party (for example identity attestations), and a signed-response format for off-chain providers.
- **Records without an escrow.** A record signed by the attester (EIP-712) and anchored by a plain attestation, for decisions that gate nothing on-chain.
- **Rule replay in the browser.** A second implementation of the rule language, tested against shared vectors.
- **PyPI release** of `attestrwa`.

## Later

- Attester key in a KMS; a quorum of attesters; a per-deal attester.
- Private or selectively disclosed records: commit to a salted tree of inputs rather than to one hash.
- An evaluation trigger that waits for confirmations instead of an API call.
- A professional audit of the escrow. No mainnet deployment before it.
- Decision records for subjects other than escrowed deals.

## Not planned

- Performing KYC or supplying screening data.
- Issuing tokens or a stablecoin.
- Operating a custody service.
