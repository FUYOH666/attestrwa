# attestrwa

Python library and command line tool for **AttestRWA decision records**: a
canonical, hash-committed record of why a decision was made (policy, inputs
and their sources, rule results), plus an independent verifier that replays
the rules and checks the record against its anchor: an on-chain EAS
attestation for an escrowed settlement, or an Ed25519 signature for a
decision with no chain, such as one made with an AI model.

```bash
uvx --from "git+https://github.com/FUYOH666/attestrwa#subdirectory=packages/attestrwa" \
  attestrwa verify record.json --rpc https://sepolia.base.org
```

```bash
attestrwa verify record.json --policy policy.yaml --document-dir ./files --public-key 0x… --strict
attestrwa keygen --out signing.key && attestrwa sign draft.json --key-file signing.key --out record.json
```

Format specifications: [`spec/DECISION_RECORD_v0.1.md`](https://github.com/FUYOH666/attestrwa/blob/main/spec/DECISION_RECORD_v0.1.md)
(escrowed settlements, EAS) and [`spec/DECISION_RECORD_v0.2.md`](https://github.com/FUYOH666/attestrwa/blob/main/spec/DECISION_RECORD_v0.2.md)
(signed records, documents, model outputs, sign-offs).
Project: <https://github.com/FUYOH666/attestrwa>.
