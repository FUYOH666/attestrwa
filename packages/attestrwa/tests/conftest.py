"""Shared fixtures: a demo policy, a registry, a record builder and a fake chain."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from attestrwa.eas import DecisionData, encode_decision, schema_uid
from attestrwa.hashing import sha256, to_hex
from attestrwa.policy import PolicyPack, load_policy, parse_policy
from attestrwa.record import build_case_record, build_record, make_envelope, record_hash
from attestrwa.registry import Registry, parse_registry
from attestrwa.rpc import RpcError, calldata, selector
from attestrwa.signing import public_key_from_seed, sign_hash

REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_FILE = REPO_ROOT / "data" / "policies" / "settlement-demo-v2.yaml"
STRICT_POLICY_FILE = REPO_ROOT / "data" / "policies" / "settlement-demo-v2-strict.yaml"
REGISTRY_FILE = REPO_ROOT / "data" / "registry" / "payees.json"

CHAIN_ID = 84532
EAS = "0x4200000000000000000000000000000000000021"
ORACLE = "0x40c57923924b5c5c5455c48d93317139addac8fb"
ESCROW = "0x" + "e5" * 20
TOKEN = "0x" + "aa" * 20
BUYER = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
PAYEE = "0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc"
UNREGISTERED_PAYEE = "0x90f79bf6eb2c4f870365e785982e1f101e93b906"
ATTESTER = "0x15d34aaf54267db7d7c367839aaf71a00a2c6a65"
DEAL_ID = "0x" + "d1" * 32
UID = "0x" + "a7" * 32
NONCE = "0x000102030405060708090a0b0c0d0e0f"
DEPOSITED_AT = 1_780_000_000
DEADLINE = DEPOSITED_AT + 86_400
EVAL_BLOCK = 57_668_489
WORD_FALSE = "0x" + "00" * 32
WORD_TRUE = "0x" + "00" * 31 + "01"


@pytest.fixture(scope="session")
def pack() -> PolicyPack:
    return load_policy(POLICY_FILE)


@pytest.fixture(scope="session")
def strict_pack() -> PolicyPack:
    return load_policy(STRICT_POLICY_FILE)


@pytest.fixture(scope="session")
def registry() -> Registry:
    return parse_registry(REGISTRY_FILE.read_bytes())


def oracle_input(name: str, address: str, *, sanctioned: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "type": "bool",
        "value": sanctioned,
        "source": {
            "kind": "onchain",
            "chain_id": CHAIN_ID,
            "to": ORACLE,
            "call": "isSanctioned(address)",
            "data": to_hex(calldata("isSanctioned(address)", address)),
            "block_number": EVAL_BLOCK,
            "result": WORD_TRUE if sanctioned else WORD_FALSE,
        },
    }


def make_inputs(
    registry: Registry,
    *,
    payee: str = PAYEE,
    amount: str = "580000000",
    jurisdiction: str = "TH",
    payee_sanctioned: bool = False,
    buyer_sanctioned: bool = False,
) -> list[dict[str, Any]]:
    return [
        {
            "name": "payee_registered",
            "type": "bool",
            "value": registry.contains(payee),
            "source": {
                "kind": "registry",
                "ref": "data/registry/payees.json",
                "sha256": registry.sha256,
                "key": payee,
            },
        },
        oracle_input("payee_sanctioned", payee, sanctioned=payee_sanctioned),
        oracle_input("buyer_sanctioned", BUYER, sanctioned=buyer_sanctioned),
        {
            "name": "amount",
            "type": "int",
            "value": amount,
            "source": {"kind": "subject", "field": "amount"},
        },
        {
            "name": "jurisdiction",
            "type": "string",
            "value": jurisdiction,
            "source": {"kind": "declared", "by": "integrator:demo"},
        },
    ]


def make_body(
    pack: PolicyPack,
    registry: Registry,
    *,
    payee: str = PAYEE,
    amount: str = "580000000",
    jurisdiction: str = "TH",
    payee_sanctioned: bool = False,
    buyer_sanctioned: bool = False,
    supersedes: str | None = None,
) -> dict[str, Any]:
    subject = {
        "chain_id": CHAIN_ID,
        "escrow": ESCROW,
        "deal_id": DEAL_ID,
        "buyer": BUYER,
        "payee": payee,
        "token": TOKEN,
        "amount": amount,
        "deadline": DEADLINE,
        "deposited_at": DEPOSITED_AT,
    }
    return build_record(
        subject=subject,
        evaluation={"block_number": EVAL_BLOCK, "evaluated_at": DEPOSITED_AT + 60},
        pack=pack,
        policy_uri="data/policies/settlement-demo-v2.yaml",
        inputs=make_inputs(
            registry,
            payee=payee,
            amount=amount,
            jurisdiction=jurisdiction,
            payee_sanctioned=payee_sanctioned,
            buyer_sanctioned=buyer_sanctioned,
        ),
        attester_address=ATTESTER,
        software="attestrwa-attester/2.0.0",
        anchor={"chain_id": CHAIN_ID, "eas": EAS, "schema_uid": to_hex(schema_uid())},
        supersedes=supersedes,
        nonce=NONCE,
    )


@pytest.fixture
def approve_body(pack: PolicyPack, registry: Registry) -> dict[str, Any]:
    return make_body(pack, registry)


@pytest.fixture
def reject_body(pack: PolicyPack, registry: Registry) -> dict[str, Any]:
    return make_body(pack, registry, payee=UNREGISTERED_PAYEE)


def envelope_for(body: dict[str, Any]) -> dict[str, Any]:
    return make_envelope(
        body, network="test", attestation={"uid": UID, "tx_hash": "0x" + "bb" * 32}
    )


@pytest.fixture
def approve_envelope(approve_body: dict[str, Any]) -> dict[str, Any]:
    return envelope_for(approve_body)


# ---- Fake chain ------------------------------------------------------------


def _word(value: int | str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value.rjust(32, b"\x00")
    if isinstance(value, int):
        return value.to_bytes(32, "big")
    return bytes.fromhex(value[2:]).rjust(32, b"\x00")


def encode_attestation(fields: dict[str, Any]) -> bytes:
    """ABI-encode the EAS ``Attestation`` struct the way ``getAttestation`` returns it."""
    data: bytes = fields["data"]
    head = b"".join(
        (
            _word(fields["uid"]),
            _word(fields["schema"]),
            _word(fields["time"]),
            _word(fields["expiration_time"]),
            _word(fields["revocation_time"]),
            _word(fields["ref_uid"]),
            _word(fields["recipient"]),
            _word(fields["attester"]),
            _word(1 if fields["revocable"] else 0),
            _word(32 * 10),
        )
    )
    padded = data + b"\x00" * (-len(data) % 32)
    return _word(32) + head + _word(len(data)) + padded


class FakeChain:
    """In-memory stand-in for the RPC endpoint: one escrow, one EAS, one oracle."""

    def __init__(self, body: dict[str, Any], uid: str = UID) -> None:
        subject = body["subject"]
        self.chain = subject["chain_id"]
        self.uid = uid
        self.attestation: dict[str, Any] = {
            "uid": uid,
            "schema": to_hex(schema_uid()),
            "time": subject["deposited_at"] + 120,
            "expiration_time": subject["deadline"],
            "revocation_time": 0,
            "ref_uid": "0x" + "00" * 32,
            "recipient": subject["escrow"],
            "attester": body["attester"]["address"],
            "revocable": True,
            "data": encode_decision(
                DecisionData(
                    deal_id=bytes.fromhex(subject["deal_id"][2:]),
                    payee=subject["payee"],
                    token=subject["token"],
                    amount=int(subject["amount"]),
                    decision=body["decision"]["code"],
                    policy_hash=bytes.fromhex(body["policy"]["sha256"][2:]),
                    record_hash=record_hash(body),
                )
            ),
        }
        self.deal: dict[str, Any] = {
            "buyer": subject["buyer"],
            "deadline": subject["deadline"],
            "status": 1,
            "payee": subject["payee"],
            "deposited_at": subject["deposited_at"],
            "token": subject["token"],
            "amount": int(subject["amount"]),
        }
        self.escrow = subject["escrow"]
        self.escrow_eas = body["anchor"]["eas"]
        self.escrow_schema = body["anchor"]["schema_uid"]
        self.trusted = {body["attester"]["address"]}
        self.sanctioned: set[str] = set()
        self.history_available = True
        self.block_times = {body["evaluation"]["block_number"]: body["evaluation"]["evaluated_at"]}
        self.calls: list[tuple[str, str, int | str]] = []

    def chain_id(self) -> int:
        return self.chain

    def block(self, tag: int | str = "latest") -> tuple[int, int]:
        if not self.history_available or tag not in self.block_times:
            raise RpcError("eth_getBlockByNumber failed: pruned history unavailable")
        return tag, self.block_times[tag]

    def eth_call(self, to: str, data: bytes, block: int | str = "latest") -> bytes:
        self.calls.append((to, to_hex(data), block))
        sel = data[:4]
        if to == self.escrow_eas and sel == selector("getAttestation(bytes32)"):
            if to_hex(data[4:36]) != self.uid:
                empty = dict(self.attestation, uid="0x" + "00" * 32, data=b"")
                return encode_attestation(empty)
            return encode_attestation(self.attestation)
        if to == self.escrow and sel == selector("getDeal(bytes32)"):
            deal = self.deal
            return b"".join(
                _word(deal[name])
                for name in (
                    "buyer",
                    "deadline",
                    "status",
                    "payee",
                    "deposited_at",
                    "token",
                    "amount",
                )
            )
        if to == self.escrow and sel == selector("eas()"):
            return _word(self.escrow_eas)
        if to == self.escrow and sel == selector("schemaUid()"):
            return _word(self.escrow_schema)
        if to == self.escrow and sel == selector("trustedAttesters(address)"):
            address = "0x" + data[16:36].hex()
            return _word(1 if address in self.trusted else 0)
        if to == ORACLE and sel == selector("isSanctioned(address)"):
            if isinstance(block, int) and not self.history_available:
                raise RpcError("eth_call failed: pruned history unavailable")
            address = "0x" + data[16:36].hex()
            return _word(1 if address in self.sanctioned else 0)
        raise RpcError(f"unexpected call to {to} with {to_hex(sel)}")


@pytest.fixture
def chain(approve_body: dict[str, Any]) -> FakeChain:
    return FakeChain(approve_body)


def clone(value: Any) -> Any:
    return copy.deepcopy(value)


# ---- Cases (format 0.2) ----------------------------------------------------

CASE_POLICY = b"""pack_id: case-demo
version: "1.0.0"
description: test policy for a decision about some material
inputs:
  label:
    type: string
    source: model
    field: label
    model: model-a
  confidence:
    type: int
    source: model
    field: confidence
    model: model-a
  documents:
    type: int
    source: document
    reading: count
  value:
    type: int
    source: document
    reading: extract
  approved:
    type: bool
    source: human
rules:
  - id: confident
    require: confidence >= 90
  - id: two-documents
    require: documents >= 2
  - id: value-within-limit
    require: value <= 50000
  - id: signed-off
    require: approved == true
"""

# Not a secret: a key for tests only.
CASE_SEED = bytes(range(32))
CASE_PUBLIC_KEY = to_hex(public_key_from_seed(CASE_SEED))
OTHER_SEED = bytes(range(32, 64))
OTHER_PUBLIC_KEY = to_hex(public_key_from_seed(OTHER_SEED))
CASE_EVALUATED_AT = 1_794_303_000

CASE_FILES: dict[str, bytes] = {
    "subject.json": b'{"item": "vacuum bottle"}\n',
    "invoice.txt": b"Invoice\nTotal USD 18,400.00\n",
    "packing.txt": b"Packing list\n100 cartons\n",
    "prompt.txt": b"Classify the goods.\n",
}


def model_output(label: str = "961700", confidence: int = 96) -> bytes:
    return json.dumps({"label": label, "confidence": confidence, "note": 0.5}).encode()


def file_hash(content: bytes) -> str:
    return to_hex(sha256(content))


def case_files(confidence: int = 96) -> dict[str, bytes]:
    """Every file a test case record cites, by name."""
    return {**CASE_FILES, "output.json": model_output(confidence=confidence)}


def make_case_inputs(
    *,
    confidence: int = 96,
    documents: tuple[str, ...] = ("invoice.txt", "packing.txt"),
    value: str = "18400",
    approved: bool = True,
) -> list[dict[str, Any]]:
    files = case_files(confidence)
    model = {
        "kind": "model",
        "provider": "example",
        "model": "model-a",
        "prompt_sha256": file_hash(files["prompt.txt"]),
        "output_sha256": file_hash(files["output.json"]),
    }
    return [
        {
            "name": "label",
            "type": "string",
            "value": "961700",
            "source": {**model, "field": "label"},
        },
        {
            "name": "confidence",
            "type": "int",
            "value": str(confidence),
            "source": {**model, "field": "confidence"},
        },
        {
            "name": "documents",
            "type": "int",
            "value": str(len(documents)),
            "source": {
                "kind": "document",
                "reading": "count",
                "items": [{"ref": name, "sha256": file_hash(files[name])} for name in documents],
            },
        },
        {
            "name": "value",
            "type": "int",
            "value": value,
            "source": {
                "kind": "document",
                "reading": "extract",
                "items": [
                    {
                        "ref": "invoice.txt",
                        "sha256": file_hash(files["invoice.txt"]),
                        "locator": "Total",
                    }
                ],
            },
        },
        {
            "name": "approved",
            "type": "bool",
            "value": approved,
            "source": {"kind": "human", "by": "reviewer:R-07", "at": CASE_EVALUATED_AT - 600},
        },
    ]


@pytest.fixture(scope="session")
def case_pack() -> PolicyPack:
    return parse_policy(CASE_POLICY)


def make_case_body(case_pack: PolicyPack, **inputs: Any) -> dict[str, Any]:
    return build_case_record(
        case_id="CASE-0001",
        title="Classification of a vacuum bottle",
        digest=file_hash(CASE_FILES["subject.json"]),
        evaluated_at=CASE_EVALUATED_AT,
        pack=case_pack,
        policy_uri="policies/case-demo.yaml",
        inputs=make_case_inputs(**inputs),
        public_key=CASE_PUBLIC_KEY,
        software="attestrwa-tests/0",
        nonce=NONCE,
    )


def sign_case(body: dict[str, Any], seed: bytes = CASE_SEED) -> dict[str, Any]:
    """An envelope whose signature is over the body's current hash."""
    return make_envelope(body, signature=to_hex(sign_hash(seed, record_hash(body))))


def supplied(files: dict[str, bytes]) -> list[tuple[str, bytes]]:
    return list(files.items())


@pytest.fixture
def case_body(case_pack: PolicyPack) -> dict[str, Any]:
    return make_case_body(case_pack)


@pytest.fixture
def case_envelope(case_body: dict[str, Any]) -> dict[str, Any]:
    return sign_case(case_body)
