"""Decision records: structure, validation and construction.

A record file is an *envelope*::

    {
      "record": { ... },          # the hashed body
      "record_hash": "0x...",     # keccak256(canonical(record))
      ...                         # how it is anchored: an attestation or a signature
    }

Only ``record`` is hashed and therefore authoritative. Everything else in
the envelope is a convenience for readers; a verifier trusts the anchor, not
the envelope.

Two format versions are understood:

- **0.1** — one profile: an escrowed deal (``subject.kind`` ``escrow_deal``)
  anchored by an EAS attestation. ``spec/DECISION_RECORD_v0.1.md``.
- **0.2** — the 0.1 profile unchanged, plus a second one: a ``case`` (any
  decision about some material, for example an AI classification with a human
  sign-off) anchored by an Ed25519 signature, with ``document``, ``model`` and
  ``human`` sources. ``spec/DECISION_RECORD_v0.2.md``.
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
    DOCUMENT_READINGS,
    INPUT_TYPES,
    SOURCE_KINDS,
    SOURCE_KINDS_V01,
    SUBJECT_FIELDS,
    InputSpec,
    PolicyPack,
    Rule,
    Value,
    evaluate_all,
)
from attestrwa.rpc import calldata
from attestrwa.signing import SIGNATURE_SCHEME, is_usable_public_key

SPEC_V01 = "attestrwa.decision-record/0.1"
SPEC_V02 = "attestrwa.decision-record/0.2"
SPEC_IDS = (SPEC_V01, SPEC_V02)
# What the reference attester writes for an escrowed deal.
SPEC_ID = SPEC_V01

SUBJECT_ESCROW = "escrow_deal"
SUBJECT_CASE = "case"
SUBJECT_KIND = SUBJECT_ESCROW

ANCHOR_EAS = "eas"
ANCHOR_SIGNATURE = "signature"

# A case has no chain and no escrow state to read from, and no address for a
# registry lookup to be about.
CASE_SOURCE_KINDS = ("provider", "declared", "document", "model", "human")

MAX_DOCUMENT_ITEMS = 200

_ADDRESS_RE = re.compile(r"0x[0-9a-f]{40}")
# At most 78 digits: enough for any uint256, and far below the size at which
# converting a decimal string becomes expensive.
_DECIMAL_RE = re.compile(r"0|[1-9][0-9]{0,77}")
_SIGNED_DECIMAL_RE = re.compile(r"-?(0|[1-9][0-9]{0,77})")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# C0 and C1 control characters: never in text a person is meant to read.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")

_BODY_MEMBERS = (
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
)


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


def _text(value: Any, path: str, *, allow_empty: bool = False, limit: int | None = None) -> None:
    if not isinstance(value, str) or (not value and not allow_empty):
        _fail(path, "must be a non-empty string" if not allow_empty else "must be a string")
    if limit is not None:
        # Members introduced by format 0.2 are bounded and free of control characters.
        if len(value) > limit:
            _fail(path, f"must be at most {limit} characters")
        if _CONTROL_RE.search(value):
            _fail(path, "must not contain control characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _fail(path, "must be valid Unicode")


# ---- Sources ---------------------------------------------------------------


def _validate_source(source: Any, path: str, kinds: Sequence[str]) -> None:
    kind = source.get("kind") if isinstance(source, dict) else None
    if not isinstance(kind, str) or kind not in kinds:
        _fail(path, f"must be an object whose 'kind' is one of {', '.join(kinds)}")
    if kind == "subject":
        _obj(source, path, ("kind", "field"))
        if not isinstance(source["field"], str) or source["field"] not in SUBJECT_FIELDS:
            _fail(f"{path}.field", f"must be one of {', '.join(SUBJECT_FIELDS)}")
    elif kind == "onchain":
        _obj(source, path, ("kind", "chain_id", "to", "call", "data", "block_number", "result"))
        _uint(source["chain_id"], f"{path}.chain_id")
        _address(source["to"], f"{path}.to")
        _text(source["call"], f"{path}.call")
        if not is_hex(source["data"]) or not 10 <= len(source["data"]) <= 2 + 2 * 1024:
            _fail(
                f"{path}.data", "must be lowercase hex calldata (selector included, at most 1 KB)"
            )
        _uint(source["block_number"], f"{path}.block_number")
        if not is_hex(source["result"]) or len(source["result"]) > 2 + 2 * 1024:
            _fail(f"{path}.result", "must be lowercase hex (at most 1 KB)")
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
    elif kind == "document":
        _obj(source, path, ("kind", "reading", "items"))
        if not isinstance(source["reading"], str) or source["reading"] not in DOCUMENT_READINGS:
            _fail(f"{path}.reading", f"must be one of {', '.join(DOCUMENT_READINGS)}")
        items = source["items"]
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_DOCUMENT_ITEMS:
            _fail(f"{path}.items", f"must be an array of 1 to {MAX_DOCUMENT_ITEMS} documents")
        for index, entry in enumerate(items):
            entry_path = f"{path}.items[{index}]"
            _obj(entry, entry_path, ("ref", "sha256"), ("locator",))
            _text(entry["ref"], f"{entry_path}.ref", limit=500)
            _bytes32(entry["sha256"], f"{entry_path}.sha256")
            if "locator" in entry:
                _text(entry["locator"], f"{entry_path}.locator", limit=500)
        if source["reading"] == "extract" and len(items) != 1:
            _fail(f"{path}.items", "an extract is read from exactly one document")
    elif kind == "model":
        _obj(
            source,
            path,
            ("kind", "provider", "model", "prompt_sha256", "output_sha256"),
            ("field",),
        )
        _text(source["provider"], f"{path}.provider", limit=200)
        _text(source["model"], f"{path}.model", limit=200)
        _bytes32(source["prompt_sha256"], f"{path}.prompt_sha256")
        _bytes32(source["output_sha256"], f"{path}.output_sha256")
        if "field" in source:
            _text(source["field"], f"{path}.field", limit=200)
    elif kind == "human":
        _obj(source, path, ("kind", "by", "at"))
        _text(source["by"], f"{path}.by", limit=200)
        _uint(source["at"], f"{path}.at")
    else:  # declared
        _obj(source, path, ("kind", "by"))
        _text(source["by"], f"{path}.by")


def _validate_input(item: Any, path: str, kinds: Sequence[str] = SOURCE_KINDS) -> None:
    _obj(item, path, ("name", "type", "value", "source"))
    if not isinstance(item["name"], str) or not _NAME_RE.fullmatch(item["name"]):
        _fail(f"{path}.name", "must be an identifier")
    type_ = item["type"]
    value = item["value"]
    if not isinstance(type_, str) or type_ not in INPUT_TYPES:
        _fail(f"{path}.type", f"must be one of {', '.join(INPUT_TYPES)}")
    if type_ == "bool" and type(value) is not bool:
        _fail(f"{path}.value", "must be true or false for type bool")
    if type_ == "int" and not (isinstance(value, str) and _SIGNED_DECIMAL_RE.fullmatch(value)):
        _fail(f"{path}.value", "must be a decimal string for type int")
    if type_ == "string":
        _text(value, f"{path}.value", allow_empty=True)
    _validate_source(item["source"], f"{path}.source", kinds)


# ---- Record body -----------------------------------------------------------


def validate_record(body: Any) -> None:
    """Check the structure of a record body. Raises :class:`RecordError`.

    Never raises anything else: a record is untrusted input, and any shape the
    checks below do not expect is reported as a structural defect.
    """
    try:
        _validate_record(body)
    except RecordError:
        raise
    except (TypeError, KeyError, AttributeError, ValueError, RecursionError) as exc:
        raise RecordError(f"record: malformed ({type(exc).__name__})") from exc


def _validate_record(body: Any) -> None:
    _obj(body, "record", _BODY_MEMBERS)
    spec = body["spec"]
    if not isinstance(spec, str) or spec not in SPEC_IDS:
        _fail("record.spec", f"must be one of {', '.join(SPEC_IDS)}")
    if not is_hex(body["nonce"], 16):
        _fail("record.nonce", "must be 16 random bytes as lowercase 0x hex")
    if body["supersedes"] is not None:
        _bytes32(body["supersedes"], "record.supersedes")

    subject = body["subject"]
    kind = subject.get("kind") if isinstance(subject, dict) else None
    if spec == SPEC_V01:
        if kind != SUBJECT_ESCROW:
            _fail("record.subject.kind", f"must be {SUBJECT_ESCROW!r}")
        _validate_escrow_profile(body)
        _validate_common(body, SOURCE_KINDS_V01)
    elif kind == SUBJECT_ESCROW:
        _validate_escrow_profile(body)
        _validate_common(body, SOURCE_KINDS)
    elif kind == SUBJECT_CASE:
        _validate_case_profile(body)
        _validate_common(body, CASE_SOURCE_KINDS)
    else:
        _fail("record.subject.kind", f"must be {SUBJECT_ESCROW!r} or {SUBJECT_CASE!r}")


def _validate_escrow_profile(body: Mapping[str, Any]) -> None:
    """An escrowed deal, anchored by an EAS attestation (the only 0.1 profile)."""
    subject = _obj(body["subject"], "record.subject", ("kind", *SUBJECT_FIELDS))
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

    attester = _obj(body["attester"], "record.attester", ("address", "software"))
    _address(attester["address"], "record.attester.address")
    _text(attester["software"], "record.attester.software")

    anchor = _obj(body["anchor"], "record.anchor", ("kind", "chain_id", "eas", "schema_uid"))
    if anchor["kind"] != ANCHOR_EAS:
        _fail("record.anchor.kind", f"must be {ANCHOR_EAS!r} for an escrowed deal")
    if not (subject["deposited_at"] <= evaluation["evaluated_at"] < subject["deadline"]):
        _fail(
            "record.evaluation.evaluated_at",
            "must lie between the deposit and the deadline of the deal",
        )
    _uint(anchor["chain_id"], "record.anchor.chain_id")
    _address(anchor["eas"], "record.anchor.eas")
    _bytes32(anchor["schema_uid"], "record.anchor.schema_uid")
    if anchor["chain_id"] != subject["chain_id"]:
        _fail("record.anchor.chain_id", "must equal record.subject.chain_id")


def _validate_case_profile(body: Mapping[str, Any]) -> None:
    """A decision about some material, anchored by a signature (format 0.2)."""
    subject = _obj(body["subject"], "record.subject", ("kind", "id", "title", "digest"))
    _text(subject["id"], "record.subject.id", limit=200)
    _text(subject["title"], "record.subject.title", limit=500)
    _bytes32(subject["digest"], "record.subject.digest")

    evaluation = _obj(body["evaluation"], "record.evaluation", ("evaluated_at",))
    _uint(evaluation["evaluated_at"], "record.evaluation.evaluated_at")

    attester = _obj(body["attester"], "record.attester", ("public_key", "software"))
    _bytes32(attester["public_key"], "record.attester.public_key")
    if not is_usable_public_key(bytes.fromhex(attester["public_key"][2:])):
        _fail(
            "record.attester.public_key",
            "is not an Ed25519 public key that anyone could hold the private half of",
        )
    _text(attester["software"], "record.attester.software")

    anchor = _obj(body["anchor"], "record.anchor", ("kind", "scheme"))
    if anchor["kind"] != ANCHOR_SIGNATURE:
        _fail("record.anchor.kind", f"must be {ANCHOR_SIGNATURE!r} for a case")
    if anchor["scheme"] != SIGNATURE_SCHEME:
        _fail("record.anchor.scheme", f"must be {SIGNATURE_SCHEME!r}")


def _validate_common(body: Mapping[str, Any], kinds: Sequence[str]) -> None:
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
        _validate_input(item, f"record.inputs[{index}]", kinds)
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
    if not isinstance(decision["outcome"], str) or decision["outcome"] not in DECISION_CODES:
        _fail("record.decision.outcome", "must be 'approve' or 'reject'")
    if type(decision["code"]) is not int or decision["code"] != DECISION_CODES[decision["outcome"]]:
        _fail("record.decision.code", "must be 1 for approve and 2 for reject")
    if not isinstance(decision["failed_rules"], list) or not all(
        isinstance(item, str) for item in decision["failed_rules"]
    ):
        _fail("record.decision.failed_rules", "must be an array of rule ids")


def record_hash(body: Mapping[str, Any]) -> bytes:
    """``keccak256`` of the canonical bytes of a record body."""
    return keccak256(canonicalize(body))


def is_case(body: Mapping[str, Any]) -> bool:
    """True for a validated record of the ``case`` profile."""
    return body["subject"]["kind"] == SUBJECT_CASE


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
    must equal the subject field; ``onchain`` values must equal the decoded
    call result and must have been read on the deal's chain at the evaluation
    block; a ``document`` count must equal the number of documents it cites; a
    ``human`` sign-off in a case cannot be dated after the evaluation. The
    other sources need outside material.
    """
    problems: list[str] = []
    for item in body["inputs"]:
        source = item["source"]
        try:
            if source["kind"] == "subject":
                expected = expected_subject_value(body["subject"], source["field"], item["type"])
            elif source["kind"] == "onchain":
                # One snapshot: every chain read belongs to the evaluation block.
                if source["chain_id"] != body["subject"]["chain_id"]:
                    problems.append(
                        f"input {item['name']!r} was read from chain {source['chain_id']}, "
                        f"not the deal's chain {body['subject']['chain_id']}"
                    )
                if source["block_number"] != body["evaluation"]["block_number"]:
                    problems.append(
                        f"input {item['name']!r} was read at block {source['block_number']}, "
                        f"not the evaluation block {body['evaluation']['block_number']}"
                    )
                expected = expected_onchain_value(source["result"], item["type"])
            elif source["kind"] == "document" and source["reading"] == "count":
                if item["type"] != "int":
                    raise RecordError("a count of documents must have type int")
                hashes = [entry["sha256"] for entry in source["items"]]
                if len(set(hashes)) != len(hashes):
                    raise RecordError("the same document is counted more than once")
                expected = str(len(hashes))
            elif source["kind"] == "human" and is_case(body):
                if source["at"] > body["evaluation"]["evaluated_at"]:
                    problems.append(
                        f"input {item['name']!r}: the sign-off is dated after the evaluation "
                        "that used it"
                    )
                continue
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

    problems += input_coverage_problems(body["inputs"], pack)
    recorded = {item["name"]: item for item in body["inputs"]}
    for spec in pack.inputs:
        item = recorded.get(spec.name)
        if item is not None and item["source"]["kind"] == spec.source:
            problems += source_problems(item, spec, body["subject"])
    return problems


def expected_source(spec: InputSpec, subject: Mapping[str, Any]) -> dict[str, Any]:
    """The source members a policy declaration pins down for a given subject."""
    params = spec.params
    if spec.source == "subject":
        return {"field": params["field"]}
    if spec.source == "registry":
        return {"key": subject.get(params["of"])}
    if spec.source == "onchain":
        if "chain_id" not in subject:
            return {"to": None}
        expected: dict[str, Any] = {
            "chain_id": subject["chain_id"],
            "call": params["call"],
            "data": to_hex(calldata(params["call"], *(subject[arg] for arg in params["args"]))),
        }
        # None means the policy names no contract for this chain: nothing can match.
        expected["to"] = params["contracts"].get(str(subject["chain_id"]))
        return expected
    if spec.source == "provider":
        return {"name": params["name"]}
    if spec.source == "document":
        return {"reading": params["reading"]}
    if spec.source == "model":
        return {key: params[key] for key in ("field", "model") if key in params}
    return {}


def source_problems(
    item: Mapping[str, Any], spec: InputSpec, subject: Mapping[str, Any]
) -> list[str]:
    """Where a recorded source is not the one the policy declares.

    Without this a record could apply the right rules to the wrong facts: a
    registry lookup of some other address, a sanctions call about another
    wallet or to another contract, an amount read from a different field, a
    confidence taken from another field of the model's output.
    """
    problems: list[str] = []
    for member, wanted in expected_source(spec, subject).items():
        actual = item["source"].get(member)
        if wanted is None:
            problems.append(
                f"input {spec.name!r}: the policy cannot name its {spec.source} source "
                "for this subject"
            )
        elif actual != wanted:
            problems.append(
                f"input {spec.name!r}: source {member} is {actual!r}, "
                f"the policy requires {wanted!r}"
            )
    return problems


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


def cited_files(body: Mapping[str, Any]) -> dict[str, str]:
    """Every file a record commits to by hash: ``sha256 -> what it is``."""
    cited: dict[str, str] = {}
    if is_case(body):
        cited[body["subject"]["digest"]] = "the material the decision is about"
    for item in body["inputs"]:
        source = item["source"]
        if source["kind"] == "document":
            for entry in source["items"]:
                cited.setdefault(entry["sha256"], f"document {entry['ref']}")
        elif source["kind"] == "model":
            cited.setdefault(source["prompt_sha256"], f"prompt for input {item['name']}")
            cited.setdefault(source["output_sha256"], f"model output for input {item['name']}")
    return cited


# ---- Construction ----------------------------------------------------------


def _decide(
    pack: PolicyPack, inputs: Sequence[Mapping[str, Any]], kinds: Sequence[str]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Validate inputs against the pack, evaluate it, and return the record parts."""
    inputs = [dict(item) for item in inputs]
    for index, item in enumerate(inputs):
        _validate_input(item, f"inputs[{index}]", kinds)
    coverage = input_coverage_problems(inputs, pack)
    if coverage:
        raise RecordError("; ".join(coverage))
    outcome = evaluate_all(
        [Rule(id=rule.id, expression=rule.expression) for rule in pack.rules],
        context_from_inputs(inputs),
    )
    rules = [
        {"id": result.rule_id, "expression": result.expression, "result": result.passed}
        for result in outcome.rule_results
    ]
    decision = {
        "outcome": outcome.decision,
        "code": DECISION_CODES[outcome.decision],
        "failed_rules": outcome.failed_rules,
    }
    return inputs, decision, rules


def _policy_member(pack: PolicyPack, policy_uri: str) -> dict[str, Any]:
    return {
        "pack_id": pack.pack_id,
        "version": pack.version,
        "sha256": pack.sha256,
        "uri": policy_uri,
    }


def _finish(body: dict[str, Any], pack: PolicyPack) -> dict[str, Any]:
    validate_record(body)
    problems = pack_problems(body, pack) + input_problems(body)
    if problems:
        raise RecordError("; ".join(problems))
    return body


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
    """Evaluate ``pack`` over ``inputs`` and assemble a record for an escrowed deal.

    The decision is a pure function of the policy and the inputs: approve if
    and only if every rule holds. Raises :class:`RecordError` if the inputs do
    not satisfy the pack's declarations or do not follow from their sources.
    """
    inputs, decision, rules = _decide(pack, inputs, SOURCE_KINDS_V01)
    body: dict[str, Any] = {
        "spec": SPEC_V01,
        "nonce": nonce if nonce is not None else to_hex(secrets.token_bytes(16)),
        "supersedes": supersedes,
        "subject": {"kind": SUBJECT_ESCROW, **{name: subject[name] for name in SUBJECT_FIELDS}},
        "evaluation": {
            "block_number": evaluation["block_number"],
            "evaluated_at": evaluation["evaluated_at"],
        },
        "policy": _policy_member(pack, policy_uri),
        "inputs": inputs,
        "rules": rules,
        "decision": decision,
        "attester": {"address": attester_address, "software": software},
        "anchor": {
            "kind": ANCHOR_EAS,
            "chain_id": anchor["chain_id"],
            "eas": anchor["eas"],
            "schema_uid": anchor["schema_uid"],
        },
    }
    return _finish(body, pack)


def build_case_record(
    *,
    case_id: str,
    title: str,
    digest: str,
    evaluated_at: int,
    pack: PolicyPack,
    policy_uri: str,
    inputs: Sequence[Mapping[str, Any]],
    public_key: str,
    software: str,
    supersedes: str | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    """Evaluate ``pack`` over ``inputs`` and assemble a format 0.2 ``case`` record.

    ``digest`` is the sha256 of the material the decision is about, and
    ``public_key`` the Ed25519 key that will sign the record. The decision is
    the same pure function as for an escrowed deal.
    """
    inputs, decision, rules = _decide(pack, inputs, CASE_SOURCE_KINDS)
    body: dict[str, Any] = {
        "spec": SPEC_V02,
        "nonce": nonce if nonce is not None else to_hex(secrets.token_bytes(16)),
        "supersedes": supersedes,
        "subject": {"kind": SUBJECT_CASE, "id": case_id, "title": title, "digest": digest},
        "evaluation": {"evaluated_at": evaluated_at},
        "policy": _policy_member(pack, policy_uri),
        "inputs": inputs,
        "rules": rules,
        "decision": decision,
        "attester": {"public_key": public_key, "software": software},
        "anchor": {"kind": ANCHOR_SIGNATURE, "scheme": SIGNATURE_SCHEME},
    }
    return _finish(body, pack)


def make_envelope(
    body: Mapping[str, Any],
    *,
    network: str | None = None,
    attestation: Mapping[str, Any] | None = None,
    links: Mapping[str, str] | None = None,
    signature: str | None = None,
) -> dict[str, Any]:
    """Wrap a record body with its hash and the non-authoritative metadata.

    An escrowed deal's envelope names the network and the attestation; a
    case's envelope carries the signature over the record hash.
    """
    envelope: dict[str, Any] = {
        "record": dict(body),
        "record_hash": to_hex(record_hash(body)),
    }
    if body["anchor"]["kind"] == ANCHOR_SIGNATURE:
        envelope["signature"] = (
            {"scheme": SIGNATURE_SCHEME, "value": signature} if signature else None
        )
    else:
        envelope["network"] = network
        envelope["attestation"] = dict(attestation) if attestation else None
    envelope["links"] = dict(links) if links else {}
    return envelope
