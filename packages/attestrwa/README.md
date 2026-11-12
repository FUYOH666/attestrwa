# attestrwa

Python library and command line tool for **AttestRWA decision records**: a
canonical, hash-committed record of why a compliance decision about a
settlement was made, plus an independent verifier that checks the record
against its on-chain EAS attestation and replays its rules.

```bash
uvx --from "git+https://github.com/FUYOH666/attestrwa#subdirectory=packages/attestrwa" \
  attestrwa verify record.json --rpc https://sepolia.base.org
```

Format specification: [`spec/DECISION_RECORD_v0.1.md`](https://github.com/FUYOH666/attestrwa/blob/main/spec/DECISION_RECORD_v0.1.md).
Project: <https://github.com/FUYOH666/attestrwa>.
