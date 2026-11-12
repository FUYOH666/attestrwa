"""Decision Record v0.1: structure, validation and construction.

A record file is an *envelope*::

    {
      "record": { ... },          # the hashed body
      "record_hash": "0x...",     # keccak256(canonical(record))
      "network": "base-sepolia",  # informational
      "attestation": {"uid": "0x...", "tx_hash": "0x..."},
      "links": { ... }
    }

Only ``record`` is hashed and therefore authoritative. Everything else in
the envelope is a convenience for readers; a verifier trusts the chain, not
the envelope. The normative description is ``spec/DECISION_RECORD_v0.1.md``.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Mapping, Sequence
from typing import Any

from attestrwa.canonical import MAX_SAFE_INTEGER, canonicalize
from attestrwa.eas import DECISION_CODES
from attestrwa.hashing import is_hex, keccak256, to_hex
from attestrwa.policy import (
    INPUT_TYPES,
    SOURCE_KINDS,
    PolicyPack,
    Rule,
    Value,
    evaluate_all,
)

SPEC_ID = "attestrwa.decision-record/0.1"

SUBJECT_KIND = "escrow_deal"
SUBJECT_FIELDS = (
    "chain_id",
    "escrow",
    "deal_id",
    "buyer",
    "payee",
    "token",
    "amount",
    "deadline",
    "deposited_at",
)

_ADDRESS_RE = re.compile(r"0x[0-9a-f]{40}")
_DECIMAL_RE = re.compile(r"0|[1-9][0-9]*")
_SIGNED_DECIMAL_RE = re.compile(r"-?(0|[1-9][0-9]*)")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class RecordError(ValueError):
    """A decision record is structurally invalid."""


# ---- Small validators ------------------------------------------------------


def _fail(path: str, message: str) -> None:
    raise RecordError(f"{path}: {message}")


def _obj(value: Any, path: str, required: Sequence[str], optional: Sequence[str] = ()) -> dict:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    missing = [key for key in required if key not in value]
    if missing:
        _fail(path, f"missing field(s): {', '.join(missing)}")
    extra = [key for key in value if key not in required and key not in optional]
    if extra:
        _fail(path, f"unexpected field(s): {', '.join(sorted(extra))}")
    return value


def _address(value: Any, path: str) -> None:
    if not isinstance(value, str) or not _ADDRESS_RE.fullmatch(value):
        _fail(path, "must be a lowercase 0x-prefixed 20-byte address")


def _bytes32(value: Any, path: str) -> None:
    if not is_hex(value, 32):
        _fail(path, "must be lowercase 0x-prefixed 32-byte hex")


def _uint(value: Any, path: str) -> None:
    if type(value) is not int or value < 0 or value > MAX_SAFE_INTEGER:
        _fail(path, "must be a non-negative integer below 2**53")


def _text(value: Any, path: str, *, allow_empty: bool = False) -> None:
    if not isinstance(value, str) or (not value and not allow_empty):
        _fail(path, "must be a non-empty string" if not allow_empty else "must be a string")


# ---- Sources ---------------------------------------------------------------


def _validate_source(source: Any, path: str) -> None:
    if not isinstance(source, dict) or source.get("kind") not in SOURCE_KINDS:
        _fail(path, f"must be an object whose 'kind' is one of {', '.join(SOURCE_KINDS)}")
    kind = source["kind"]
    if kind == "subject":
        _obj(source, path, ("kind", "field"))
        if source["field"] not in SUBJECT_FIELDS:
            _fail(f"{path}.field", f"must be one of {', '.join(SUBJECT_FIELDS)}")
    elif kind == "onchain":
        _obj(source, path, ("kind", "chain_id", "to", "call", "data", "block_number", "result"))
        _uint(source["chain_id"], f"{path}.chain_id")
        _address(source["to"], f"{path}.to")
        _text(source["call"], f"{path}.call")
        if not is_hex(source["data"]) or len(source["data"]) < 10:
            _fail(f"{path}.data", "must be lowercase hex calldata (selector included)")
        _uint(source["block_number"], f"{path}.block_number")
        if not is_hex(source["result"]):
            _fail(f"{path}.result", "must be lowercase hex")
    elif kind == "registry":
        _obj(source, path, ("kind", "ref", "sha256", "key"))
        _text(source["ref"], f"{path}.ref")
        _bytes32(source["sha256"], f"{path}.sha256")
        _text(source["key"], f"{path}.key")
    elif kind == "provider":
        _obj(source, path, ("kind", "name", "response_sha256", "retrieved_at"))
        _text(source["name"], f"{path}.name")
        _bytes32(source["response_sha256"], f"{path}.response_sha256")
        _uint(source["retrieved_at"], f"{path}.retrieved_at")
    else:  # declared
        _obj(source, path, ("kind", "by"))
        _text(source["by"], f"{path}.by")


def _validate_input(item: Any, path: str) -> None:
    _obj(item, path, ("name", "type", "value", "source"))
    if not isinstance(item["name"], str) or not _NAME_RE.fullmatch(item["name"]):
        _fail(f"{path}.name", "must be an identifier")
    type_ = item["type"]
    value = item["value"]
    if type_ not in INPUT_TYPES:
        _fail(f"{path}.type", f"must be one of {', '.join(INPUT_TYPES)}")
    if type_ == "bool" and type(value) is not bool:
        _fail(f"{path}.value", "must be true or false for type bool")
    if type_ == "int" and not (isinstance(value, str) and _SIGNED_DECIMAL_RE.fullmatch(value)):
        _fail(f"{path}.value", "must be a decimal string for type int")
    if type_ == "string" and not isinstance(value, str):
        _fail(f"{path}.value", "must be a string for type string")
    _validate_source(item["source"], f"{path}.source")


# ---- Record body -----------------------------------------------------------


def validate_record(body: Any) -> None:
    """Check the structure of a record body. Raises :class:`RecordError`."""
    _obj(
        body,
        "record",
        (
            "spec",
            "nonce",
            "supersedes",
            "subject",
            "evaluation",
            "policy",
            "inputs",
            "rules",
            "decision",
            "attester",
            "anchor",
        ),
    )
    if body["spec"] != SPEC_ID:
        _fail("record.spec", f"must be {SPEC_ID!r}")
    if not is_hex(body["nonce"], 16):
        _fail("record.nonce", "must be 16 random bytes as lowercase 0x hex")
    if body["supersedes"] is not None:
        _bytes32(body["supersedes"], "record.supersedes")

    subject = _obj(body["subject"], "record.subject", ("kind", *SUBJECT_FIELDS))
    if subject["kind"] != SUBJECT_KIND:
        _fail("record.subject.kind", f"must be {SUBJECT_KIND!r}")
    _uint(subject["chain_id"], "record.subject.chain_id")
    _address(subject["escrow"], "record.subject.escrow")
    _bytes32(subject["deal_id"], "record.subject.deal_id")
    for name in ("buyer", "payee", "token"):
        _address(subject[name], f"record.subject.{name}")
    if not (isinstance(subject["amount"], str) and _DECIMAL_RE.fullmatch(subject["amount"])):
        _fail("record.subject.amount", "must be a decimal string")
    if int(subject["amount"]) >= 2**256:
        _fail("record.subject.amount", "must fit in uint256")
    _uint(subject["deadline"], "record.subject.deadline")
    _uint(subject["deposited_at"], "record.subject.deposited_at")

    evaluation = _obj(body["evaluation"], "record.evaluation", ("block_number", "evaluated_at"))
    _uint(evaluation["block_number"], "record.evaluation.block_number")
    _uint(evaluation["evaluated_at"], "record.evaluation.evaluated_at")

    policy = _obj(body["policy"], "record.policy", ("pack_id", "version", "sha256", "uri"))
    _text(policy["pack_id"], "record.policy.pack_id")
    _text(policy["version"], "record.policy.version")
    _bytes32(policy["sha256"], "record.policy.sha256")
    _text(policy["uri"], "record.policy.uri", allow_empty=True)

    inputs = body["inputs"]
    if not isinstance(inputs, list) or not inputs:
        _fail("record.inputs", "must be a non-empty array")
    seen_inputs: set[str] = set()
    for index, item in enumerate(inputs):
        _validate_input(item, f"record.inputs[{index}]")
        if item["name"] in seen_inputs:
            _fail(f"record.inputs[{index}].name", f"duplicate input {item['name']!r}")
        seen_inputs.add(item["name"])

    rules = body["rules"]
    if not isinstance(rules, list) or not rules:
        _fail("record.rules", "must be a non-empty array")
    seen_rules: set[str] = set()
    for index, rule in enumerate(rules):
        path = f"record.rules[{index}]"
        _obj(rule, path, ("id", "expression", "result"))
        _text(rule["id"], f"{path}.id")
        _text(rule["expression"], f"{path}.expression")
        if type(rule["result"]) is not bool:
            _fail(f"{path}.result", "must be true or false")
        if rule["id"] in seen_rules:
            _fail(f"{path}.id", f"duplicate rule {rule['id']!r}")
        seen_rules.add(rule["id"])

    decision = _obj(body["decision"], "record.decision", ("outcome", "code", "failed_rules"))
    if decision["outcome"] not in DECISION_CODES:
        _fail("record.decision.outcome", "must be 'approve' or 'reject'")
    if decision["code"] != DECISION_CODES[decision["outcome"]]:
        _fail("record.decision.code", "must be 1 for approve and 2 for reject")
    if not isinstance(decision["failed_rules"], list) or not all(
        isinstance(item, str) for item in decision["failed_rules"]
    ):
        _fail("record.decision.failed_rules", "must be an array of rule ids")

    attester = _obj(body["attester"], "record.attester", ("address", "software"))
    _address(attester["address"], "record.attester.address")
    _text(attester["software"], "record.attester.software")

    anchor = _obj(body["anchor"], "record.anchor", ("kind", "chain_id", "eas", "schema_uid"))
    if anchor["kind"] != "eas":
        _fail("record.anchor.kind", "must be 'eas'")
    _uint(anchor["chain_id"], "record.anchor.chain_id")
    _address(anchor["eas"], "record.anchor.eas")
    _bytes32(anchor["schema_uid"], "record.anchor.schema_uid")
    if anchor["chain_id"] != subject["chain_id"]:
        _fail("record.anchor.chain_id", "must equal record.subject.chain_id")


def record_hash(body: Mapping[str, Any]) -> bytes:
    """``keccak256`` of the canonical bytes of a record body."""
    return keccak256(canonicalize(body))


# ---- Inputs ----------------------------------------------------------------


def input_value(item: Mapping[str, Any]) -> Value:
    """The typed value of a recorded input, as the rule evaluator sees it."""
    if item["type"] == "int":
        return int(item["value"])
    return item["value"]


def context_from_inputs(inputs: Sequence[Mapping[str, Any]]) -> dict[str, Value]:
    return {item["name"]: input_value(item) for item in inputs}


def expected_subject_value(subject: Mapping[str, Any], field: str, type_: str) -> Any:
    """What a ``subject``-sourced input must hold for a given subject field."""
    raw = subject[field]
    if type_ == "int":
        return str(int(raw))
    if type_ == "string":
        return str(raw)
    raise RecordError(f"subject field {field!r} cannot be read as {type_}")


def expected_onchain_value(result_hex: str, type_: str) -> Any:
    """Decode a single ABI word returned by an ``eth_call`` into an input value."""
    raw = bytes.fromhex(result_hex[2:])
    if len(raw) != 32:
        raise RecordError("on-chain result must be exactly one 32-byte word")
    number = int.from_bytes(raw, "big")
    if type_ == "bool":
        if number not in (0, 1):
            raise RecordError("on-chain result is not an ABI bool")
        return number == 1
    if type_ == "int":
        return str(number)
    raise RecordError(f"on-chain result cannot be read as {type_}")


def input_problems(body: Mapping[str, Any]) -> list[str]:
    """Inputs whose recorded value does not follow from their recorded source.

    Only sources that are self-contained are checked here: ``subject`` values
    must equal the subject field, ``onchain`` values must equal the decoded
    call result. Registry, provider and declared inputs need outside material.
    """
    problems: list[str] = []
    for item in body["inputs"]:
        source = item["source"]
        try:
            if source["kind"] == "subject":
                expected = expected_subject_value(body["subject"], source["field"], item["type"])
            elif source["kind"] == "onchain":
                expected = expected_onchain_value(source["result"], item["type"])
            else:
                continue
        except RecordError as exc:
            problems.append(f"input {item['name']!r}: {exc}")
            continue
        if expected != item["value"]:
            problems.append(
                f"input {item['name']!r}: value {item['value']!r} does not match its "
                f"{source['kind']} source ({expected!r})"
            )
    return problems


def pack_problems(body: Mapping[str, Any], pack: PolicyPack) -> list[str]:
    """Differences between a record and the policy pack it claims to apply."""
    problems: list[str] = []
    policy = body["policy"]
    if policy["sha256"] != pack.sha256:
        problems.append(
            f"policy hash differs: record has {policy['sha256']}, file is {pack.sha256}"
        )
    if policy["pack_id"] != pack.pack_id or policy["version"] != pack.version:
        problems.append(
            f"policy identity differs: record has {policy['pack_id']}@{policy['version']}, "
            f"file is {pack.pack_id}@{pack.version}"
        )
    recorded_rules = [(rule["id"], rule["expression"]) for rule in body["rules"]]
    pack_rules = [(rule.id, rule.expression) for rule in pack.rules]
    if recorded_rules != pack_rules:
        problems.append("the record's rules are not the rules of the policy file")

    return problems + input_coverage_problems(body["inputs"], pack)


def input_coverage_problems(inputs: Sequence[Mapping[str, Any]], pack: PolicyPack) -> list[str]:
    """Inputs that are missing, undeclared, mistyped or from the wrong kind of source."""
    problems: list[str] = []
    recorded = {item["name"]: item for item in inputs}
    for spec in pack.inputs:
        item = recorded.get(spec.name)
        if item is None:
            problems.append(f"input {spec.name!r} is required by the policy but not recorded")
            continue
        if item["type"] != spec.type:
            problems.append(
                f"input {spec.name!r}: policy requires type {spec.type}, record has {item['type']}"
            )
        if item["source"]["kind"] != spec.source:
            problems.append(
                f"input {spec.name!r}: policy requires a {spec.source} source, "
                f"record has {item['source']['kind']}"
            )
    for name in recorded:
        if pack.input(name) is None:
            problems.append(f"input {name!r} is recorded but not declared by the policy")
    return problems


# ---- Construction ----------------------------------------------------------


def build_record(
    *,
    subject: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    pack: PolicyPack,
    policy_uri: str,
    inputs: Sequence[Mapping[str, Any]],
    attester_address: str,
    software: str,
    anchor: Mapping[str, Any],
    supersedes: str | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    """Evaluate ``pack`` over ``inputs`` and assemble a valid record body.

    The decision is a pure function of the policy and the inputs: approve if
    and only if every rule holds. Raises :class:`RecordError` if the inputs do
    not satisfy the pack's declarations or do not follow from their sources.
    """
    inputs = [dict(item) for item in inputs]
    for index, item in enumerate(inputs):
        _validate_input(item, f"inputs[{index}]")
    coverage = input_coverage_problems(inputs, pack)
    if coverage:
        raise RecordError("; ".join(coverage))
    outcome = evaluate_all(
        [Rule(id=rule.id, expression=rule.expression) for rule in pack.rules],
        context_from_inputs(inputs),
    )
    body: dict[str, Any] = {
        "spec": SPEC_ID,
        "nonce": nonce if nonce is not None else to_hex(secrets.token_bytes(16)),
        "supersedes": supersedes,
        "subject": {"kind": SUBJECT_KIND, **{name: subject[name] for name in SUBJECT_FIELDS}},
        "evaluation": {
            "block_number": evaluation["block_number"],
            "evaluated_at": evaluation["evaluated_at"],
        },
        "policy": {
            "pack_id": pack.pack_id,
            "version": pack.version,
            "sha256": pack.sha256,
            "uri": policy_uri,
        },
        "inputs": inputs,
        "rules": [
            {"id": result.rule_id, "expression": result.expression, "result": result.passed}
            for result in outcome.rule_results
        ],
        "decision": {
            "outcome": outcome.decision,
            "code": DECISION_CODES[outcome.decision],
            "failed_rules": outcome.failed_rules,
        },
        "attester": {"address": attester_address, "software": software},
        "anchor": {
            "kind": "eas",
            "chain_id": anchor["chain_id"],
            "eas": anchor["eas"],
            "schema_uid": anchor["schema_uid"],
        },
    }
    validate_record(body)
    problems = pack_problems(body, pack) + input_problems(body)
    if problems:
        raise RecordError("; ".join(problems))
    return body


def make_envelope(
    body: Mapping[str, Any],
    *,
    network: str,
    attestation: Mapping[str, Any] | None = None,
    links: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Wrap a record body with its hash and the non-authoritative metadata."""
    return {
        "record": dict(body),
        "record_hash": to_hex(record_hash(body)),
        "network": network,
        "attestation": dict(attestation) if attestation else None,
        "links": dict(links) if links else {},
    }
