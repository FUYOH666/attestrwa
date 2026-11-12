# Security

AttestRWA is a testnet reference implementation. It has had no professional security audit and is not deployed to mainnet.

## Supported versions

Security fixes go to the latest release on `main`.

## Reporting a vulnerability

Please report privately first, not in a public issue:

- GitHub [private vulnerability reporting](https://github.com/FUYOH666/attestrwa/security/advisories/new)
- Email: [private@scanovich.ai](mailto:private@scanovich.ai)
- Telegram: [@ScanovichAI](https://t.me/ScanovichAI)

You will get an answer within a few days. Please include the component (contract, library, attester, web UI, scripts), the commit or release, and steps to reproduce: a Foundry test, a `cast` or `curl` command, or a record file. Never send private keys.

Reports are credited in the changelog unless you prefer otherwise. There is no bug bounty.

## Scope

In scope:

- ways funds in `SettlementEscrow` could move to anyone other than a deal's payee or buyer, or be locked;
- ways a caller could obtain a decision the policy and the sources do not support;
- ways a record could pass `attestrwa verify` although it was altered or does not match the chain;
- escapes from the rule language, and inputs that crash the verifier or the attester.

Out of scope:

- anything that requires a compromised attester or owner key, beyond what the [threat model](docs/THREAT_MODEL.md) already states;
- the demo token `MockUSDC`, which anyone may mint by design;
- vulnerabilities in EAS, OpenZeppelin, Foundry or other upstream projects; please report those upstream.

## Deployment notes

- The attester signs on-chain transactions. Give it a key that is trusted by the escrow and is **not** the escrow owner, and keep that key out of files that are tracked or shared.
- `POST /attest/settlement` requires an API key; without `ATTESTRWA_API_KEYS` the instance refuses every request. Do not expose the attester without TLS in front of it.
- The local scripts use the publicly known Foundry development mnemonic. Its accounts must never hold value on a real network.
- The design's guarantees and remaining risks are in [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).
