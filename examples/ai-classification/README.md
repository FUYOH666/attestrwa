# Example: a decision made with an AI model

A customs broker's pipeline asks a model for the tariff code of a product. A policy decides whether that answer may be used: two models must agree, the model must be confident, the description must be backed by documents, and a named reviewer must sign off. The decision record says, afterwards and to anyone, what the model answered, what it was shown, which rules held and who signed.

This is [Decision Record v0.2](../../spec/DECISION_RECORD_v0.2.md): the same record as for a settlement, signed with a key instead of attested on-chain. No blockchain, no network, no account.

Everything here is synthetic: the companies, the documents, the model outputs (written by hand, not produced by a model) and the reviewer. The tariff codes are illustrative, not classification advice.

## Verify it

From the repository root:

```bash
uvx --from ./packages/attestrwa attestrwa verify examples/ai-classification/records/approve.json \
  --policy examples/ai-classification/policy.yaml \
  --document-dir examples/ai-classification/case-approve \
  --public-key 0xd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a \
  --strict
```

```text
AttestRWA decision record: examples/ai-classification/records/approve.json
  case      CLS-2026-000412: HS classification: stainless steel vacuum bottle VB-500
  decision  APPROVE under customs-classification-demo@1.0.0
  anchor    Ed25519 signature, key 0xd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a

Record
  ✓ record.structure  valid Decision Record v0.2
  ✓ record.hash       record hash 0x8faf64dfec101f94ca74f5ab7007e059575084c52abba9375a2651e473d45631
  ✓ record.inputs     6 input(s); counts of documents follow from the documents cited
  ✓ record.replay     5 rule(s) re-evaluated from the recorded inputs; all results match
  ✓ record.decision   decision APPROVE follows from the rules

Policy
  ✓ policy.match  policy file customs-classification-demo@1.0.0 hashes to 0x17c6199e…6d4897; rules, input types and input sources match the record

Documents
  ✓ documents.match  all 7 cited file(s) supplied; every hash matches
  ✓ model.output     3 value(s) equal the named field of the model output

Signature
  ✓ signature.valid   valid Ed25519 signature by 0xd75a9801…07511a (a published test key: anyone can produce this signature)
  ✓ signature.signer  signed by the key you trust (a published test key: anyone can produce this signature)

Result: VERIFIED (signed with a published test key: consistent, not authentic): 10 passed, 0 failed, 0 skipped
```

The second record, [`records/reject.json`](records/reject.json) with `--document-dir examples/ai-classification/case-reject`, is a refusal: the two models disagreed, neither was confident, one document was on file, and the reviewer declined. All four reasons are in the record.

Now change the invoice and name the changed file:

```bash
sed 's/18,400.00/1,840.00/' examples/ai-classification/case-approve/commercial-invoice.txt > /tmp/invoice-edited.txt
uvx --from ./packages/attestrwa attestrwa verify examples/ai-classification/records/approve.json \
  --document /tmp/invoice-edited.txt
```

```text
Documents
  ✗ documents.match  /tmp/invoice-edited.txt: not cited by this record, or altered since it was made

Result: NOT VERIFIED
```

Edit the record instead (raise a confidence, flip the decision, name another reviewer) and the hash, the replay of the rules, the model output or the signature catches it.

## What is in the record

| Input | Value in `approve.json` | Source | What a verifier checks |
|---|---|---|---|
| `hs_code` | `961700` | field `hs_code` of the output of `classifier-demo-1` | The output file is the one cited; the field holds this value. |
| `confidence_pct` | `96` | field `confidence_pct` of the same output | Same. |
| `hs_code_check` | `961700` | field `hs_code` of the output of `classifier-demo-2` | Same, for the second model. |
| `supporting_documents` | `3` | count of the invoice, the packing list and the data sheet | The three files are the ones cited, and there are three. |
| `customs_value_usd` | `18400` | extracted from the invoice, line "Total" | The invoice is the one cited. The reading itself is a claim. |
| `reviewer_approved` | `true` | reviewer R-07, at a stated time | Nothing: it is the signer's statement. |

The [policy](policy.yaml) declares these sources, so a record cannot take the confidence from another field or another model, or replace the reviewer's sign-off with a flag set by the pipeline.

## What it proves, and what it does not

A verified record proves that the holder of the signing key committed to exactly this record, that the decision follows from the rules and the inputs, that the rules are those of this policy file, and that the documents, the prompt and the model outputs are byte for byte the ones the decision used.

It does not prove that a model produced the output, that the reviewer really signed off, or when any of it happened: those are statements of whoever signed. It turns "trust our pipeline" into a short list of named statements by a named key, each of which can be checked against a fixed file or disputed on its own. [Section 2 of the specification](../../spec/DECISION_RECORD_v0.2.md#2-what-a-case-record-proves-and-what-it-does-not) has the full list.

The example is signed with the test key of RFC 8032, whose private half is printed in the RFC. Anyone can sign with it, which is why the verifier says "consistent, not authentic". A real record is signed with your own key, and the verifier is given your public key.

## Make your own

[`make_records.py`](make_records.py) is the whole integration in one short script: hash the material, say where each input came from, let the policy decide, sign.

```bash
uv run --with ./packages/attestrwa examples/ai-classification/make_records.py
```

With your own key:

```bash
attestrwa keygen --out signing.key          # prints the public key; the file is owner-only
attestrwa sign draft.json --key-file signing.key --out record.json
attestrwa verify record.json --policy policy.yaml --document-dir ./files --public-key 0x… --strict
```

`draft.json` is what `build_case_record` returns, with the public key from `keygen` as `public_key`. The signing key can also be given in the `ATTESTRWA_SIGNING_KEY` environment variable. `*.key` files are ignored by this repository's `.gitignore`.

## Files

| Path | What |
|---|---|
| [`policy.yaml`](policy.yaml) | The policy pack: six inputs with their sources, five rules. |
| [`case-approve/`](case-approve), [`case-reject/`](case-reject) | The material of each case: the line item being classified, the documents, the prompt, the two model outputs. |
| [`records/`](records) | The two signed records. They are also the format's [test vectors](../../spec/test-vectors). |
| [`make_records.py`](make_records.py) | Builds and signs both records, reproducibly. |
