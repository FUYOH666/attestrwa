"""Verifying a signed case record (format 0.2): the record, its files, its signer."""

import pytest

from attestrwa.hashing import to_hex
from attestrwa.record import make_envelope, record_hash
from attestrwa.signing import RFC8032_TEST_PUBLIC_KEY, RFC8032_TEST_SEED, sign_hash
from attestrwa.verify import FAIL, PASS, SKIP, verify

from .conftest import (
    CASE_PUBLIC_KEY,
    OTHER_PUBLIC_KEY,
    OTHER_SEED,
    case_files,
    clone,
    file_hash,
    make_case_body,
    model_output,
    sign_case,
    supplied,
)

FULL_CHECKS = [
    "record.structure",
    "record.hash",
    "record.inputs",
    "record.replay",
    "record.decision",
    "policy.match",
    "documents.match",
    "model.output",
    "signature.valid",
    "signature.signer",
]


def statuses(report) -> dict[str, str]:
    return {check.id: check.status for check in report.checks}


def detail(report, check_id: str) -> str:
    return next(check.detail for check in report.checks if check.id == check_id)


def full(envelope, case_pack, **overrides):
    arguments = {
        "policy": case_pack,
        "documents": supplied(case_files()),
        "public_key": CASE_PUBLIC_KEY,
        "strict": True,
    }
    arguments.update(overrides)
    return verify(envelope, **arguments)


class Untouchable:
    """An RPC stand-in that fails the test if the verifier reaches for the chain."""

    def __getattr__(self, name):
        raise AssertionError(f"a case record must not touch the chain ({name})")


def test_a_signed_case_with_its_files_and_a_trusted_key_is_verified(case_envelope, case_pack):
    report = full(case_envelope, case_pack)
    assert [check.id for check in report.checks] == FULL_CHECKS
    assert all(check.status == PASS for check in report.checks)
    assert report.ok and report.anchored
    assert report.verdict == "VERIFIED"
    assert report.summary["case_id"] == "CASE-0001"
    assert report.summary["signer"] == CASE_PUBLIC_KEY
    assert report.summary["decision"] == "approve"
    assert "deal_id" not in report.summary


def test_a_rejection_is_verified_just_the_same(case_pack) -> None:
    body = make_case_body(case_pack, confidence=64, documents=("invoice.txt",), approved=False)
    files = case_files(confidence=64)
    del files["packing.txt"]  # this record does not cite it
    report = full(sign_case(body), case_pack, documents=supplied(files))
    assert report.ok and report.anchored
    assert "failed: confident, two-documents, signed-off" in detail(report, "record.decision")


def test_a_case_never_reaches_for_the_chain(case_envelope, case_pack) -> None:
    report = full(case_envelope, case_pack, rpc=Untouchable(), uid="0x" + "a7" * 32)
    assert report.ok
    assert not any(check.group == "On-chain" for check in report.checks)


def test_without_a_trusted_key_a_valid_signature_is_not_yet_proof(case_envelope, case_pack):
    report = full(case_envelope, case_pack, public_key=None, strict=False)
    assert statuses(report)["signature.valid"] == PASS
    assert statuses(report)["signature.signer"] == SKIP
    assert report.ok and not report.anchored
    assert report.verdict.startswith("CONSISTENT AND SIGNED")
    assert not full(case_envelope, case_pack, public_key=None).ok


def test_an_unsigned_record_is_only_consistent(case_body, case_pack) -> None:
    for document in (make_envelope(case_body), case_body):
        report = full(document, case_pack, strict=False)
        assert statuses(report)["signature.valid"] == SKIP
        assert report.ok and not report.anchored
        assert report.verdict == "CONSISTENT (unsigned)"
    assert not full(case_body, case_pack).ok


def test_a_key_other_than_the_trusted_one_fails(case_envelope, case_pack) -> None:
    report = full(case_envelope, case_pack, public_key=OTHER_PUBLIC_KEY)
    assert statuses(report)["signature.valid"] == PASS
    assert statuses(report)["signature.signer"] == FAIL
    assert not report.ok and report.verdict == "NOT VERIFIED"


def test_the_trusted_key_may_be_given_in_upper_case(case_envelope, case_pack) -> None:
    report = full(case_envelope, case_pack, public_key="0x" + CASE_PUBLIC_KEY[2:].upper())
    assert report.ok and report.anchored


def test_a_signature_made_with_another_key_is_invalid(case_body, case_pack) -> None:
    report = full(sign_case(case_body, seed=OTHER_SEED), case_pack)
    assert statuses(report)["signature.valid"] == FAIL
    assert not report.ok and not report.anchored


def test_a_forger_who_names_their_own_key_meets_the_trusted_key(case_body, case_pack) -> None:
    forged = clone(case_body)
    forged["attester"]["public_key"] = OTHER_PUBLIC_KEY
    forged["decision"] = {"outcome": "approve", "code": 1, "failed_rules": []}
    report = full(sign_case(forged, seed=OTHER_SEED), case_pack)
    assert statuses(report)["signature.valid"] == PASS
    assert statuses(report)["signature.signer"] == FAIL
    assert not report.ok


def test_editing_a_signed_record_breaks_the_hash(case_envelope, case_pack) -> None:
    tampered = clone(case_envelope)
    tampered["record"]["subject"]["title"] = "Classification of something else"
    report = full(tampered, case_pack)
    assert statuses(report)["record.hash"] == FAIL
    assert statuses(report)["signature.valid"] == FAIL
    assert not report.ok


def test_editing_a_signed_record_and_restating_its_hash_breaks_the_signature(
    case_envelope, case_pack
) -> None:
    tampered = clone(case_envelope)
    tampered["record"]["inputs"][4]["source"]["by"] = "reviewer:R-99"
    tampered["record_hash"] = to_hex(record_hash(tampered["record"]))
    report = full(tampered, case_pack)
    assert statuses(report)["record.hash"] == PASS
    assert statuses(report)["signature.valid"] == FAIL
    assert not report.ok


def test_a_flipped_decision_is_caught_before_the_signature_is_even_read(case_pack) -> None:
    body = make_case_body(case_pack, confidence=64)
    body["decision"] = {"outcome": "approve", "code": 1, "failed_rules": []}
    report = full(sign_case(body), case_pack, documents=supplied(case_files(confidence=64)))
    assert statuses(report)["record.decision"] == FAIL
    assert statuses(report)["signature.valid"] == PASS
    assert not report.ok


def test_a_raised_confidence_is_caught_by_the_model_output(case_pack) -> None:
    body = make_case_body(case_pack, confidence=64)
    confidence = next(item for item in body["inputs"] if item["name"] == "confidence")
    confidence["value"] = "96"
    body["rules"][0]["result"] = True
    body["decision"] = {"outcome": "approve", "code": 1, "failed_rules": []}
    report = full(sign_case(body), case_pack, documents=supplied(case_files(confidence=64)))
    assert statuses(report)["record.replay"] == PASS
    assert statuses(report)["documents.match"] == PASS
    assert statuses(report)["model.output"] == FAIL
    assert "confidence" in detail(report, "model.output")
    assert not report.ok


@pytest.mark.parametrize(
    "output",
    [
        b"not json at all",
        b"\xff\xfe\x00",
        b"[]",
        b'{"label": "961700"}',
        b'{"label": "961700", "confidence": "96"}',
        b'{"label": "961700", "confidence": 96.0}',
        b'{"label": "961700", "confidence": true}',
        b'{"label": 961700, "confidence": 96}',
        b'{"label": "961700", "confidence": 64, "confidence": 96}',
        b'{"label": "961700", "confidence": 96, "extra": {"a": 1, "a": 2}}',
        b'{"label": "961700", "confidence": 96, "extra": NaN}',
        b'{"label": "961700", "confidence": 96, "extra": [Infinity]}',
        b'{"label": "961700", "confidence": 96, "extra": -Infinity}',
        b'{"label": "961700", "confidence": 96, "extra": ' + b"1" * 5000 + b"}",
        b"[" * 100_000,
    ],
)
def test_a_model_output_that_does_not_hold_the_recorded_value_fails(case_pack, output) -> None:
    body = make_case_body(case_pack)
    for item in body["inputs"]:
        if item["source"]["kind"] == "model":
            item["source"]["output_sha256"] = file_hash(output)
    files = {**case_files(), "output.json": output}
    report = full(sign_case(body), case_pack, documents=supplied(files))
    assert statuses(report)["documents.match"] == PASS
    assert statuses(report)["model.output"] == FAIL
    assert not report.ok


def test_an_altered_document_is_caught(case_envelope, case_pack) -> None:
    files = case_files()
    files["invoice.txt"] = files["invoice.txt"].replace(b"18,400", b"8,400")
    report = full(case_envelope, case_pack, documents=supplied(files))
    assert statuses(report)["documents.match"] == FAIL
    assert "invoice.txt" in detail(report, "documents.match")
    assert not report.ok


def test_a_file_the_record_does_not_cite_is_refused(case_envelope, case_pack) -> None:
    files = {**case_files(), "another-case.txt": b"not part of this decision"}
    report = full(case_envelope, case_pack, documents=supplied(files))
    assert statuses(report)["documents.match"] == FAIL
    assert "another-case.txt" in detail(report, "documents.match")


def test_missing_files_are_named_and_skipped_not_passed(case_envelope, case_pack) -> None:
    files = case_files()
    del files["packing.txt"], files["output.json"]
    report = full(case_envelope, case_pack, documents=supplied(files), strict=False)
    assert statuses(report)["documents.match"] == SKIP
    assert "3 of 5" in detail(report, "documents.match")
    assert "document packing.txt" in detail(report, "documents.match")
    assert statuses(report)["model.output"] == SKIP
    assert report.ok and report.anchored
    assert not full(case_envelope, case_pack, documents=supplied(files)).ok


def test_without_files_the_document_checks_are_skipped(case_envelope, case_pack) -> None:
    for nothing in (None, []):
        report = full(case_envelope, case_pack, documents=nothing, strict=False)
        assert statuses(report)["documents.match"] == SKIP
        assert statuses(report)["model.output"] == SKIP
        assert report.ok


def test_a_wrong_policy_file_fails(case_envelope, pack) -> None:
    report = verify(case_envelope, policy=pack)
    assert statuses(report)["policy.match"] == FAIL


def test_a_model_other_than_the_declared_one_fails_the_policy(case_body, case_pack) -> None:
    body = clone(case_body)
    for item in body["inputs"]:
        if item["source"]["kind"] == "model":
            item["source"]["model"] = "model-b"
    report = full(sign_case(body), case_pack)
    assert statuses(report)["policy.match"] == FAIL
    assert "model-b" in detail(report, "policy.match")


def test_a_double_counted_document_fails(case_body, case_pack) -> None:
    body = clone(case_body)
    items = next(i for i in body["inputs"] if i["name"] == "documents")["source"]["items"]
    items[1] = dict(items[0], ref="copy-of-invoice.txt")
    report = full(sign_case(body), case_pack, strict=False)
    assert statuses(report)["record.inputs"] == FAIL


@pytest.mark.parametrize(
    "signature",
    [
        "0x" + "00" * 64,
        {"scheme": "ed25519"},
        {"scheme": "ed25519", "value": "0x1234"},
        {"scheme": "ed25519", "value": "0x" + "AB" * 64},
        {"scheme": "ed25519", "value": 5},
        {"scheme": "secp256k1", "value": "0x" + "00" * 64},
        {"value": "0x" + "00" * 64},
        ["ed25519", "0x" + "00" * 64],
        True,
        0,
    ],
)
def test_a_malformed_signature_member_fails_cleanly(case_envelope, signature) -> None:
    envelope = clone(case_envelope)
    envelope["signature"] = signature
    report = verify(envelope)
    assert not report.ok
    assert statuses(report) == {"record.structure": FAIL}


def test_a_well_formed_but_meaningless_signature_is_invalid(case_envelope) -> None:
    envelope = clone(case_envelope)
    envelope["signature"]["value"] = "0x" + "00" * 64
    report = verify(envelope)
    assert statuses(report)["signature.valid"] == FAIL
    assert not report.ok


@pytest.mark.parametrize(
    "public_key", ["", "0x", "0x1234", "not a key", "0x" + "zz" * 32, 5, b"\x00" * 32, ["0x00"]]
)
def test_a_malformed_trusted_key_fails_cleanly(case_envelope, public_key) -> None:
    report = verify(case_envelope, public_key=public_key)
    assert not report.ok
    assert statuses(report) == {"record.structure": FAIL}


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.__setitem__("subject", None),
        lambda r: r.__setitem__("subject", {"kind": "case"}),
        lambda r: r.__setitem__("subject", {"kind": ["case"]}),
        lambda r: r.__setitem__("attester", {"public_key": 1, "software": "x"}),
        lambda r: r.__setitem__("anchor", "signature"),
        lambda r: r.__setitem__("evaluation", []),
        lambda r: r["inputs"][2]["source"].__setitem__("items", [None]),
        lambda r: r["inputs"][2]["source"].__setitem__("items", [{"ref": {}, "sha256": []}]),
        lambda r: r["inputs"][0]["source"].__setitem__("output_sha256", {"a": 1}),
        lambda r: r["inputs"][4].__setitem__("source", {"kind": "human", "by": None, "at": None}),
        lambda r: r["inputs"].append(r["inputs"][0]),
        lambda r: r["subject"].__setitem__("title", "\ud800"),
    ],
)
def test_hostile_values_inside_a_case_fail_cleanly(case_envelope, mutation) -> None:
    envelope = clone(case_envelope)
    mutation(envelope["record"])
    report = verify(envelope, documents=supplied(case_files()), public_key=CASE_PUBLIC_KEY)
    assert not report.ok
    assert report.checks[0].id == "record.structure" and report.checks[0].status == FAIL


def test_a_record_signed_with_a_published_test_key_says_so(case_pack) -> None:
    body = make_case_body(case_pack)
    body["attester"]["public_key"] = to_hex(RFC8032_TEST_PUBLIC_KEY)
    envelope = make_envelope(
        body, signature=to_hex(sign_hash(RFC8032_TEST_SEED, record_hash(body)))
    )
    report = full(envelope, case_pack, public_key=to_hex(RFC8032_TEST_PUBLIC_KEY))
    assert report.ok and report.anchored
    assert report.summary["signer_is_published_test_key"] is True
    assert "published test key" in report.verdict
    assert "anyone can produce this signature" in detail(report, "signature.valid")


def test_an_ordinary_key_carries_no_such_caveat(case_envelope, case_pack) -> None:
    report = full(case_envelope, case_pack)
    assert report.summary["signer_is_published_test_key"] is False
    assert "test key" not in detail(report, "signature.valid")


def test_an_escrowed_deal_is_checked_exactly_as_before(approve_envelope, pack, registry) -> None:
    report = verify(approve_envelope, policy=pack, registry=registry)
    assert [check.id for check in report.checks] == [
        "record.structure",
        "record.hash",
        "record.inputs",
        "record.replay",
        "record.decision",
        "policy.match",
        "registry.match",
        "chain.network",
    ]
    assert detail(report, "record.structure") == "valid Decision Record v0.1"
    assert report.verdict == "CONSISTENT (not checked against the chain)"
    assert "signer" not in report.summary


def test_a_signature_on_an_escrowed_deal_is_not_an_anchor(approve_envelope, pack) -> None:
    envelope = clone(approve_envelope)
    envelope["signature"] = {"scheme": "ed25519", "value": "0x" + "00" * 64}
    report = verify(envelope, policy=pack, public_key=CASE_PUBLIC_KEY)
    assert not report.anchored
    assert "signature.valid" not in statuses(report)


def test_the_report_of_a_case_serialises(case_envelope, case_pack) -> None:
    data = full(case_envelope, case_pack).to_dict()
    assert data["ok"] is True and data["anchored"] is True
    assert data["counts"] == {"pass": 10, "fail": 0, "skip": 0}
    assert data["summary"]["title"] == "Classification of a vacuum bottle"


def test_changing_only_the_model_output_file_is_caught(case_envelope, case_pack) -> None:
    files = {**case_files(), "output.json": model_output(confidence=97)}
    report = full(case_envelope, case_pack, documents=supplied(files))
    assert statuses(report)["documents.match"] == FAIL


def test_a_file_named_for_a_record_that_cites_none_is_refused(approve_envelope, pack) -> None:
    report = verify(approve_envelope, policy=pack, documents=[("invoice.txt", b"anything")])
    assert statuses(report)["documents.match"] == FAIL
    assert "cites no files" in detail(report, "documents.match")
    assert not report.ok
    assert "documents.match" not in statuses(verify(approve_envelope, policy=pack, documents=[]))


def test_the_identity_key_forgery_is_refused(case_body, case_pack) -> None:
    """Found in review: with the identity as public key, one constant signature
    is valid for any record. It used to come out as VERIFIED when the caller
    was talked into trusting that key."""
    identity = "0x01" + "00" * 31
    forged = clone(case_body)
    forged["attester"]["public_key"] = identity
    envelope = make_envelope(forged, signature="0x01" + "00" * 63)
    report = full(envelope, case_pack, public_key=identity)
    assert not report.ok and not report.anchored
    assert statuses(report) == {"record.structure": FAIL}

    report = full(envelope, case_pack)
    assert not report.ok and report.checks[0].status == FAIL


@pytest.mark.parametrize("key", ["0x01" + "00" * 31, "0x" + "00" * 32, "0x" + "ff" * 32])
def test_a_trusted_key_that_nobody_can_hold_fails_cleanly(case_envelope, key) -> None:
    report = verify(case_envelope, public_key=key)
    assert not report.ok
    assert statuses(report) == {"record.structure": FAIL}


@pytest.mark.parametrize("signature", [{}, "junk", {"scheme": "rsa"}, 0, ["x"]])
def test_a_stray_signature_member_does_not_change_how_a_deal_is_checked(
    approve_envelope, pack, registry, signature
) -> None:
    plain = verify(approve_envelope, policy=pack, registry=registry)
    envelope = clone(approve_envelope)
    envelope["signature"] = signature
    report = verify(envelope, policy=pack, registry=registry)
    assert report.ok == plain.ok is True
    assert [(c.id, c.status, c.detail) for c in report.checks] == [
        (c.id, c.status, c.detail) for c in plain.checks
    ]
    assert report.verdict == plain.verdict
