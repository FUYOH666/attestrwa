"""Decision Record v0.2: the ``case`` profile and the new sources."""

import pytest

from attestrwa.record import (
    SPEC_V01,
    SPEC_V02,
    RecordError,
    build_case_record,
    cited_files,
    input_problems,
    is_case,
    make_envelope,
    pack_problems,
    record_hash,
    validate_record,
)

from .conftest import (
    CASE_EVALUATED_AT,
    CASE_FILES,
    CASE_PUBLIC_KEY,
    NONCE,
    case_files,
    clone,
    file_hash,
    make_case_body,
    make_case_inputs,
    sign_case,
)


def source_of(body: dict, name: str) -> dict:
    return next(item for item in body["inputs"] if item["name"] == name)["source"]


def test_a_case_record_is_built_validated_and_approved(case_body) -> None:
    validate_record(case_body)
    assert case_body["spec"] == SPEC_V02
    assert is_case(case_body)
    assert case_body["decision"] == {"outcome": "approve", "code": 1, "failed_rules": []}
    assert case_body["anchor"] == {"kind": "signature", "scheme": "ed25519"}
    assert case_body["attester"]["public_key"] == CASE_PUBLIC_KEY


def test_every_failed_rule_is_recorded(case_pack) -> None:
    body = make_case_body(case_pack, confidence=64, documents=("invoice.txt",), approved=False)
    assert body["decision"]["outcome"] == "reject"
    assert body["decision"]["failed_rules"] == ["confident", "two-documents", "signed-off"]
    assert [rule["result"] for rule in body["rules"]] == [False, False, True, False]


def test_the_hash_is_stable_and_depends_on_every_member(case_body) -> None:
    assert record_hash(case_body) == record_hash(clone(case_body))
    edited = clone(case_body)
    source_of(edited, "approved")["by"] = "reviewer:R-08"
    assert record_hash(edited) != record_hash(case_body)


def test_cited_files_are_the_subject_the_documents_the_prompt_and_the_output(case_body) -> None:
    files = case_files()
    assert set(cited_files(case_body)) == {file_hash(content) for content in files.values()}


def test_an_escrowed_deal_cites_no_files(approve_body) -> None:
    assert cited_files(approve_body) == {}


def test_a_signed_envelope_carries_the_signature_and_no_chain_members(case_body) -> None:
    envelope = sign_case(case_body)
    assert list(envelope) == ["record", "record_hash", "signature", "links"]
    assert envelope["signature"]["scheme"] == "ed25519"
    assert len(envelope["signature"]["value"]) == 2 + 128
    assert make_envelope(case_body)["signature"] is None


def test_an_escrow_envelope_is_unchanged(approve_body) -> None:
    assert list(make_envelope(approve_body)) == [
        "record",
        "record_hash",
        "network",
        "attestation",
        "links",
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b.__setitem__("spec", "attestrwa.decision-record/0.3"),
        lambda b: b["subject"].__setitem__("kind", "matter"),
        lambda b: b["subject"].pop("digest"),
        lambda b: b["subject"].__setitem__("digest", "0xabc"),
        lambda b: b["subject"].__setitem__("id", ""),
        lambda b: b["subject"].__setitem__("id", "x" * 201),
        lambda b: b["subject"].__setitem__("title", "line one\nline two"),
        lambda b: b["subject"].__setitem__("title", "bell \x07"),
        lambda b: b["subject"].__setitem__("title", "escape \x1b[31m"),
        lambda b: b["subject"].__setitem__("title", "x" * 501),
        lambda b: b["subject"].__setitem__("chain_id", 1),
        lambda b: b["evaluation"].__setitem__("block_number", 1),
        lambda b: b["evaluation"].__setitem__("evaluated_at", -1),
        lambda b: b["evaluation"].__setitem__("evaluated_at", "now"),
        lambda b: b["attester"].__setitem__("public_key", "0x" + "ab" * 20),
        lambda b: b["attester"].__setitem__("public_key", ("0x" + "ab" * 32).upper()),
        lambda b: b["attester"].__setitem__("address", "0x" + "ab" * 20),
        lambda b: b["attester"].pop("software"),
        lambda b: b["anchor"].__setitem__("kind", "eas"),
        lambda b: b["anchor"].__setitem__("scheme", "secp256k1"),
        lambda b: b["anchor"].__setitem__("chain_id", 1),
        lambda b: b.__setitem__("signature", "0x00"),
        lambda b: b.__setitem__("supersedes", "0x00"),
    ],
)
def test_structural_defects_of_a_case_are_rejected(case_body, mutation) -> None:
    body = clone(case_body)
    mutation(body)
    with pytest.raises(RecordError):
        validate_record(body)


@pytest.mark.parametrize(
    ("name", "mutation"),
    [
        ("documents", lambda s: s.__setitem__("items", [])),
        ("documents", lambda s: s.__setitem__("items", [s["items"][0]] * 201)),
        ("documents", lambda s: s.__setitem__("reading", "summary")),
        ("documents", lambda s: s["items"][0].__setitem__("sha256", "0x12")),
        ("documents", lambda s: s["items"][0].pop("ref")),
        ("documents", lambda s: s["items"][0].__setitem__("ref", "")),
        ("documents", lambda s: s["items"][0].__setitem__("ref", "a\tb")),
        ("documents", lambda s: s["items"][0].__setitem__("page", 2)),
        ("documents", lambda s: s["items"].__setitem__(0, "invoice.txt")),
        ("documents", lambda s: s.__setitem__("items", {"ref": "x"})),
        ("value", lambda s: s["items"].append(dict(s["items"][0]))),
        ("value", lambda s: s["items"][0].__setitem__("locator", "")),
        ("value", lambda s: s["items"][0].__setitem__("locator", 3)),
        ("label", lambda s: s.pop("output_sha256")),
        ("label", lambda s: s.pop("prompt_sha256")),
        ("label", lambda s: s.__setitem__("prompt_sha256", None)),
        ("label", lambda s: s.__setitem__("model", "")),
        ("label", lambda s: s.__setitem__("provider", 7)),
        ("label", lambda s: s.__setitem__("field", "")),
        ("label", lambda s: s.__setitem__("temperature", 0)),
        ("approved", lambda s: s.pop("at")),
        ("approved", lambda s: s.__setitem__("at", "yesterday")),
        ("approved", lambda s: s.__setitem__("at", 1.5)),
        ("approved", lambda s: s.__setitem__("by", "")),
        ("approved", lambda s: s.__setitem__("by", "x" * 201)),
        ("approved", lambda s: s.__setitem__("kind", "oracle")),
    ],
)
def test_malformed_sources_are_rejected(case_body, name, mutation) -> None:
    body = clone(case_body)
    mutation(source_of(body, name))
    with pytest.raises(RecordError):
        validate_record(body)


@pytest.mark.parametrize(
    "source",
    [
        {"kind": "subject", "field": "amount"},
        {
            "kind": "onchain",
            "chain_id": 1,
            "to": "0x" + "11" * 20,
            "call": "f()",
            "data": "0x12345678",
            "block_number": 1,
            "result": "0x" + "00" * 32,
        },
        {"kind": "registry", "ref": "r.json", "sha256": "0x" + "11" * 32, "key": "k"},
    ],
)
def test_a_case_has_no_chain_escrow_or_registry_to_read_from(case_body, source) -> None:
    body = clone(case_body)
    body["inputs"][0]["source"] = source
    with pytest.raises(RecordError, match="kind"):
        validate_record(body)


def test_format_0_1_keeps_its_own_source_vocabulary(approve_body) -> None:
    body = clone(approve_body)
    body["inputs"][-1]["source"] = {"kind": "human", "by": "reviewer", "at": 1}
    with pytest.raises(RecordError, match="kind"):
        validate_record(body)


def test_format_0_1_cannot_describe_a_case(case_body) -> None:
    body = clone(case_body)
    body["spec"] = SPEC_V01
    with pytest.raises(RecordError, match=r"subject\.kind"):
        validate_record(body)


def test_an_escrowed_deal_in_format_0_2_may_use_the_new_sources(approve_body) -> None:
    body = clone(approve_body)
    body["spec"] = SPEC_V02
    body["inputs"][-1]["source"] = {"kind": "human", "by": "compliance:officer-3", "at": 1}
    validate_record(body)
    assert not is_case(body)


def test_a_count_must_equal_the_number_of_documents_cited(case_body) -> None:
    body = clone(case_body)
    next(item for item in body["inputs"] if item["name"] == "documents")["value"] = "3"
    assert any("does not match its document source" in p for p in input_problems(body))


def test_the_same_document_cannot_be_counted_twice(case_body) -> None:
    body = clone(case_body)
    source = source_of(body, "documents")
    source["items"][1] = dict(source["items"][0], ref="the same bytes under another name")
    assert any("counted more than once" in problem for problem in input_problems(body))


def test_a_count_cannot_be_recorded_as_a_string(case_body) -> None:
    body = clone(case_body)
    next(item for item in body["inputs"] if item["name"] == "documents")["type"] = "string"
    assert any("must have type int" in problem for problem in input_problems(body))


def test_a_sign_off_cannot_be_dated_after_the_evaluation(case_body) -> None:
    body = clone(case_body)
    source_of(body, "approved")["at"] = CASE_EVALUATED_AT + 1
    assert any("after the evaluation" in problem for problem in input_problems(body))
    source_of(body, "approved")["at"] = CASE_EVALUATED_AT
    assert input_problems(body) == []


@pytest.mark.parametrize(
    ("name", "member", "value", "expected"),
    [
        ("confidence", "field", "score", "source field is 'score'"),
        ("confidence", "model", "model-b", "source model is 'model-b'"),
        ("documents", "reading", "extract", "source reading is 'extract'"),
        ("value", "reading", "count", "source reading is 'count'"),
    ],
)
def test_a_source_other_than_the_declared_one_fails_the_policy(
    case_body, case_pack, name, member, value, expected
) -> None:
    body = clone(case_body)
    source_of(body, name)[member] = value
    assert any(expected in problem for problem in pack_problems(body, case_pack))


def test_a_model_value_without_its_field_fails_the_policy(case_body, case_pack) -> None:
    body = clone(case_body)
    source_of(body, "confidence").pop("field")
    assert any("source field is None" in p for p in pack_problems(body, case_pack))


def test_a_human_sign_off_cannot_be_replaced_by_a_declaration(case_body, case_pack) -> None:
    body = clone(case_body)
    next(i for i in body["inputs"] if i["name"] == "approved")["source"] = {
        "kind": "declared",
        "by": "pipeline",
    }
    assert any("requires a human source" in p for p in pack_problems(body, case_pack))


def test_the_builder_refuses_inputs_that_do_not_fit_the_policy(case_pack) -> None:
    def build(inputs):
        return build_case_record(
            case_id="CASE-0002",
            title="t",
            digest=file_hash(CASE_FILES["subject.json"]),
            evaluated_at=CASE_EVALUATED_AT,
            pack=case_pack,
            policy_uri="",
            inputs=inputs,
            public_key=CASE_PUBLIC_KEY,
            software="tests",
            nonce=NONCE,
        )

    missing = make_case_inputs()[:-1]
    with pytest.raises(RecordError, match="required by the policy"):
        build(missing)

    miscounted = make_case_inputs()
    miscounted[2]["value"] = "5"
    with pytest.raises(RecordError, match="does not match its document source"):
        build(miscounted)

    wrong_field = make_case_inputs()
    wrong_field[1]["source"]["field"] = "score"
    with pytest.raises(RecordError, match="source field"):
        build(wrong_field)

    from_chain = make_case_inputs()
    from_chain[0]["source"] = {"kind": "subject", "field": "amount"}
    with pytest.raises(RecordError, match="kind"):
        build(from_chain)


def test_a_random_nonce_makes_two_records_of_the_same_case_differ(case_pack) -> None:
    def build():
        return build_case_record(
            case_id="CASE-0003",
            title="t",
            digest=file_hash(CASE_FILES["subject.json"]),
            evaluated_at=CASE_EVALUATED_AT,
            pack=case_pack,
            policy_uri="",
            inputs=make_case_inputs(),
            public_key=CASE_PUBLIC_KEY,
            software="tests",
        )

    assert record_hash(build()) != record_hash(build())


@pytest.mark.parametrize(
    "key",
    [
        "0x01" + "00" * 31,
        "0x" + "00" * 32,
        "0xecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
        "0x" + "ff" * 32,
    ],
)
def test_a_record_cannot_name_a_key_that_nobody_can_hold(case_body, key) -> None:
    body = clone(case_body)
    body["attester"]["public_key"] = key
    with pytest.raises(RecordError, match="public_key"):
        validate_record(body)


@pytest.mark.parametrize("code", [True, 1.0, "1", [1], None])
def test_the_decision_code_is_an_integer_in_both_formats(case_body, approve_body, code) -> None:
    for original in (case_body, approve_body):
        body = clone(original)
        body["decision"]["code"] = code
        with pytest.raises(RecordError, match="decision.code"):
            validate_record(body)
