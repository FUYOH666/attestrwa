"""The published specification files agree with the implementation."""

import json

import jsonschema
import pytest

from attestrwa.canonical import loads_strict
from attestrwa.hashing import to_hex
from attestrwa.record import RecordError, record_hash, validate_record
from attestrwa.verify import verify

from .conftest import REPO_ROOT, clone, envelope_for

SPEC_DIR = REPO_ROOT / "spec"
SCHEMA = json.loads((SPEC_DIR / "decision-record-0.1.schema.json").read_text(encoding="utf-8"))
VECTORS = SPEC_DIR / "test-vectors"


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
