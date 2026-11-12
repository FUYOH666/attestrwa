# Decision Record v0.1

Status: draft, implemented by `packages/attestrwa` 2.0.0 and later. Identifier:
`attestrwa.decision-record/0.1`.

[Version 0.2](DECISION_RECORD_v0.2.md) adds signed records for decisions that
have no escrow. It changes nothing here: 0.1 records stay valid as they are.

A decision record states why a compliance decision about one settlement was
made: which policy version was applied, which inputs were used and where each
came from, which rules held, and what the outcome was. Its hash is anchored
on-chain in an [EAS](https://attest.org) attestation, so anyone who later
receives the record can check that it is the record the attester committed to,
and can re-run the rules to confirm that the decision follows from it.

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119.

## 1. What a record proves, and what it does not

A verified record proves that:

1. the attester committed, at a known time, to exactly these bytes;
2. the stated decision is the result of applying the stated rules to the
   stated inputs;
3. the rules are those of a policy file with a known hash (when the verifier
   holds that file);
4. inputs sourced from the subject or from an on-chain call follow from that
   source, and on-chain inputs can be re-queried at the recorded block.

It does not prove that inputs from a registry, an off-chain provider or a
declaration were true. The record makes their origin explicit so that a
reviewer can decide how much weight to give them. Address-list screening, for
example, says nothing about a freshly created wallet.

## 2. File layout

A record file is a JSON object, the *envelope*:

| Member | Required | Hashed | Meaning |
|---|---|---|---|
| `record` | yes | yes | The record body (section 3). |
| `record_hash` | yes | no | `0x`-prefixed keccak256 of the canonical bytes of `record`. |
| `network` | no | no | Human-readable network label, for example `base-sepolia`. |
| `attestation` | no | no | `{"uid": "0x…", "tx_hash": "0x…"}` or `null`. |
| `links` | no | no | Explorer URLs and similar. |

Only `record` is authoritative. A verifier MUST recompute `record_hash` and
MUST NOT trust any other envelope member; the attestation UID cannot be part
of the hashed body because EAS derives it from data that contains the hash.

A JSON Schema for the envelope is in
[`decision-record-0.1.schema.json`](decision-record-0.1.schema.json).

## 3. Record body

All members are required. Unknown members MUST be rejected.

| Member | Type | Meaning |
|---|---|---|
| `spec` | string | `attestrwa.decision-record/0.1`. |
| `nonce` | hex, 16 bytes | Random. Prevents guessing a low-entropy record from its hash. |
| `supersedes` | bytes32 or `null` | UID of the revoked attestation this record replaces. |
| `subject` | object | What was decided about (3.1). |
| `evaluation` | object | `block_number` and `evaluated_at` (Unix seconds) of the evaluation. |
| `policy` | object | `pack_id`, `version`, `sha256` of the policy file bytes, `uri`. |
| `inputs` | array | Every value the rules used, with its source (3.2). |
| `rules` | array | `id`, `expression`, `result` for every rule, in policy order. |
| `decision` | object | `outcome` (`approve` or `reject`), `code` (1 or 2), `failed_rules`. |
| `attester` | object | `address` of the attester and `software` that produced the record. |
| `anchor` | object | `kind` (`eas`), `chain_id`, `eas` contract, `schema_uid`. |

Value conventions:

- Addresses and hashes are lowercase `0x`-prefixed hex. EIP-55 casing is not used.
- Integers that may exceed 2^53−1 (token amounts, `int` inputs) are decimal strings.
- Other integers are JSON numbers in the range 0 … 2^53−1.
- The hashed body contains no free prose.

### 3.1 Subject

`subject.kind` is `escrow_deal`. The remaining members are read from the
escrow contract by the attester, never taken from the caller:

`chain_id`, `escrow`, `deal_id`, `buyer`, `payee`, `token`, `amount`
(decimal string), `deadline`, `deposited_at` (Unix seconds).

`anchor.chain_id` MUST equal `subject.chain_id`.

### 3.2 Inputs

Each input is `{"name", "type", "value", "source"}`.

| `type` | `value` |
|---|---|
| `bool` | JSON `true` or `false` |
| `int` | decimal string, optional leading `-` |
| `string` | JSON string |

`source.kind` states where the value came from:

| Kind | Members | A verifier can check |
|---|---|---|
| `subject` | `field` | The value equals that subject field. |
| `onchain` | `chain_id`, `to`, `call`, `data`, `block_number`, `result` | The value equals the decoded `result`; `eth_call(to, data)` at `block_number` returns `result`. |
| `registry` | `ref`, `sha256`, `key` | Given the registry file: its hash, and whether `key` is a member. |
| `provider` | `name`, `response_sha256`, `retrieved_at` | Given the provider response: its hash. |
| `declared` | `by` | Nothing. The value was stated by `by`. |

For `onchain`, `result` MUST be exactly one 32-byte ABI word. A `bool` input
is `true` if the word is 1 and `false` if it is 0; any other word is invalid.
An `int` input is the word read as an unsigned integer. `data` is what is
replayed; `call` is the signature the policy declares.

One snapshot: every `onchain` input MUST have `chain_id` equal to
`subject.chain_id` and `block_number` equal to `evaluation.block_number`, and
`evaluation.evaluated_at` MUST be the timestamp of that block. It MUST lie
between `subject.deposited_at` (inclusive) and `subject.deadline` (exclusive).
A record cannot combine readings from different moments.

Decimal strings are at most 78 digits.

### 3.3 Decision

The decision MUST be a pure function of the policy and the inputs:

- `outcome` is `approve` if every rule's `result` is `true`, otherwise `reject`;
- `code` is 1 for `approve` and 2 for `reject`;
- `failed_rules` lists the `id` of every rule whose `result` is `false`, in order.

Every rule is evaluated; evaluation does not stop at the first failure.

## 4. Canonical bytes and the record hash

```
record_hash = keccak256( canonical(record) )
```

`canonical` is [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) (JCS)
restricted to values on which implementations cannot disagree:

- object keys MUST match `[a-z0-9_]+`;
- numbers MUST be integers in the range ±(2^53−1); floats MUST be rejected;
- strings MUST be valid Unicode (no unpaired surrogates).

Under these restrictions any conforming RFC 8785 library produces the same
bytes. A parser reading a record MUST reject duplicate object keys.

Test vectors: [`test-vectors/canonical.json`](test-vectors/canonical.json),
[`test-vectors/record-approve.json`](test-vectors/record-approve.json),
[`test-vectors/record-reject.json`](test-vectors/record-reject.json).

## 5. Policy packs and the rule language

A policy pack is a YAML file with `pack_id`, `version` (a string), `inputs`
and `rules`. `policy.sha256` is the SHA-256 of the file's exact bytes, so a
change of one character is a different policy.

```yaml
pack_id: settlement-demo
version: "2.0.0"
inputs:
  payee_registered: {type: bool, source: registry, registry_id: demo-payees, of: payee}
  payee_sanctioned:
    type: bool
    source: onchain
    call: isSanctioned(address)
    args: [payee]
    contracts: {"84532": "0x40c57923924b5c5c5455c48d93317139addac8fb"}
  amount:           {type: int,  source: subject, field: amount}
rules:
  - id: payee-is-registered
    require: payee_registered == true
  - id: amount-within-limit
    require: amount <= 1000000000000
```

`inputs` declares, for every name a rule may use, its type, the kind of
source it MUST come from, and what exactly that source is:

| Source | Declaration | The record's source MUST have |
|---|---|---|
| `subject` | `field` | the same `field` |
| `onchain` | `call` (a signature taking only addresses), `args` (subject address fields: `escrow`, `buyer`, `payee`, `token`), `contracts` (chain id → contract address) | `to` equal to the contract for the subject's chain, `data` equal to the selector of `call` followed by the named subject addresses, the same `call` |
| `registry` | `registry_id`, `of` (a subject address field) | `key` equal to that subject address; the registry file, when available, has that `registry_id` |
| `provider` | `name` | the same `name` |
| `declared` | nothing | nothing further |

A record whose input has a different type, source kind or source than the
pack declares does not conform to that pack. This is what stops a value the
policy expects from the chain being supplied as a declaration, and what stops
the right rules being applied to the wrong facts: a registry lookup of some
other address, a sanctions call about another wallet or to another contract.

Rule grammar:

```
expr       := or_expr
or_expr    := and_expr ("or" and_expr)*
and_expr   := not_expr ("and" not_expr)*
not_expr   := "not" not_expr | comparison
comparison := operand (("==" | "!=" | "<" | "<=" | ">" | ">=") operand)?
operand    := NAME | INT | STRING | "true" | "false" | "(" expr ")"

NAME   := [A-Za-z_][A-Za-z0-9_]*
INT    := "-"? ( "0" | [1-9][0-9]* )
STRING := '"' ( any character except '"', '\' and newline )* '"'
```

Tokens are separated by spaces or tabs. Nothing else is part of the
language: no hexadecimal, octal, binary, underscored or exponent numbers, no
single-quoted or prefixed strings, no escape sequences, no adjacent string
literals, no comments. An implementation MUST reject such input and MUST NOT
fall back to the syntax of its host language.

Semantics:

- `NAME` resolves to a recorded input; an unknown name is an error.
- `and`, `or` and `not` take booleans only. All operands are evaluated.
- `==` and `!=` require both sides to have the same type.
- `<`, `<=`, `>`, `>=` take integers only. Comparisons do not chain.
- `INT` is a decimal integer of any size, optionally negative. There are no
  floats, no arithmetic, no function calls and no attribute or index access.
- A rule MUST evaluate to a boolean. Any error makes the record unverifiable;
  it is never treated as `false`.

Limits: an expression is at most 500 characters, a pack at most 200 rules and
256 KB.

## 6. On-chain anchor

The record is anchored by an EAS attestation with the schema in
[`eas-schema.txt`](eas-schema.txt):

```
bytes32 dealId, address payee, address token, uint256 amount, uint8 decision, bytes32 policyHash, bytes32 recordHash
```

Schema UID (resolver zero, revocable):
`0x1a86145e70ac5055683604a56201574b2c9edf0512ad08fc1368a9e7cb565135`.

| Field | Value |
|---|---|
| `dealId`, `payee`, `token`, `amount` | The subject, as held by the escrow. |
| `decision` | 1 approve, 2 reject. |
| `policyHash` | `policy.sha256`. |
| `recordHash` | `record_hash`. |
| EAS `recipient` | The escrow contract. |
| EAS `expirationTime` | No later than the deal's deadline. |
| EAS `refUID` | `supersedes`, or zero when `supersedes` is `null`. |

At most one unrevoked decision SHOULD exist per deal. To re-evaluate, the
attester revokes the earlier attestation and issues a new record whose
`supersedes` names it.

Rejections are attested with the same schema. The attestation exposes only
the outcome; the reasons stay in the record, which the attester MAY keep
private and disclose to the parties and auditors entitled to it. Note that an
on-chain `reject` about a payee address is itself public information.

## 7. Verification

A record is untrusted input. A verifier MUST parse it strictly (duplicate
keys and floats are errors) and MUST report any malformed record as not
verified; it MUST NOT crash or guess.

A verifier MUST perform, and report separately:

1. **Record.** Structure; hash; inputs follow from `subject` and `onchain`
   sources and belong to one snapshot; every rule re-evaluates to its
   recorded result; the decision follows from the rule results.
2. **Policy** (when the policy file is available). File hash equals
   `policy.sha256`; the file's rules equal the record's; every input has the
   type, source kind and source the pack declares.
3. **Registry** (when the registry file is available). File hash and
   membership claims.
4. **On-chain** (when an RPC endpoint is available). The attestation exists,
   uses the schema above, is addressed to the escrow, was made by
   `attester.address`, is not revoked, was made no earlier than the deposit
   and the evaluation, has `refUID` equal to `supersedes`, and its
   `recordHash`, `policyHash`, deal fields and `decision` equal the record's.
   The escrow holds the same deal, reads the same EAS contract and schema,
   and trusts the attester. `evaluation.evaluated_at` equals the timestamp of
   block `evaluation.block_number`.

A check that cannot be performed (no policy file, no RPC, state no longer
served at the recorded block) MUST be reported as skipped, not as passed and
not as failed. On-chain checks SHOULD use state reads only: public endpoints
prune old receipts and logs but keep serving contract state.

Reference implementation: `attestrwa verify` (exit code 0 verified, 1 not
verified, 2 usage or RPC error).

## 8. Versioning

`spec` names the format version. A change that alters the canonical bytes of
an existing record, the meaning of a member, or the rule semantics requires a
new version identifier. v0.1 may still change before 1.0; records state their
version so that old records remain verifiable by the implementation that
understands them.
