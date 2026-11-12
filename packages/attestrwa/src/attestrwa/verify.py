"""Independent verification of a decision record.

The verifier answers one question: *does this record explain the decision
that was anchored, and does the decision follow from the record?*

It never trusts the envelope around a record. Offline it recomputes the hash
and replays the rules. Given the policy and registry files it confirms the
record applied exactly those bytes. Then it checks the anchor:

- an escrowed deal: given an RPC endpoint, it reads the EAS attestation and
  the escrow's own state and compares both with the record;
- a case (format 0.2): it checks the Ed25519 signature over the record hash,
  the signer against a key the caller trusts, and any supplied documents and
  model outputs against the hashes the record cites.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from attestrwa import rpc as chain
from attestrwa.canonical import CanonicalError
from attestrwa.eas import DECISION_CODES, DecisionDataError, decode_decision, schema_uid
from attestrwa.hashing import is_hex, sha256, to_hex
from attestrwa.policy import DSLError, PolicyPack, Rule, evaluate_rule, names_in
from attestrwa.record import (
    RecordError,
    cited_files,
    context_from_inputs,
    input_problems,
    is_case,
    pack_problems,
    record_hash,
    validate_record,
)
from attestrwa.registry import Registry
from attestrwa.signing import (
    PUBLISHED_TEST_KEYS,
    SIGNATURE_SCHEME,
    is_usable_public_key,
    verify_signature,
)

PASS = "pass"  # noqa: S105 - a status label, not a credential
FAIL = "fail"
SKIP = "skip"

GROUPS = ("Record", "Policy", "Registry", "Documents", "Signature", "On-chain")


@dataclass(slots=True, frozen=True)
class Check:
    id: str
    group: str
    status: str
    detail: str


@dataclass(slots=True)
class Report:
    """Result of verifying one record."""

    checks: list[Check] = field(default_factory=list)
    strict: bool = False
    record_hash: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)

    def add(self, check_id: str, group: str, status: str, detail: str) -> None:
        self.checks.append(Check(id=check_id, group=group, status=status, detail=detail))

    def count(self, status: str) -> int:
        return sum(1 for check in self.checks if check.status == status)

    @property
    def ok(self) -> bool:
        if self.count(FAIL):
            return False
        return not (self.strict and self.count(SKIP))

    def _status(self, check_id: str) -> str | None:
        for check in self.checks:
            if check.id == check_id:
                return check.status
        return None

    @property
    def anchored(self) -> bool:
        """True when the record was actually tied to its anchor.

        For an escrowed deal: its hash was compared with the on-chain
        attestation. For a case: the signature is valid *and* the signer is a
        key the caller said they trust.
        """
        if self._status("attestation.record_hash") == PASS:
            return True
        return self._status("signature.valid") == PASS and self._status("signature.signer") == PASS

    @property
    def verdict(self) -> str:
        if not self.ok:
            return "NOT VERIFIED"
        if self.anchored:
            if self.summary.get("signer_is_published_test_key"):
                return "VERIFIED (signed with a published test key: consistent, not authentic)"
            return "VERIFIED"
        signature = self._status("signature.valid")
        if signature == PASS:
            return "CONSISTENT AND SIGNED (signer not checked against a trusted key)"
        if signature == SKIP:
            return "CONSISTENT (unsigned)"
        return "CONSISTENT (not checked against the chain)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "anchored": self.anchored,
            "verdict": self.verdict,
            "strict": self.strict,
            "record_hash": self.record_hash,
            "summary": self.summary,
            "counts": {status: self.count(status) for status in (PASS, FAIL, SKIP)},
            "checks": [
                {"id": c.id, "group": c.group, "status": c.status, "detail": c.detail}
                for c in self.checks
            ],
        }


def _short(value: str) -> str:
    return value if len(value) <= 18 else f"{value[:10]}…{value[-6:]}"


# ---- Offline checks --------------------------------------------------------


def _check_replay(body: Mapping[str, Any], report: Report) -> None:
    try:
        context = context_from_inputs(body["inputs"])
        mismatches: list[str] = []
        for rule in body["rules"]:
            unknown = names_in(rule["expression"]) - context.keys()
            if unknown:
                mismatches.append(
                    f"rule {rule['id']!r} uses unrecorded input(s) {', '.join(sorted(unknown))}"
                )
                continue
            actual = evaluate_rule(Rule(id=rule["id"], expression=rule["expression"]), context)
            if actual != rule["result"]:
                mismatches.append(
                    f"rule {rule['id']!r} is recorded as {rule['result']} but evaluates to {actual}"
                )
    except DSLError as exc:
        report.add("record.replay", "Record", FAIL, f"rules cannot be replayed: {exc}")
        return
    if mismatches:
        report.add("record.replay", "Record", FAIL, "; ".join(mismatches))
        return
    report.add(
        "record.replay",
        "Record",
        PASS,
        f"{len(body['rules'])} rule(s) re-evaluated from the recorded inputs; all results match",
    )

    failed = [rule["id"] for rule in body["rules"] if not rule["result"]]
    outcome = "reject" if failed else "approve"
    decision = body["decision"]
    if decision["outcome"] != outcome or decision["failed_rules"] != failed:
        report.add(
            "record.decision",
            "Record",
            FAIL,
            f"the rules give {outcome} (failed: {failed or 'none'}) but the record says "
            f"{decision['outcome']} (failed: {decision['failed_rules'] or 'none'})",
        )
    else:
        report.add(
            "record.decision",
            "Record",
            PASS,
            f"decision {outcome.upper()} follows from the rules"
            + (f" (failed: {', '.join(failed)})" if failed else ""),
        )


def _check_policy(body: Mapping[str, Any], pack: PolicyPack | None, report: Report) -> None:
    if pack is None:
        report.add(
            "policy.match",
            "Policy",
            SKIP,
            "no policy file given (--policy); cannot confirm the rules are those of "
            f"{body['policy']['pack_id']}@{body['policy']['version']}",
        )
        return
    problems = pack_problems(body, pack)
    if problems:
        report.add("policy.match", "Policy", FAIL, "; ".join(problems))
    else:
        report.add(
            "policy.match",
            "Policy",
            PASS,
            f"policy file {pack.pack_id}@{pack.version} hashes to {_short(pack.sha256)}; "
            "rules, input types and input sources match the record",
        )


def _check_registry(
    body: Mapping[str, Any], registry: Registry | None, pack: PolicyPack | None, report: Report
) -> None:
    items = [item for item in body["inputs"] if item["source"]["kind"] == "registry"]
    if not items:
        return
    if registry is None:
        report.add(
            "registry.match",
            "Registry",
            SKIP,
            f"no registry file given (--registry); {len(items)} registry input(s) not re-checked",
        )
        return
    problems: list[str] = []
    if pack is not None:
        for spec in pack.inputs:
            wanted = spec.params.get("registry_id") if spec.source == "registry" else None
            if wanted is not None and wanted != registry.registry_id:
                problems.append(
                    f"input {spec.name!r}: the policy requires registry {wanted!r}, "
                    f"the file is {registry.registry_id!r}"
                )
    for item in items:
        source = item["source"]
        if source["sha256"] != registry.sha256:
            problems.append(
                f"input {item['name']!r} refers to registry {_short(source['sha256'])}, "
                f"the file is {_short(registry.sha256)}"
            )
            continue
        if item["type"] != "bool":
            problems.append(f"input {item['name']!r}: registry inputs must be bool")
            continue
        member = registry.contains(source["key"])
        if member != item["value"]:
            problems.append(
                f"input {item['name']!r} is recorded as {item['value']} but {source['key']} "
                f"is {'in' if member else 'not in'} the registry"
            )
    if problems:
        report.add("registry.match", "Registry", FAIL, "; ".join(problems))
    else:
        report.add(
            "registry.match",
            "Registry",
            PASS,
            f"registry {registry.registry_id}@{registry.version} hashes to "
            f"{_short(registry.sha256)}; {len(items)} membership claim(s) confirmed",
        )


# ---- Files and signature (format 0.2) --------------------------------------


def _unambiguous_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """A JSON object, refused when a member name repeats: readers would disagree."""
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate member name")
    return result


def _field_matches(output: Any, name: str, type_: str, value: Any) -> bool:
    """Does a model output's top-level field hold exactly the recorded value?"""
    if not isinstance(output, dict) or name not in output:
        return False
    actual = output[name]
    if type_ == "int":
        return type(actual) is int and actual == int(value)
    if type_ == "bool":
        return type(actual) is bool and actual == value
    return isinstance(actual, str) and actual == value


def _check_files(
    body: Mapping[str, Any], documents: Sequence[tuple[str, bytes]] | None, report: Report
) -> None:
    """Compare supplied files with the hashes the record cites.

    A supplied file that matches nothing the record cites is a failure: the
    caller expected it to be covered, and either it was altered or it is not
    part of this decision.
    """
    cited = cited_files(body)
    group = "Documents"
    if not cited:
        if documents:
            names = ", ".join(name for name, _ in documents)
            report.add(
                "documents.match", group, FAIL, f"{names}: this record cites no files at all"
            )
        return
    with_field = [
        item
        for item in body["inputs"]
        if item["source"]["kind"] == "model" and "field" in item["source"]
    ]
    if not documents:
        report.add(
            "documents.match",
            group,
            SKIP,
            f"none of the {len(cited)} cited file(s) was supplied (--document, --document-dir); "
            "not re-checked",
        )
        if with_field:
            report.add(
                "model.output",
                group,
                SKIP,
                f"{len(with_field)} value(s) read from model output not re-checked",
            )
        return

    supplied: dict[str, bytes] = {}
    stray: list[str] = []
    for name, content in documents:
        digest = to_hex(sha256(content))
        if digest in cited:
            supplied[digest] = content
        else:
            stray.append(name)
    missing = len(cited) - len(supplied)
    absent = [label for digest, label in cited.items() if digest not in supplied]
    if stray:
        report.add(
            "documents.match",
            group,
            FAIL,
            f"{', '.join(stray)}: not cited by this record, or altered since it was made",
        )
    elif missing:
        report.add(
            "documents.match",
            group,
            SKIP,
            f"{len(supplied)} of {len(cited)} cited file(s) supplied and matching; "
            f"not supplied: {'; '.join(absent[:5])}{' …' if missing > 5 else ''}",
        )
    else:
        report.add(
            "documents.match",
            group,
            PASS,
            f"all {len(cited)} cited file(s) supplied; every hash matches",
        )

    if not with_field:
        return
    problems: list[str] = []
    unavailable = 0
    for item in with_field:
        source = item["source"]
        content = supplied.get(source["output_sha256"])
        if content is None:
            unavailable += 1
            continue
        try:
            output = json.loads(content, object_pairs_hook=_unambiguous_object)
        except (ValueError, RecursionError):
            problems.append(
                f"input {item['name']!r}: the model output is not JSON, or repeats a member name"
            )
            continue
        if not _field_matches(output, source["field"], item["type"], item["value"]):
            problems.append(
                f"input {item['name']!r} is recorded as {item['value']!r}, which is not "
                f"what field {source['field']!r} of the model output holds"
            )
    if problems:
        report.add("model.output", group, FAIL, "; ".join(problems))
    elif unavailable:
        report.add(
            "model.output",
            group,
            SKIP,
            f"{unavailable} of {len(with_field)} value(s) not re-checked: "
            "the model output was not supplied",
        )
    else:
        report.add(
            "model.output",
            group,
            PASS,
            f"{len(with_field)} value(s) equal the named field of the model output",
        )


def _check_signature(
    body: Mapping[str, Any],
    computed: bytes,
    signature: str | None,
    trusted_key: str | None,
    report: Report,
) -> None:
    group = "Signature"
    signer = body["attester"]["public_key"]
    report.summary["signer"] = signer
    test_key = bytes.fromhex(signer[2:]) in PUBLISHED_TEST_KEYS
    report.summary["signer_is_published_test_key"] = test_key
    caveat = " (a published test key: anyone can produce this signature)" if test_key else ""
    if signature is None:
        report.add(
            "signature.valid", group, SKIP, "the file carries no signature (an unsigned draft)"
        )
    elif verify_signature(bytes.fromhex(signer[2:]), computed, bytes.fromhex(signature[2:])):
        report.add(
            "signature.valid", group, PASS, f"valid Ed25519 signature by {_short(signer)}{caveat}"
        )
    else:
        report.add(
            "signature.valid",
            group,
            FAIL,
            "the signature does not match this record and the key it names",
        )

    if trusted_key is None:
        report.add(
            "signature.signer",
            group,
            SKIP,
            "no trusted key given (--public-key): the record names its own signer, "
            "which says nothing about who holds that key",
        )
    elif trusted_key == signer:
        report.add("signature.signer", group, PASS, f"signed by the key you trust{caveat}")
    else:
        report.add(
            "signature.signer",
            group,
            FAIL,
            f"the record names signer {_short(signer)}, you trust {_short(trusted_key)}",
        )


# ---- On-chain checks -------------------------------------------------------


def _check_chain(
    body: Mapping[str, Any],
    computed_hash: bytes,
    rpc: Any,
    uid: str,
    recheck_inputs: bool,
    report: Report,
) -> None:
    subject = body["subject"]
    anchor = body["anchor"]
    group = "On-chain"

    actual_chain = rpc.chain_id()
    if actual_chain != subject["chain_id"]:
        report.add(
            "chain.network",
            group,
            FAIL,
            f"the RPC serves chain {actual_chain}, the record is about chain {subject['chain_id']}",
        )
        return
    report.add("chain.network", group, PASS, f"RPC serves chain {actual_chain}")

    expected_schema = to_hex(schema_uid())
    if anchor["schema_uid"] != expected_schema:
        report.add(
            "attestation.schema",
            group,
            FAIL,
            f"record anchors to schema {_short(anchor['schema_uid'])}, "
            f"SettlementDecision is {_short(expected_schema)}",
        )
        return

    attestation = chain.read_attestation(rpc, anchor["eas"], uid)
    if not attestation.exists:
        report.add("attestation.exists", group, FAIL, f"no attestation {_short(uid)} on this chain")
        return
    report.add(
        "attestation.exists",
        group,
        PASS,
        f"attestation {_short(uid)} found, made at {attestation.time}",
    )

    if to_hex(attestation.schema) != expected_schema:
        report.add(
            "attestation.schema",
            group,
            FAIL,
            f"attestation uses schema {_short(to_hex(attestation.schema))}",
        )
        return
    report.add("attestation.schema", group, PASS, "schema is SettlementDecision")

    try:
        data = decode_decision(attestation.data)
    except DecisionDataError as exc:
        report.add("attestation.data", group, FAIL, f"attestation data is malformed: {exc}")
        return

    if data.record_hash == computed_hash:
        report.add(
            "attestation.record_hash",
            group,
            PASS,
            "the attestation commits to exactly this record",
        )
    else:
        report.add(
            "attestation.record_hash",
            group,
            FAIL,
            f"the attestation commits to {_short(to_hex(data.record_hash))}, "
            f"this record hashes to {_short(to_hex(computed_hash))}",
        )

    if to_hex(data.policy_hash) == body["policy"]["sha256"]:
        report.add(
            "attestation.policy_hash", group, PASS, "on-chain policy hash matches the record"
        )
    else:
        report.add(
            "attestation.policy_hash",
            group,
            FAIL,
            f"on-chain policy hash is {_short(to_hex(data.policy_hash))}, "
            f"the record says {_short(body['policy']['sha256'])}",
        )

    deal_mismatch = [
        name
        for name, on_chain, recorded in (
            ("deal_id", to_hex(data.deal_id), subject["deal_id"]),
            ("payee", data.payee, subject["payee"]),
            ("token", data.token, subject["token"]),
            ("amount", str(data.amount), subject["amount"]),
        )
        if on_chain != recorded
    ]
    if deal_mismatch:
        report.add(
            "attestation.deal",
            group,
            FAIL,
            f"attestation and record disagree on: {', '.join(deal_mismatch)}",
        )
    else:
        report.add(
            "attestation.deal", group, PASS, "deal id, payee, token and amount match the record"
        )

    if data.decision == body["decision"]["code"]:
        report.add(
            "attestation.decision",
            group,
            PASS,
            f"on-chain decision is {body['decision']['outcome'].upper()}",
        )
    else:
        names = {code: name for name, code in DECISION_CODES.items()}
        report.add(
            "attestation.decision",
            group,
            FAIL,
            f"on-chain decision is {names.get(data.decision, data.decision)}, "
            f"the record says {body['decision']['outcome']}",
        )

    if attestation.recipient == subject["escrow"]:
        report.add("attestation.recipient", group, PASS, "attestation is addressed to this escrow")
    else:
        report.add(
            "attestation.recipient",
            group,
            FAIL,
            f"attestation is addressed to {attestation.recipient}, not the record's escrow",
        )

    if attestation.attester == body["attester"]["address"]:
        report.add("attestation.attester", group, PASS, f"attested by {attestation.attester}")
    else:
        report.add(
            "attestation.attester",
            group,
            FAIL,
            f"attested by {attestation.attester}, the record names {body['attester']['address']}",
        )

    if attestation.revocation_time:
        report.add(
            "attestation.not_revoked",
            group,
            FAIL,
            f"the attester revoked this decision at {attestation.revocation_time}",
        )
    else:
        report.add("attestation.not_revoked", group, PASS, "not revoked")

    evaluated_at = body["evaluation"]["evaluated_at"]
    if attestation.time < subject["deposited_at"]:
        report.add(
            "attestation.time",
            group,
            FAIL,
            f"attested at {attestation.time}, before the deposit at {subject['deposited_at']}",
        )
    elif attestation.time < evaluated_at:
        report.add(
            "attestation.time",
            group,
            FAIL,
            f"attested at {attestation.time}, before the evaluation it claims at {evaluated_at}",
        )
    else:
        report.add("attestation.time", group, PASS, "attested after the deposit and the evaluation")

    zero = "0x" + "00" * 32
    claimed = body["supersedes"] or zero
    referenced = to_hex(attestation.ref_uid)
    if referenced == claimed:
        report.add(
            "attestation.supersedes",
            group,
            PASS,
            "replaces no earlier decision"
            if claimed == zero
            else f"replaces {_short(claimed)}, as the attestation's refUID also says",
        )
    else:
        report.add(
            "attestation.supersedes",
            group,
            FAIL,
            f"the record says it replaces {_short(claimed)}, "
            f"the attestation references {_short(referenced)}",
        )

    block_number = body["evaluation"]["block_number"]
    try:
        _, block_time = rpc.block(block_number)
    except chain.RpcError:
        report.add(
            "evaluation.block",
            group,
            SKIP,
            f"the RPC no longer serves block {block_number}; its timestamp was not compared",
        )
    else:
        if block_time == evaluated_at:
            report.add(
                "evaluation.block",
                group,
                PASS,
                f"evaluation time is the timestamp of block {block_number}",
            )
        else:
            report.add(
                "evaluation.block",
                group,
                FAIL,
                f"block {block_number} has timestamp {block_time}, "
                f"the record says it was evaluated at {evaluated_at}",
            )

    escrow = subject["escrow"]
    escrow_eas = chain.read_escrow_eas(rpc, escrow)
    escrow_schema = to_hex(chain.read_escrow_schema_uid(rpc, escrow))
    if escrow_eas == anchor["eas"] and escrow_schema == anchor["schema_uid"]:
        report.add("escrow.config", group, PASS, "escrow reads the same EAS contract and schema")
    else:
        report.add(
            "escrow.config",
            group,
            FAIL,
            f"escrow is configured with EAS {escrow_eas} and schema {_short(escrow_schema)}",
        )

    deal = chain.read_deal(rpc, escrow, subject["deal_id"])
    if deal.status == 0:
        report.add("escrow.deal", group, FAIL, "the escrow has no such deal")
    else:
        differences = [
            name
            for name, on_chain, recorded in (
                ("buyer", deal.buyer, subject["buyer"]),
                ("payee", deal.payee, subject["payee"]),
                ("token", deal.token, subject["token"]),
                ("amount", str(deal.amount), subject["amount"]),
                ("deadline", deal.deadline, subject["deadline"]),
                ("deposited_at", deal.deposited_at, subject["deposited_at"]),
            )
            if on_chain != recorded
        ]
        if differences:
            report.add(
                "escrow.deal",
                group,
                FAIL,
                f"the escrow's deal differs from the record on: {', '.join(differences)}",
            )
        else:
            report.add(
                "escrow.deal",
                group,
                PASS,
                f"the escrow holds this exact deal (now {deal.status_name})",
            )
        report.summary["deal_status"] = deal.status_name

    if chain.read_attester_trusted(rpc, escrow, attestation.attester):
        report.add("escrow.attester_trusted", group, PASS, "the escrow trusts this attester")
    else:
        report.add(
            "escrow.attester_trusted",
            group,
            FAIL,
            "the escrow does not (or no longer) trust this attester",
        )

    onchain_inputs = [item for item in body["inputs"] if item["source"]["kind"] == "onchain"]
    if not onchain_inputs:
        return
    if not recheck_inputs:
        report.add(
            "inputs.onchain",
            group,
            SKIP,
            f"{len(onchain_inputs)} on-chain input(s) not re-queried (use --recheck-inputs)",
        )
        return
    problems: list[str] = []
    unavailable = 0
    for item in onchain_inputs:
        source = item["source"]
        if source["chain_id"] != actual_chain:
            problems.append(f"input {item['name']!r} was read from chain {source['chain_id']}")
            continue
        try:
            result = rpc.eth_call(
                source["to"], bytes.fromhex(source["data"][2:]), source["block_number"]
            )
        except chain.RpcError:
            unavailable += 1
            continue
        if to_hex(result) != source["result"]:
            problems.append(
                f"input {item['name']!r}: the call now returns {_short(to_hex(result))} at "
                f"block {source['block_number']}, the record has {_short(source['result'])}"
            )
    if problems:
        report.add("inputs.onchain", group, FAIL, "; ".join(problems))
    elif unavailable:
        report.add(
            "inputs.onchain",
            group,
            SKIP,
            f"{unavailable} of {len(onchain_inputs)} on-chain input(s) could not be re-queried: "
            "the RPC no longer serves state at the recorded block",
        )
    else:
        report.add(
            "inputs.onchain",
            group,
            PASS,
            f"{len(onchain_inputs)} on-chain input(s) re-queried at their recorded blocks; "
            "all results match",
        )


# ---- Entry point -----------------------------------------------------------


def verify(
    doc: Mapping[str, Any],
    *,
    rpc: Any | None = None,
    uid: str | None = None,
    policy: PolicyPack | None = None,
    registry: Registry | None = None,
    recheck_inputs: bool = False,
    strict: bool = False,
    documents: Sequence[tuple[str, bytes]] | None = None,
    public_key: str | None = None,
) -> Report:
    """Verify a record envelope (or a bare record body).

    ``rpc`` is any object with ``chain_id()``, ``block(number)`` and
    ``eth_call(to, data, block)``;
    pass ``None`` to verify offline. ``uid`` overrides the attestation UID named
    in the envelope. With ``strict`` a skipped check counts as a failure.

    For format 0.2: ``documents`` are ``(name, content)`` pairs to compare
    with the hashes the record cites, and ``public_key`` is the Ed25519 key
    the caller trusts to have signed a case.
    """
    report = Report(strict=strict)
    signature_value: str | None = None
    if isinstance(doc, Mapping) and "record" in doc:
        body = doc["record"]
        claimed_hash = doc.get("record_hash")
        attestation_member = doc.get("attestation")
        signature_member = doc.get("signature")
        envelope_uid = None
        if attestation_member is not None:
            envelope_uid = (
                attestation_member.get("uid") if isinstance(attestation_member, Mapping) else None
            )
            if not is_hex(envelope_uid, 32):
                report.add(
                    "record.structure",
                    "Record",
                    FAIL,
                    "attestation: must be null or an object whose 'uid' is 32-byte hex",
                )
                return report
        if claimed_hash is not None and not is_hex(claimed_hash, 32):
            report.add("record.structure", "Record", FAIL, "record_hash: must be 32-byte hex")
            return report
    else:
        body, claimed_hash, envelope_uid, signature_member = doc, None, None, None
    if uid is not None and not is_hex(uid, 32):
        report.add("record.structure", "Record", FAIL, "the given UID is not 32-byte hex")
        return report
    if public_key is not None:
        public_key = public_key.lower() if isinstance(public_key, str) else public_key
        if not is_hex(public_key, 32) or not is_usable_public_key(bytes.fromhex(public_key[2:])):
            report.add(
                "record.structure",
                "Record",
                FAIL,
                "the given public key is not an Ed25519 public key (32-byte hex)",
            )
            return report

    try:
        validate_record(body)
        computed = record_hash(body)
    except (RecordError, CanonicalError) as exc:
        report.add("record.structure", "Record", FAIL, str(exc))
        return report
    case = is_case(body)
    # The signature belongs to the case profile; around an escrowed deal the
    # member means nothing and is ignored, as any stray envelope member is.
    if case and signature_member is not None:
        well_formed = (
            isinstance(signature_member, Mapping)
            and signature_member.get("scheme") == SIGNATURE_SCHEME
            and is_hex(signature_member.get("value"), 64)
        )
        if not well_formed:
            report.add(
                "record.structure",
                "Record",
                FAIL,
                "signature: must be null or {scheme: ed25519, value: 64-byte hex}",
            )
            return report
        signature_value = signature_member["value"]
    version = body["spec"].rsplit("/", 1)[1]
    report.add("record.structure", "Record", PASS, f"valid Decision Record v{version}")

    report.record_hash = to_hex(computed)
    if claimed_hash is not None and claimed_hash != report.record_hash:
        report.add(
            "record.hash",
            "Record",
            FAIL,
            f"the file states hash {_short(str(claimed_hash))} but the record hashes to "
            f"{_short(report.record_hash)}",
        )
    else:
        report.add("record.hash", "Record", PASS, f"record hash {report.record_hash}")

    if case:
        report.summary.update({"case_id": body["subject"]["id"], "title": body["subject"]["title"]})
    else:
        report.summary.update(
            {
                "deal_id": body["subject"]["deal_id"],
                "chain_id": body["subject"]["chain_id"],
                "escrow": body["subject"]["escrow"],
            }
        )
    report.summary.update(
        {
            "decision": body["decision"]["outcome"],
            "policy": f"{body['policy']['pack_id']}@{body['policy']['version']}",
        }
    )

    problems = input_problems(body)
    if problems:
        report.add("record.inputs", "Record", FAIL, "; ".join(problems))
    else:
        report.add(
            "record.inputs",
            "Record",
            PASS,
            f"{len(body['inputs'])} input(s); "
            + (
                "counts of documents follow from the documents cited"
                if case
                else "subject and on-chain values follow from their sources"
            ),
        )

    _check_replay(body, report)
    _check_policy(body, policy, report)
    _check_registry(body, registry, policy, report)
    _check_files(body, documents, report)
    if case:
        _check_signature(body, computed, signature_value, public_key, report)
        return report

    attestation_uid = uid or envelope_uid
    if rpc is None:
        report.add("chain.network", "On-chain", SKIP, "offline: no RPC endpoint given (--rpc)")
        return report
    if not attestation_uid:
        report.add(
            "attestation.exists",
            "On-chain",
            FAIL,
            "no attestation UID in the file and none given (--uid)",
        )
        return report
    report.summary["attestation_uid"] = attestation_uid
    _check_chain(body, computed, rpc, attestation_uid, recheck_inputs, report)
    return report
