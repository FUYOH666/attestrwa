# Decision Record v0.2

Status: draft, implemented by `packages/attestrwa` 2.1.0. Identifier:
`attestrwa.decision-record/0.2`.

A decision record states why a decision was made: which policy version was
applied, which inputs were used and where each came from, which rules held,
and what the outcome was. Anyone who later receives the record can check that
it is the record its author committed to, and can re-run the rules to confirm
that the decision follows from it.

[Version 0.1](DECISION_RECORD_v0.1.md) describes one kind of decision: a
compliance decision about an escrowed stablecoin settlement, anchored on-chain
in an [EAS](https://attest.org) attestation. Version 0.2 keeps that profile
and adds a second one for decisions that have no chain and no escrow: a
*case*, anchored by a signature, whose inputs may come from documents, from
the output of an AI model and from a named person.

This document defines what 0.2 adds. Where it says "as in 0.1", the text of
0.1 applies unchanged. The key words MUST, MUST NOT, SHOULD and MAY are used
as in RFC 2119.

## 1. What changed since 0.1

- A second subject, `case`, anchored by an Ed25519 signature over the record
  hash instead of an EAS attestation (sections 3, 4.1 and 7).
- Three source kinds: `document`, `model` and `human` (section 4.2).
- An escrowed deal may be written as a 0.2 record and may then use the new
  sources. Nothing else about that profile changes.

Nothing in 0.1 changes. A 0.1 record keeps its bytes, its hash and its
meaning, and a 0.1 record MUST NOT use anything defined here. An
implementation of 0.2 MUST verify 0.1 records by the rules of 0.1.

## 2. What a case record proves, and what it does not

A verified case record proves that:

1. the holder of the signing key committed to exactly these bytes (given a
   valid signature and a verifier who knows whose key it is);
2. the stated decision is the result of applying the stated rules to the
   stated inputs;
3. the rules are those of a policy file with a known hash (when the verifier
   holds that file);
4. the documents, the prompt and the model output the record cites are,
   byte for byte, the files the verifier holds (when it holds them); a value
   the record says it read from a named field of the model output is what
   that field holds; a count of documents is the number of distinct
   documents cited.

It does not prove:

- **that a model produced the output.** The hash binds the record to a file,
  not the file to a model. Who ran which model is the signer's statement.
- **that an extracted value is what the document says.** The document is
  fixed by its hash; reading a number out of it is a claim a reviewer can
  now check against that exact document.
- **that the named person signed off.** A `human` source is the signer's
  statement that this person did. Co-signatures are not part of 0.2.
- **when the record was made.** A signature carries no time.
  `evaluation.evaluated_at` and `human.at` are the signer's statements.
- **that no later record replaces this one.** A single file cannot show
  that; see section 7.3.
- **who holds the key.** That is established outside the record.

The record makes the origin of every input explicit so that a reviewer can
decide how much weight to give it, and so that a dispute is about one named
fact instead of about what happened.

## 3. File layout

A record file is a JSON object, the *envelope*:

| Member | Required | Hashed | Meaning |
|---|---|---|---|
| `record` | yes | yes | The record body (section 4). |
| `record_hash` | yes | no | `0x`-prefixed keccak256 of the canonical bytes of `record`. |
| `signature` | no | no | For a case: `{"scheme": "ed25519", "value": "0x…"}` (64 bytes), or `null` for an unsigned draft. |
| `network`, `attestation` | no | no | For an escrowed deal, as in 0.1. |
| `links` | no | no | Where to find the policy, the documents and the like. |

Only `record` is authoritative. A verifier MUST recompute `record_hash` and
MUST NOT trust any other envelope member. The signature cannot be part of the
hashed body, because it is made over the hash.

A JSON Schema for the envelope is in
[`decision-record-0.2.schema.json`](decision-record-0.2.schema.json). The
schema is necessary, not sufficient: it cannot express the rules of sections
4.2 and 7.

## 4. Record body

The members are those of 0.1, all required, unknown members rejected:
`spec`, `nonce`, `supersedes`, `subject`, `evaluation`, `policy`, `inputs`,
`rules`, `decision`, `attester`, `anchor`. `spec` is
`attestrwa.decision-record/0.2`.

`subject.kind` selects the profile:

| Member | `escrow_deal` | `case` |
|---|---|---|
| `subject` | As in 0.1, section 3.1. | `kind`, `id`, `title`, `digest` (4.1). |
| `evaluation` | `block_number`, `evaluated_at`. | `evaluated_at` (Unix seconds) only. |
| `attester` | `address`, `software`. | `public_key` (32 bytes, hex), `software`. |
| `anchor` | `kind` `eas`, `chain_id`, `eas`, `schema_uid`. | `kind` `signature`, `scheme` `ed25519`. |
| `supersedes` | UID of the revoked attestation, or `null`. | Hash of the record this one replaces, or `null`. |
| Sources allowed | All eight kinds. | `provider`, `declared`, `document`, `model`, `human`. |

The two profiles do not mix: an escrowed deal is anchored by `eas`, a case by
`signature`. A case has no chain, no escrow state and no address to look up,
so it cannot use `subject`, `onchain` or `registry` sources.

Value conventions are those of 0.1. In addition, the text members introduced
here (`subject.id`, `subject.title`, and the text members of the `document`,
`model` and `human` sources) MUST NOT contain control characters (U+0000 to
U+001F, U+007F to U+009F) and are limited in length as stated below, counted
in Unicode code points.

### 4.1 Case subject

| Member | Type | Meaning |
|---|---|---|
| `kind` | string | `case`. |
| `id` | text, 1 to 200 | The producer's identifier of the case. |
| `title` | text, 1 to 500 | One line saying what was decided about. |
| `digest` | bytes32 | SHA-256 of the exact bytes of the material the decision is about. |

When the material is more than one file, `digest` is the hash of a manifest
of them; the manifest's format is the producer's choice.

### 4.2 Sources

The five source kinds of 0.1 are unchanged. Three are added:

| Kind | Members | A verifier can check |
|---|---|---|
| `document` | `reading` (`count` or `extract`), `items`: 1 to 200 of `{"ref", "sha256", "locator"?}` | Given the files: each is byte-identical to the one cited. For `count`: the value is the number of items. |
| `model` | `provider`, `model`, `prompt_sha256`, `output_sha256`, `field`? | Given the files: the prompt and the output are the ones cited. With `field`: the value is what that field of the output holds. |
| `human` | `by`, `at` (Unix seconds) | Nothing beyond consistency: the value was stated by `by` at `at`. |

Files are identified by the SHA-256 of their exact bytes, as policy files
are. `ref` (1 to 500) names a document for a reader: a file name, a document
number, a URI. `locator` (1 to 500, optional) says where in the document to
look. `provider`, `model`, `field` and `by` are 1 to 200.

**`document`, reading `count`.** The input MUST have type `int`, its value
MUST equal the number of `items`, and no two items may have the same
`sha256`: the same bytes under two names are one document.

**`document`, reading `extract`.** `items` MUST contain exactly one document:
the one the value was read from.

**`model`.** `prompt_sha256` is the hash of everything that was sent to the
model, `output_sha256` the hash of what it returned, each as one file whose
format is the producer's choice. When `field` is present, the output MUST be
a JSON object in which no member name repeats, at any depth, and the input's
value MUST equal its top-level member `field`:

| Input `type` | The member MUST be |
|---|---|
| `string` | a JSON string, equal to the value |
| `bool` | JSON `true` or `false`, equal to the value |
| `int` | a JSON number without fraction or exponent, equal to the value |

Integers are compared exactly. There are no floats in a record, so a
confidence of `0.93` cannot be an input; a model that is to feed a rule
reports it as `93` (per cent) or `9300` (basis points).

**`human`.** In a case, `at` MUST NOT be later than `evaluation.evaluated_at`:
a sign-off cannot postdate the evaluation that used it.

### 4.3 Decision

As in 0.1, section 3.3: `approve` if and only if every rule holds; every rule
is evaluated and recorded.

## 5. Canonical bytes and the record hash

As in 0.1, section 4: `record_hash = keccak256(canonical(record))`, with the
same restricted RFC 8785 canonicalisation. The record hash stays keccak256 in
both profiles so that any record can also be committed to on-chain.

Test vectors for 0.2: [`test-vectors/case-approve.json`](test-vectors/case-approve.json)
and [`test-vectors/case-reject.json`](test-vectors/case-reject.json). They are
the records of [`examples/ai-classification`](../examples/ai-classification),
where the policy and every file they cite can be found, and they are signed
with the test key of section 7.2. The 0.1 vectors are unchanged.

## 6. Policy packs and the rule language

As in 0.1, section 5. The rule language is unchanged. A pack may declare the
new sources:

| Source | Declaration | The record's source MUST have |
|---|---|---|
| `document` | `reading`: `count` or `extract` | the same `reading` |
| `model` | `field` (optional), `model` (optional) | the same `field` when the pack names one; the same `model` when the pack names one |
| `human` | nothing | nothing further |

```yaml
inputs:
  confidence_pct:       {type: int,  source: model, field: confidence_pct, model: classifier-demo-1}
  supporting_documents: {type: int,  source: document, reading: count}
  customs_value_usd:    {type: int,  source: document, reading: extract}
  reviewer_approved:    {type: bool, source: human}
rules:
  - id: model-is-confident
    require: confidence_pct >= 90
  - id: reviewer-signed-off
    require: reviewer_approved == true
```

As in 0.1, a record whose input has a different type, source kind or source
than the pack declares does not conform to that pack. Here that is what stops
a human sign-off being replaced by a declaration of the pipeline, and a
confidence being taken from another field or from another model.

A pack that declares a `subject`, `onchain` or `registry` input cannot be
applied to a case.

## 7. Signature anchor

### 7.1 Signature

A case record is signed with Ed25519 as defined in
[RFC 8032](https://www.rfc-editor.org/rfc/rfc8032) (pure Ed25519: no context,
no pre-hash). The signed message is 70 bytes:

```
"attestrwa.decision-record.signature/1" || 0x00 || record_hash
```

that is, the 37 ASCII bytes of the label, one zero byte, and the 32 bytes of
the record hash. The label separates this use of a key from any other: a
signature made here is not a valid signature of anything else, and the
reverse.

`attester.public_key` is the 32-byte public key, inside the hashed body. The
64-byte signature is the envelope's `signature.value`. Ed25519 is
deterministic: the same key and record always give the same signature.

The public key MUST be the canonical encoding of a point of prime order. A
verifier MUST reject a record that names any other value, and MUST reject
such a value as a trusted key. The identity and the other points of small
order have no private key, yet satisfy the verification equation: for the
identity, one constant signature is valid for every message.

### 7.2 Whose key it is

A valid signature by the key a record names proves only that the holder of
that key signed. A verifier MUST be told, from outside the record, which key
it trusts, and MUST report a record signed by any other key as not verified.
Without such a key it MUST report the signer as not checked, not as passed.

How a producer publishes its key (its website, a DNS record, a contract, an
attestation) is outside this version.

The private half of one key is public: the test key of RFC 8032, section 7.1,
TEST 1, public key
`0xd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a`. The
test vectors are signed with it. A record signed with it is authentic to
nobody, and a verifier SHOULD say so.

### 7.3 Replacing a record

A signature cannot be revoked. To replace a decision, the producer issues a
new record whose `supersedes` is the hash of the old one. Whether a record
has been replaced cannot be read from the record itself: a relying party
needs the producer's register of records, or a public log of record hashes.
Neither is defined in 0.2.

### 7.4 Time

A signature proves no time. A producer who needs to show that a record
existed by a certain moment MAY publish its hash where the time is recorded
by someone else, for example in an on-chain attestation. 0.2 does not define
such an anchor for cases.

## 8. On-chain anchor

For an escrowed deal, as in 0.1, section 6, with `recordHash` computed over
the 0.2 record.

## 9. Verification

As in 0.1, section 7: a record is untrusted input, parsed strictly; a
malformed record is reported as not verified; a check that cannot be
performed is reported as skipped, not as passed and not as failed.

For a 0.2 record a verifier MUST additionally perform, and report separately:

1. **Record.** The profile rules of section 4; a `count` equals the number of
   distinct documents cited; a sign-off in a case does not postdate the
   evaluation.
2. **Policy** (when the policy file is available). As in 0.1, with the
   declarations of section 6.
3. **Documents** (when files are supplied). Every supplied file has the
   SHA-256 of a file the record cites: the case material, a document, a
   prompt or a model output. A file the caller supplied that the record does
   not cite MUST be reported as a failure: either it was altered or it is not
   part of this decision. Cited files that were not supplied are reported as
   skipped. For every `model` source with a `field` whose output was
   supplied, the value equals that field (section 4.2).
4. **Signature** (case). The signature is valid for the record hash and
   `attester.public_key` (7.1); the key is the one the verifier trusts (7.2).
   An envelope without a signature is an unsigned draft: reported as skipped.

A case is verified only when the signature is valid and the signer is a key
the verifier trusts. A case never requires a chain.

Reference implementation:

```bash
attestrwa verify record.json --policy policy.yaml \
  --document-dir ./case-files --public-key 0x… --strict
```

`--document FILE` names a file the record must cite; `--document-dir DIR` is
searched for the cited files and other files in it are ignored. Exit code 0
verified, 1 not verified, 2 usage error. Without `--public-key` the result is
"consistent and signed", not "verified".

## 10. Versioning

As in 0.1, section 8. Records state their version, and each version is
verified by its own rules: 0.1 records remain valid and unchanged. The
reference attester for escrowed deals continues to write 0.1 records. 0.2 may
still change before 1.0.
