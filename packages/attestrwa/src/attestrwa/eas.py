"""The on-chain anchor: the ``SettlementDecision`` EAS schema.

The attestation carries only what the escrow must enforce plus two hashes.
Everything else about a decision lives in the record, which the hashes commit to.
"""

from __future__ import annotations

from dataclasses import dataclass

from attestrwa.hashing import keccak256

# Must stay byte-identical to ``spec/eas-schema.txt``; a test enforces it.
DECISION_SCHEMA = (
    "bytes32 dealId, address payee, address token, uint256 amount, "
    "uint8 decision, bytes32 policyHash, bytes32 recordHash"
)

# Canonical EAS predeploy on OP-stack chains (Base, Base Sepolia, Optimism).
EAS_PREDEPLOY = "0x4200000000000000000000000000000000000021"
SCHEMA_REGISTRY_PREDEPLOY = "0x4200000000000000000000000000000000000020"

DECISION_APPROVE = 1
DECISION_REJECT = 2
DECISION_CODES = {"approve": DECISION_APPROVE, "reject": DECISION_REJECT}

_ENCODED_LENGTH = 7 * 32


class DecisionDataError(ValueError):
    """Attestation data does not have the ``SettlementDecision`` layout."""


def schema_uid(schema: str = DECISION_SCHEMA, *, revocable: bool = True) -> bytes:
    """UID the EAS SchemaRegistry assigns: keccak(schema ‖ resolver ‖ revocable)."""
    resolver = b"\x00" * 20
    return keccak256(schema.encode("utf-8") + resolver + (b"\x01" if revocable else b"\x00"))


@dataclass(slots=True, frozen=True)
class DecisionData:
    """Decoded ``SettlementDecision`` attestation data."""

    deal_id: bytes
    payee: str
    token: str
    amount: int
    decision: int
    policy_hash: bytes
    record_hash: bytes


def _word_address(address: str) -> bytes:
    raw = bytes.fromhex(address[2:])
    if len(raw) != 20:
        raise DecisionDataError(f"not a 20-byte address: {address!r}")
    return b"\x00" * 12 + raw


def encode_decision(data: DecisionData) -> bytes:
    """ABI-encode the seven static fields (224 bytes)."""
    for name, value in (
        ("deal_id", data.deal_id),
        ("policy_hash", data.policy_hash),
        ("record_hash", data.record_hash),
    ):
        if len(value) != 32:
            raise DecisionDataError(f"{name} must be 32 bytes")
    if not 0 <= data.amount < 2**256:
        raise DecisionDataError("amount must fit in uint256")
    if not 0 <= data.decision < 2**8:
        raise DecisionDataError("decision must fit in uint8")
    return b"".join(
        (
            data.deal_id,
            _word_address(data.payee),
            _word_address(data.token),
            data.amount.to_bytes(32, "big"),
            data.decision.to_bytes(32, "big"),
            data.policy_hash,
            data.record_hash,
        )
    )


def decode_decision(raw: bytes) -> DecisionData:
    """Decode attestation data, rejecting anything that is not exactly 7 words."""
    if len(raw) != _ENCODED_LENGTH:
        raise DecisionDataError(f"expected {_ENCODED_LENGTH} bytes, got {len(raw)}")
    words = [raw[i : i + 32] for i in range(0, _ENCODED_LENGTH, 32)]
    for index in (1, 2):
        if words[index][:12] != b"\x00" * 12:
            raise DecisionDataError("address word has non-zero padding")
    decision = int.from_bytes(words[4], "big")
    if decision >= 2**8:
        raise DecisionDataError("decision does not fit in uint8")
    return DecisionData(
        deal_id=words[0],
        payee="0x" + words[1][12:].hex(),
        token="0x" + words[2][12:].hex(),
        amount=int.from_bytes(words[3], "big"),
        decision=decision,
        policy_hash=words[5],
        record_hash=words[6],
    )
