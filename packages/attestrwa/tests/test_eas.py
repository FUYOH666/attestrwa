import pytest

from attestrwa.eas import (
    DECISION_SCHEMA,
    DecisionData,
    DecisionDataError,
    decode_decision,
    encode_decision,
    schema_uid,
)
from attestrwa.hashing import keccak256, to_hex

from .conftest import PAYEE, REPO_ROOT, TOKEN

EXPECTED_UID = "0x1a86145e70ac5055683604a56201574b2c9edf0512ad08fc1368a9e7cb565135"
SAMPLE = DecisionData(
    deal_id=b"\xd1" * 32,
    payee=PAYEE,
    token=TOKEN,
    amount=580_000_000,
    decision=1,
    policy_hash=b"\x22" * 32,
    record_hash=b"\x33" * 32,
)


def test_schema_string_is_the_one_published_in_the_spec() -> None:
    assert (REPO_ROOT / "spec" / "eas-schema.txt").read_text(encoding="utf-8") == DECISION_SCHEMA


def test_schema_uid_matches_the_registry_formula() -> None:
    assert to_hex(schema_uid()) == EXPECTED_UID
    assert schema_uid() == keccak256(DECISION_SCHEMA.encode() + b"\x00" * 20 + b"\x01")
    assert schema_uid(revocable=False) != schema_uid()


def test_decision_data_round_trips() -> None:
    encoded = encode_decision(SAMPLE)
    assert len(encoded) == 224
    assert decode_decision(encoded) == SAMPLE


def test_encoding_is_plain_abi_words() -> None:
    encoded = encode_decision(SAMPLE)
    assert encoded[:32] == SAMPLE.deal_id
    assert encoded[32:64] == b"\x00" * 12 + bytes.fromhex(PAYEE[2:])
    assert int.from_bytes(encoded[96:128], "big") == 580_000_000
    assert int.from_bytes(encoded[128:160], "big") == 1
    assert encoded[192:224] == SAMPLE.record_hash


@pytest.mark.parametrize("length", [0, 32, 223, 225, 320])
def test_wrong_length_data_is_rejected(length: int) -> None:
    with pytest.raises(DecisionDataError):
        decode_decision(b"\x00" * length)


def test_dirty_address_padding_is_rejected() -> None:
    encoded = bytearray(encode_decision(SAMPLE))
    encoded[32] = 0x01
    with pytest.raises(DecisionDataError):
        decode_decision(bytes(encoded))


def test_out_of_range_decision_is_rejected() -> None:
    encoded = bytearray(encode_decision(SAMPLE))
    encoded[128 + 30] = 0x01
    with pytest.raises(DecisionDataError):
        decode_decision(bytes(encoded))


def test_encode_rejects_bad_fields() -> None:
    with pytest.raises(DecisionDataError):
        encode_decision(DecisionData(b"\x01", PAYEE, TOKEN, 1, 1, b"\x02" * 32, b"\x03" * 32))
    with pytest.raises(DecisionDataError):
        encode_decision(
            DecisionData(b"\x01" * 32, PAYEE, TOKEN, 2**256, 1, b"\x02" * 32, b"\x03" * 32)
        )
