# Contributing

Thanks for helping. Bug reports, policy packs, input sources, second implementations of the format and pull requests are all welcome.

## Reporting

- **Bugs**: open an [issue](https://github.com/FUYOH666/attestrwa/issues/new/choose) with what you ran, what you expected and what happened. For the verifier, attach the record file if you can.
- **Format questions**: if the specification is unclear or two readings are possible, that is a bug in the specification. Please report it.
- **Security issues**: privately, see [SECURITY.md](SECURITY.md).

## Development setup

[Foundry](https://book.getfoundry.sh/getting-started/installation) 1.7, [uv](https://docs.astral.sh/uv/) with Python 3.12+, and [pnpm](https://pnpm.io/installation) with Node 22.18+ for the web app.

```bash
git clone https://github.com/FUYOH666/attestrwa.git && cd attestrwa
./scripts/install-contract-deps.sh

(cd packages/attestrwa && uv sync && uv run pytest -q)     # no network, under a second
(cd apps/api && uv sync && uv run pytest -q)               # no network
(cd contracts && forge test)                               # real EAS contracts, no network
(cd apps/web && pnpm install --frozen-lockfile && pnpm test && pnpm run build)
```

The end-to-end paths need network access to the public Base Sepolia RPC, because they run on a fork:

```bash
./scripts/dev-chain.sh && ./scripts/deploy-contracts.sh
./scripts/e2e_rwa_flow.sh && ./scripts/e2e_rwa_reject.sh
./scripts/stop-demo-mode.sh
```

The scripts keep their state in `.run/` and stop only the processes they started. If ports 8545, 8080 or 3000 are taken, set `DEV_ANVIL_PORT`, `ATTESTRWA_API_PORT` or `ATTESTRWA_WEB_PORT`.

## Pull requests

- Keep the record format stable. A change to the canonical bytes, to the meaning of a member or to the rule semantics needs a new spec version and new test vectors; explain why in the pull request.
- Add or update tests for behaviour changes. A fix for a defect comes with a test that fails without it.
- Contract changes keep the invariants green and Slither clean at medium and above. If you suppress a detector, give the reason in the source.
- A new input source needs: the declaration it reads from the policy, what it writes into the record, and what a verifier can check about it.
- Run `uvx ruff@0.17.4 check . && uvx ruff@0.17.4 format .` in the Python projects and `forge fmt` in `contracts/`.
- Update `CHANGELOG.md` and the relevant file in `docs/`.
- No secrets, private keys, absolute personal paths or internal addresses in tracked files.

Coding agents: read [AGENTS.md](AGENTS.md) first.

## Licence

By contributing you agree that your contribution is licensed under [Apache-2.0](LICENSE).
