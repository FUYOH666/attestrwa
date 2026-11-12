## What does this pull request do

<!-- One to three sentences: what changes and why. -->

## Area

- [ ] Record format or specification (`spec/`)
- [ ] Library and verifier (`packages/attestrwa`)
- [ ] Contracts (`contracts/`)
- [ ] Attester (`apps/api`)
- [ ] Web UI (`apps/web`)
- [ ] Scripts, CI or docs

## Checks

- [ ] `cd packages/attestrwa && uv run pytest -q`
- [ ] `cd apps/api && uv run pytest -q`
- [ ] `cd contracts && forge fmt --check && forge test`, and Slither clean at medium and above if a contract changed
- [ ] `cd apps/web && pnpm test && pnpm run build` if the web app changed
- [ ] `./scripts/e2e_rwa_flow.sh` and `./scripts/e2e_rwa_reject.sh` if the flow changed
- [ ] `CHANGELOG.md` and the affected docs are updated
- [ ] No secrets, private keys, personal paths or internal addresses in tracked files

## Format impact

<!-- Does this change the canonical bytes of a record, the meaning of a member,
     the rule semantics or the EAS schema? If yes, say which spec version it targets. -->
