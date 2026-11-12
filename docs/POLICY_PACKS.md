# Policy packs

A policy pack is a YAML file that says which inputs a decision needs, where each must come from, and which rules must hold. The SHA-256 of the file's exact bytes is the policy's identity: it is written into every record and into every attestation, so a change of one character is a different policy and "which version applied" has one answer.

The demo pack is [`data/policies/settlement-demo-v2.yaml`](../data/policies/settlement-demo-v2.yaml). It is synthetic and illustrative, not compliance advice.

## Structure

```yaml
pack_id: settlement-demo
version: "2.0.0"            # a string; quote it
description: free text

inputs:
  payee_registered:
    type: bool
    source: registry
    registry_id: demo-payees
    of: payee
  payee_sanctioned:
    type: bool
    source: onchain
    call: isSanctioned(address)
    args: [payee]
    contracts:
      "84532": "0x40c57923924b5c5c5455c48d93317139addac8fb"
  amount:
    type: int
    source: subject
    field: amount
  jurisdiction:
    type: string
    source: declared

rules:
  - id: payee-is-registered
    require: payee_registered == true
  - id: amount-within-limit
    require: amount <= 1000000000000
```

A settlement is approved if and only if every rule holds. All rules are evaluated and recorded, including those after a failure.

## Inputs

Types are `bool`, `int` and `string`. Each input names one source:

| `source` | Declaration | Where the attester gets the value | What a verifier can check |
|---|---|---|---|
| `subject` | `field`: one of `chain_id`, `escrow`, `deal_id`, `buyer`, `payee`, `token`, `amount`, `deadline`, `deposited_at` | The escrow's deal, read at the evaluation block. | The value equals that field. |
| `onchain` | `call`: a signature taking only addresses; `args`: subject address fields; `contracts`: chain id to contract address | `eth_call` at the evaluation block. | The call is the declared one, to the declared contract, about the declared party; replaying it returns the recorded word. |
| `registry` | `registry_id`; `of`: a subject address field | Membership of that address in the registry file. | With the registry file: its hash and the membership. |
| `provider` | `name` | An off-chain provider (none is implemented in the reference attester). | With the provider's response: its hash. |
| `declared` | nothing | The authenticated caller's request. | Nothing: it is recorded as declared, by whom. |

An `onchain` call returns one ABI word, read as `bool` or `int`.

Format 0.2 adds three sources, for decisions about documents and model outputs:

| `source` | Declaration | Where the value comes from | What a verifier can check |
|---|---|---|---|
| `document` | `reading`: `count` or `extract` | The number of documents cited by hash, or a value read out of exactly one of them. | With the files: each is byte for byte the one cited. A count equals the number of distinct documents. An extracted value is a claim about a fixed document. |
| `model` | `field` (optional), `model` (optional) | The output of a model, cited by the hashes of the prompt and of the output. | With the files: they are the ones cited, and the value is what the named top-level field of the output holds. That a model produced the file is not checked. |
| `human` | nothing | A named person, at a stated time. | Nothing: it is the signer's statement. |

A model output read by `field` is a JSON object, and the field holds a string, `true` or `false`, or an integer. There are no floats: a confidence is written as `93`, not `0.93`.

A record about a case (a decision with no escrow) may use `provider`, `declared`, `document`, `model` and `human`. It has no chain and no address, so a pack that declares a `subject`, `onchain` or `registry` input cannot be applied to it. [`examples/ai-classification/policy.yaml`](../examples/ai-classification/policy.yaml) is such a pack.

The attester refuses to supply an input from any other source, and the verifier refuses a record that did. That is why a caller cannot declare `buyer_sanctioned`, and why a record cannot quietly look up a different address.

## Rule language

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

- Names are declared inputs. `true` and `false` are the only other words.
- `and`, `or` and `not` take booleans. Both sides of `==` and `!=` must have the same type. `<`, `<=`, `>` and `>=` take integers. Comparisons do not chain.
- Integers have no size limit. There are no floats, no arithmetic, no functions.
- A type error or an unknown name is an error, never `false`.

The language is defined by this grammar, not by the implementation's host language. Expressions are checked token by token before they are parsed, so hexadecimal numbers, string escapes and the like are rejected even though Python would accept them.

Limits: 500 characters per expression, 200 rules and 256 KB per pack.

## Changing a policy

Edit the file and bump `version`. The hash changes with the bytes, so records made before and after are distinguishable on-chain by `policyHash`. [`settlement-demo-v2-strict.yaml`](../data/policies/settlement-demo-v2-strict.yaml) is such a revision: the same deal that the base pack approves is rejected under it, and both records prove which pack was applied.

A policy change does not invalidate decisions already attested. To withdraw one, the attester revokes its attestation; a new evaluation then produces a record that names the revoked one.

```bash
attestrwa policy-hash data/policies/settlement-demo-v2.yaml
```

## Payee registry

[`data/registry/payees.json`](../data/registry/payees.json):

```json
{
  "registry_id": "demo-payees",
  "version": "2026-11-12",
  "payees": [{"address": "0x…", "id": "…", "name": "…"}]
}
```

A record refers to a registry by the hash of the file's bytes. The demo registry lists accounts of the public development mnemonic under fictional names.
