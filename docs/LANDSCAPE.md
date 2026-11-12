# Where AttestRWA fits

Checked on 2026-11-12. Text in quotation marks is taken from each project's own page; the rest is a one-line summary. Follow the links for what each project ships today.

## The short version

Gating a settlement on a compliance check is not new, and several projects do it well. AttestRWA does not try to be another gate. It is a format and a verifier for the **record** of a decision: which policy version was applied to which inputs from which sources, committed on-chain so a third party can check it afterwards. The escrow in this repository exists to show one complete use of that record.

## Neighbouring projects

| Project | What it is | Relation |
|---|---|---|
| [Predicate](https://predicate.io) | "Define transaction rules to secure financial products." Policies are evaluated off-chain and enforced before a transaction. | Decides whether a transaction may proceed. A decision record could describe such a decision; it does not make one. |
| [Chainlink Automated Compliance Engine](https://chain.link/automated-compliance-engine) | A compliance engine for on-chain policy enforcement, aimed at institutions. | Same as above: an engine, where AttestRWA is a record format. |
| [ERC-3643](https://eips.ethereum.org/EIPS/eip-3643) | A token standard whose transfers are checked against an on-chain identity registry. | Enforces eligibility inside the token on every transfer. An issuer using it needs no escrow; it may still want a record of why a holder was admitted. |
| [ERC-7943](https://eips.ethereum.org/EIPS/eip-7943) | A minimal interface for regulated assets: `canSend`, `canReceive`, `canTransfer`, frozen balances, forced transfers. | A possible input: a policy could read `canTransfer` as an `onchain` source. |
| [Circle Refund Protocol](https://github.com/circlefin/refund-protocol) | "A smart contract for stablecoin payment disputes." | A similar release-or-refund shape, decided by an arbiter. No record of the reasoning is part of it. |
| [Alkahest](https://github.com/arkhai-io/alkahest) | "Contract library and SDKs for conditional peer-to-peer escrow", with escrow, arbiter and obligation contracts built on EAS. | The closest in mechanism: general conditional escrow on EAS. AttestRWA's escrow is narrower; its contribution is the record and its verification. |
| [Fireblocks Policy Engine](https://www.fireblocks.com/platforms/governance-and-policy-engine/) | Transaction authorisation rules inside the Fireblocks platform. | Decisions and their audit trail live inside one vendor's system. A decision record is the portable counterpart. |
| [Ethereum Attestation Service](https://attest.org) | The attestation protocol AttestRWA anchors to. | The foundation. |
| ["RWA Disclosure Interfaces" proposal](https://ethereum-magicians.org/t/erc-proposal-rwa-disclosure-interfaces/28679) | A draft read interface for attestations about real-world assets. | Adjacent in intent: making attested facts about an asset readable. Worth following. |

## What is different here

1. **The unit is the decision, not the transfer.** One record per decision, with its inputs and their sources, kept by the party that made it and checkable by anyone it is given to.
2. **Vendor-neutral verification.** `attestrwa verify` needs the record, a public RPC endpoint and, for the policy checks, the policy file. It does not call the attester.
3. **Provenance per input.** The policy states where each value must come from; the record states where it came from; the verifier compares the two. A value that was only declared is visibly that.
4. **Policy versions are provable.** The hash of the policy file's bytes is in the attestation.

## What AttestRWA does not do

- It does not perform KYC, identity verification or transaction monitoring.
- It does not supply screening data beyond reading the public Chainalysis sanctions oracle.
- It does not make an attester's decision legally sufficient. In the regimes we know of, the obligation stays with the licensed entity that uses a tool, not with the tool.
- It does not provide custody; the escrow is a reference contract on a testnet.

## Who it is for

Teams that already make compliance decisions about settlements and have to account for them: tokenisation platforms, stablecoin payment providers, escrow and settlement operators, and the engineers who build for them. The record format is not specific to stablecoins or to real-world assets; `subject.kind` and `anchor.kind` leave room for other decisions and other anchors.
