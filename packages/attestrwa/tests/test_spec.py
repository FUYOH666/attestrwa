"""The published specification files agree with the implementation."""

import hashlib
import importlib.util
import json

import jsonschema
import pytest

from attestrwa.canonical import loads_strict
from attestrwa.hashing import to_hex
from attestrwa.policy import load_policy
from attestrwa.record import RecordError, record_hash, validate_record
from attestrwa.signing import RFC8032_TEST_PUBLIC_KEY
from attestrwa.verify import verify

from .conftest import (
    REPO_ROOT,
    case_files,
    clone,
    envelope_for,
    make_case_body,
    sign_case,
    supplied,
)

SPEC_DIR = REPO_ROOT / "spec"
SCHEMA = json.loads((SPEC_DIR / "decision-record-0.1.schema.json").read_text(encoding="utf-8"))
SCHEMA_V02 = json.loads((SPEC_DIR / "decision-record-0.2.schema.json").read_text(encoding="utf-8"))
VECTORS = SPEC_DIR / "test-vectors"
EXAMPLE = REPO_ROOT / "examples" / "ai-classification"


def test_json_schema_is_itself_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_built_records_satisfy_the_json_schema(approve_body, reject_body) -> None:
    for body in (approve_body, reject_body):
        jsonschema.validate(envelope_for(body), SCHEMA)


@pytest.mark.parametrize("name", ["record-approve.json", "record-reject.json"])
def test_published_record_vectors_verify(name: str, pack, registry) -> None:
    envelope = loads_strict((VECTORS / name).read_bytes())
    jsonschema.validate(envelope, SCHEMA)
    validate_record(envelope["record"])
    assert to_hex(record_hash(envelope["record"])) == envelope["record_hash"]
    report = verify(envelope, policy=pack, registry=registry)
    assert report.ok, [c for c in report.checks if c.status == "fail"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda e: e["record"].pop("policy"),
        lambda e: e["record"]["subject"].__setitem__("amount", 5),
        lambda e: e["record"]["inputs"][0]["source"].__setitem__("kind", "rumour"),
        lambda e: e["record"]["decision"].__setitem__("outcome", "maybe"),
        lambda e: e["record"]["subject"].__setitem__("escrow", "0xABC"),
        lambda e: e["record"].__setitem__("unexpected", True),
        lambda e: e.pop("record_hash"),
    ],
)
def test_schema_and_validator_reject_the_same_defects(approve_body, mutation) -> None:
    envelope = clone(envelope_for(approve_body))
    mutation(envelope)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(envelope, SCHEMA)
    if "record_hash" in envelope:
        with pytest.raises(RecordError):
            validate_record(envelope["record"])


# ---- Format 0.1 is frozen --------------------------------------------------

FROZEN_V01 = {
    "decision-record-0.1.schema.json": (
        "05a74b20e7307ee0faa4a5ac2b8420942c6b6f8af01dcd661bab78b59ab731c9"
    ),
    "test-vectors/canonical.json": (
        "fd2358a43d86060791bf10fad88b00b677dc73220ec7be4d6ca919160ad1c35d"
    ),
    "test-vectors/record-approve.json": (
        "087194de71c92947df222970b520d9936724b706088f08e5f2cacc67ca3cad0c"
    ),
    "test-vectors/record-reject.json": (
        "7a91790a54b442536952a98feffd1fc68c9d3b685ee37b17b7afe0a4be58fa7f"
    ),
}


@pytest.mark.parametrize("name", sorted(FROZEN_V01))
def test_the_published_0_1_files_have_not_changed_by_a_byte(name: str) -> None:
    """A change here is a change of a published format: it needs a new version."""
    assert hashlib.sha256((SPEC_DIR / name).read_bytes()).hexdigest() == FROZEN_V01[name]


# ---- Format 0.2 ------------------------------------------------------------


def test_json_schema_0_2_is_itself_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA_V02)


def test_built_case_records_satisfy_the_0_2_schema(case_pack) -> None:
    for body in (make_case_body(case_pack), make_case_body(case_pack, confidence=10)):
        jsonschema.validate(sign_case(body), SCHEMA_V02)
        jsonschema.validate({"record": body, "record_hash": to_hex(record_hash(body))}, SCHEMA_V02)


def test_an_escrowed_deal_restated_in_0_2_satisfies_the_0_2_schema(approve_body) -> None:
    body = clone(approve_body)
    body["spec"] = "attestrwa.decision-record/0.2"
    body["inputs"][-1]["source"] = {"kind": "human", "by": "compliance:officer-3", "at": 1}
    validate_record(body)
    jsonschema.validate(envelope_for(body), SCHEMA_V02)


def test_each_schema_accepts_only_its_own_version(approve_body, case_envelope) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(envelope_for(approve_body), SCHEMA_V02)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(case_envelope, SCHEMA)


@pytest.mark.parametrize("name", ["approve", "reject"])
def test_published_case_vectors_verify_with_their_material(name: str) -> None:
    raw = (VECTORS / f"case-{name}.json").read_bytes()
    envelope = loads_strict(raw)
    jsonschema.validate(envelope, SCHEMA_V02)
    assert to_hex(record_hash(envelope["record"])) == envelope["record_hash"]
    assert envelope["record"]["decision"]["outcome"] == name

    folder = EXAMPLE / f"case-{name}"
    documents = [(path.name, path.read_bytes()) for path in sorted(folder.iterdir())]
    report = verify(
        envelope,
        policy=load_policy(EXAMPLE / "policy.yaml"),
        documents=documents,
        public_key=to_hex(RFC8032_TEST_PUBLIC_KEY),
        strict=True,
    )
    assert report.ok and report.anchored, [c for c in report.checks if c.status != "pass"]
    assert len(report.checks) == 10
    # The vector is the example's record, byte for byte.
    assert raw == (EXAMPLE / "records" / f"{name}.json").read_bytes()


def test_the_case_vectors_are_reproducible_from_the_example() -> None:
    path = EXAMPLE / "make_records.py"
    spec = importlib.util.spec_from_file_location("ai_classification_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, envelope in module.build_all().items():
        assert module.dump(envelope).encode() == (VECTORS / f"case-{name}.json").read_bytes()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda e: e["record"].pop("policy"),
        lambda e: e["record"].__setitem__("unexpected", True),
        lambda e: e["record"]["subject"].__setitem__("kind", "matter"),
        lambda e: e["record"]["subject"].__setitem__("title", "two\nlines"),
        lambda e: e["record"]["subject"].__setitem__("id", "x" * 201),
        lambda e: e["record"]["subject"].__setitem__("digest", "0xABC"),
        lambda e: e["record"]["subject"].__setitem__("chain_id", 1),
        lambda e: e["record"]["evaluation"].__setitem__("block_number", 1),
        lambda e: e["record"]["attester"].__setitem__("address", "0x" + "ab" * 20),
        lambda e: e["record"]["attester"].__setitem__("public_key", "0x" + "ab" * 20),
        lambda e: e["record"]["anchor"].__setitem__("kind", "eas"),
        lambda e: e["record"]["anchor"].__setitem__("scheme", "rsa"),
        lambda e: e["record"]["decision"].__setitem__("code", 2),
        lambda e: e["record"]["inputs"][0]["source"].__setitem__("kind", "subject"),
        lambda e: e["record"]["inputs"][0]["source"].pop("output_sha256"),
        lambda e: e["record"]["inputs"][0]["source"].__setitem__("provider", ""),
        lambda e: e["record"]["inputs"][2]["source"].__setitem__("items", []),
        lambda e: e["record"]["inputs"][2]["source"].__setitem__("reading", "summary"),
        lambda e: e["record"]["inputs"][2]["source"]["items"][0].__setitem__("sha256", "0x1"),
        lambda e: e["record"]["inputs"][2]["source"]["items"][0].__setitem__("page", 1),
        lambda e: e["record"]["inputs"][3]["source"]["items"].append(
            dict(e["record"]["inputs"][3]["source"]["items"][0])
        ),
        lambda e: e["record"]["inputs"][4]["source"].pop("at"),
        lambda e: e["record"]["inputs"][4]["source"].__setitem__("at", -1),
        lambda e: e["record"]["inputs"][4]["source"].__setitem__("by", "a\tb"),
    ],
)
def test_the_0_2_schema_and_the_validator_reject_the_same_defects(case_body, mutation) -> None:
    envelope = clone(sign_case(case_body))
    mutation(envelope)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(envelope, SCHEMA_V02)
    with pytest.raises(RecordError):
        validate_record(envelope["record"])


@pytest.mark.parametrize(
    "signature",
    [
        "0x" + "00" * 64,
        {"scheme": "ed25519"},
        {"scheme": "rsa", "value": "0x" + "00" * 64},
        {"scheme": "ed25519", "value": "0x" + "00" * 63},
        {"scheme": "ed25519", "value": "0x" + "00" * 64, "by": "someone"},
    ],
)
def test_the_0_2_schema_and_the_verifier_reject_the_same_signature_members(
    case_envelope, signature
) -> None:
    envelope = clone(case_envelope)
    envelope["signature"] = signature
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(envelope, SCHEMA_V02)
    assert not verify(envelope, documents=supplied(case_files())).ok
