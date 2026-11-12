import pytest

from attestrwa.canonical import canonicalize
from attestrwa.hashing import keccak256, to_hex
from attestrwa.record import (
    SPEC_ID,
    RecordError,
    build_record,
    input_problems,
    make_envelope,
    pack_problems,
    record_hash,
    validate_record,
)

from .conftest import (
    BUYER,
    PAYEE,
    UNREGISTERED_PAYEE,
    clone,
    make_body,
    make_inputs,
)


def test_built_record_is_valid_and_approves(approve_body) -> None:
    validate_record(approve_body)
    assert approve_body["spec"] == SPEC_ID
    assert approve_body["decision"] == {"outcome": "approve", "code": 1, "failed_rules": []}
    assert [rule["result"] for rule in approve_body["rules"]] == [True] * 5
    assert approve_body["subject"]["kind"] == "escrow_deal"


def test_unregistered_payee_gives_a_reject_naming_the_rule(reject_body) -> None:
    assert reject_body["decision"] == {
        "outcome": "reject",
        "code": 2,
        "failed_rules": ["payee-is-registered"],
    }
    assert reject_body["subject"]["payee"] == UNREGISTERED_PAYEE


@pytest.mark.parametrize(
    ("overrides", "failed"),
    [
        ({"payee_sanctioned": True}, ["payee-not-sanctioned"]),
        ({"buyer_sanctioned": True}, ["buyer-not-sanctioned"]),
        ({"amount": "1000000000001"}, ["amount-within-limit"]),
        ({"jurisdiction": "US"}, ["supported-jurisdiction"]),
        (
            {"payee": UNREGISTERED_PAYEE, "jurisdiction": "US"},
            ["payee-is-registered", "supported-jurisdiction"],
        ),
    ],
)
def test_decision_is_a_pure_function_of_policy_and_inputs(pack, registry, overrides, failed):
    body = make_body(pack, registry, **overrides)
    assert body["decision"]["outcome"] == "reject"
    assert body["decision"]["failed_rules"] == failed


def test_policy_revision_changes_the_decision_and_the_policy_hash(pack, strict_pack, registry):
    """Same deal, two policy versions: the record proves which one was applied."""
    amount = "600000000000"
    relaxed = make_body(pack, registry, amount=amount)
    subject = relaxed["subject"]
    strict = build_record(
        subject={key: subject[key] for key in subject if key != "kind"},
        evaluation=relaxed["evaluation"],
        pack=strict_pack,
        policy_uri="data/policies/settlement-demo-v2-strict.yaml",
        inputs=make_inputs(registry, amount=amount),
        attester_address=relaxed["attester"]["address"],
        software=relaxed["attester"]["software"],
        anchor=relaxed["anchor"],
        nonce=relaxed["nonce"],
    )
    assert relaxed["decision"]["outcome"] == "approve"
    assert strict["decision"]["outcome"] == "reject"
    assert strict["decision"]["failed_rules"] == ["amount-within-limit"]
    assert relaxed["policy"]["sha256"] != strict["policy"]["sha256"]
    assert record_hash(relaxed) != record_hash(strict)


def test_record_hash_is_keccak_of_the_canonical_bytes(approve_body) -> None:
    assert record_hash(approve_body) == keccak256(canonicalize(approve_body))
    envelope = make_envelope(approve_body, network="test")
    assert envelope["record_hash"] == to_hex(record_hash(approve_body))
    assert envelope["attestation"] is None and envelope["links"] == {}


def test_any_change_to_the_body_changes_the_hash(approve_body) -> None:
    original = record_hash(approve_body)
    for path in (
        ("subject", "amount"),
        ("policy", "version"),
        ("attester", "software"),
        ("nonce",),
    ):
        changed = clone(approve_body)
        target = changed
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = "0x" + "ff" * 16 if path == ("nonce",) else str(target[path[-1]]) + "1"
        assert record_hash(changed) != original, path


def test_nonce_is_random_when_not_supplied(pack, registry) -> None:
    first = make_body(pack, registry)
    subject = {key: first["subject"][key] for key in first["subject"] if key != "kind"}
    kwargs = dict(
        subject=subject,
        evaluation=first["evaluation"],
        pack=pack,
        policy_uri=first["policy"]["uri"],
        inputs=first["inputs"],
        attester_address=first["attester"]["address"],
        software=first["attester"]["software"],
        anchor=first["anchor"],
    )
    a, b = build_record(**kwargs), build_record(**kwargs)
    assert a["nonce"] != b["nonce"]
    assert record_hash(a) != record_hash(b)


def _mutate(body, mutation):
    changed = clone(body)
    mutation(changed)
    return changed


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b.pop("anchor"),
        lambda b: b.__setitem__("extra", 1),
        lambda b: b.__setitem__("spec", "attestrwa.decision-record/9.9"),
        lambda b: b.__setitem__("nonce", "0x00"),
        lambda b: b.__setitem__("supersedes", "0x1234"),
        lambda b: b["subject"].__setitem__("kind", "invoice"),
        lambda b: b["subject"].__setitem__("payee", PAYEE.upper().replace("0X", "0x")),
        lambda b: b["subject"].__setitem__("amount", 580000000),
        lambda b: b["subject"].__setitem__("amount", "0580"),
        lambda b: b["subject"].__setitem__("amount", str(2**256)),
        lambda b: b["subject"].__setitem__("deadline", "soon"),
        lambda b: b["subject"].__setitem__("deadline", True),
        lambda b: b["subject"].pop("buyer"),
        lambda b: b["evaluation"].__setitem__("block_number", -1),
        lambda b: b["policy"].__setitem__("sha256", "0xabc"),
        lambda b: b.__setitem__("inputs", []),
        lambda b: b["inputs"][0].__setitem__("type", "float"),
        lambda b: b["inputs"][0].__setitem__("value", "yes"),
        lambda b: b["inputs"][3].__setitem__("value", 580000000),
        lambda b: b["inputs"][0]["source"].__setitem__("kind", "rumour"),
        lambda b: b["inputs"][0]["source"].pop("sha256"),
        lambda b: b["inputs"][1]["source"].__setitem__("to", "0x1234"),
        lambda b: b["inputs"].append(clone(b["inputs"][0])),
        lambda b: b["rules"][0].__setitem__("result", "true"),
        lambda b: b["rules"].append(clone(b["rules"][0])),
        lambda b: b["decision"].__setitem__("outcome", "maybe"),
        lambda b: b["decision"].__setitem__("code", 2),
        lambda b: b["decision"].__setitem__("failed_rules", "none"),
        lambda b: b["attester"].__setitem__("address", "0x0"),
        lambda b: b["anchor"].__setitem__("kind", "ipfs"),
        lambda b: b["anchor"].__setitem__("chain_id", 1),
    ],
)
def test_structural_defects_are_rejected(approve_body, mutation) -> None:
    with pytest.raises(RecordError):
        validate_record(_mutate(approve_body, mutation))


def test_non_object_record_is_rejected() -> None:
    with pytest.raises(RecordError):
        validate_record(["not", "an", "object"])


def test_input_that_contradicts_its_subject_source_is_reported(approve_body) -> None:
    changed = clone(approve_body)
    changed["inputs"][3]["value"] = "1"
    assert any("amount" in problem for problem in input_problems(changed))


def test_input_that_contradicts_its_onchain_result_is_reported(approve_body) -> None:
    changed = clone(approve_body)
    changed["inputs"][1]["value"] = True
    assert any("payee_sanctioned" in problem for problem in input_problems(changed))


def test_onchain_result_must_be_one_abi_word(approve_body) -> None:
    changed = clone(approve_body)
    changed["inputs"][1]["source"]["result"] = "0x01"
    assert input_problems(changed)
    changed["inputs"][1]["source"]["result"] = "0x" + "00" * 31 + "02"
    assert input_problems(changed)


def test_build_refuses_an_input_from_the_wrong_kind_of_source(pack, registry) -> None:
    """A value the policy requires from chain cannot be supplied as a declaration."""
    inputs = make_inputs(registry)
    inputs[2] = {
        "name": "buyer_sanctioned",
        "type": "bool",
        "value": False,
        "source": {"kind": "declared", "by": "buyer"},
    }
    body = make_body(pack, registry)
    subject = {key: body["subject"][key] for key in body["subject"] if key != "kind"}
    with pytest.raises(RecordError, match="onchain source"):
        build_record(
            subject=subject,
            evaluation=body["evaluation"],
            pack=pack,
            policy_uri="",
            inputs=inputs,
            attester_address=body["attester"]["address"],
            software="x",
            anchor=body["anchor"],
        )


def test_build_refuses_missing_or_extra_inputs(pack, registry) -> None:
    body = make_body(pack, registry)
    subject = {key: body["subject"][key] for key in body["subject"] if key != "kind"}
    common = dict(
        subject=subject,
        evaluation=body["evaluation"],
        pack=pack,
        policy_uri="",
        attester_address=body["attester"]["address"],
        software="x",
        anchor=body["anchor"],
    )
    extra = make_inputs(registry) + [
        {
            "name": "buyer_kyc_tier",
            "type": "int",
            "value": "3",
            "source": {"kind": "declared", "by": BUYER},
        }
    ]
    with pytest.raises(RecordError, match="not declared by the policy"):
        build_record(inputs=extra, **common)
    with pytest.raises(RecordError, match="required by the policy but not recorded"):
        build_record(inputs=make_inputs(registry)[:-1], **common)


def test_pack_problems_detects_a_different_policy(approve_body, strict_pack) -> None:
    problems = pack_problems(approve_body, strict_pack)
    assert any("policy hash differs" in p for p in problems)
    assert any("rules" in p for p in problems)
