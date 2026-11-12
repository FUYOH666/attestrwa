# History

**May 2026.** AttestRWA began as a submission to the SEA Blockchain Week 2026 hackathon. An earlier prototype about bank-side checks for property purchases in Thailand was turned into an on-chain idea: a stablecoin escrow that releases only when an attester has signed an EAS attestation approving the deal.

**June to July 2026.** The prototype was published and discussed with maintainers of adjacent projects. The clearest feedback was a boundary: eligibility ("may this wallet hold this asset?") and settlement decisions are different layers, and a settlement layer should compose with eligibility systems through their public interfaces rather than extend them.

**November 2026: version 2.** A review of the prototype against the market and against its own code led to three conclusions.

1. Gating a settlement on an attested decision is already built by others, and built well. A standalone "escrow plus attester" had no evident buyer.
2. What was not available as an open, vendor-neutral piece was the record behind a decision: which policy version, which inputs from which sources, checkable by a third party after the fact.
3. The prototype's attester trusted its caller. It decided on facts supplied in the request, which made its central guarantee hollow.

Version 2 therefore rebuilt the project around the decision record, kept the escrow as its reference consumer, moved the trust boundary to where it belongs, and removed everything that served only the pitch.

The state of the repository before this rework, including the first prototype under `archive/v0.5/`, is preserved at the tag [`v1.1.0-hackathon-final`](https://github.com/FUYOH666/attestrwa/tree/v1.1.0-hackathon-final).
