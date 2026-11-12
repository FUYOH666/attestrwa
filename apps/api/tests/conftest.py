"""An in-memory chain (escrow + EAS + sanctions oracle) and a wired API client."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import pytest
from attestrwa.eas import schema_uid
from attestrwa.hashing import keccak256, to_hex
from attestrwa.policy import load_policy
from attestrwa.registry import parse_registry
from attestrwa.rpc import RpcError, selector
from fastapi.testclient import TestClient

from app.chain import AttestationReceipt
from app.config import Settings, get_settings
from app.errors import UpstreamError
from app.main import app, get_service
from app.service import AttesterService
from app.store import RecordStore

REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_FILE = "data/policies/settlement-demo-v2.yaml"
REGISTRY_FILE = "data/registry/payees.json"

CHAIN_ID = 84532
EAS = "0x4200000000000000000000000000000000000021"
ORACLE = "0x40c57923924b5c5c5455c48d93317139addac8fb"
ESCROW = "0x" + "e5" * 20
TOKEN = "0x" + "aa" * 20
BUYER = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
PAYEE = "0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc"
IMPOSTOR = "0x90f79bf6eb2c4f870365e785982e1f101e93b906"
ATTESTER = "0x15d34aaf54267db7d7c367839aaf71a00a2c6a65"
API_KEY = "test-key-123"
NOW = 1_780_000_000


def _word(value: int | str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value.rjust(32, b"\x00")
    if isinstance(value, int):
        return value.to_bytes(32, "big")
    return bytes.fromhex(value[2:]).rjust(32, b"\x00")


def _encode_attestation(fields: dict[str, Any]) -> bytes:
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
            _word(1),
            _word(320),
        )
    )
    return _word(32) + head + _word(len(data)) + data + b"\x00" * (-len(data) % 32)


class FakeChain:
    """Plays the RPC endpoint and the attester's signer."""

    def __init__(self) -> None:
        self.chain = CHAIN_ID
        self.number = 1_000
        self.timestamp = NOW
        self.deals: dict[str, dict[str, Any]] = {}
        self.attestations: dict[str, dict[str, Any]] = {}
        self.sanctioned: set[str] = set()
        self.trusted: set[str] = {ATTESTER}
        self.escrow_schema = schema_uid()
        self.oracle_down = False
        self.attest_down = False
        self._salt = itertools.count(1)

    # ---- test helpers ----

    def open_deal(
        self,
        *,
        payee: str = PAYEE,
        buyer: str = BUYER,
        amount: int = 580_000_000,
        lifetime: int = 86_400,
    ) -> str:
        deal_id = to_hex(keccak256(f"deal-{next(self._salt)}".encode()))
        self.deals[deal_id] = {
            "buyer": buyer,
            "deadline": self.timestamp + lifetime,
            "status": 1,
            "payee": payee,
            "deposited_at": self.timestamp,
            "token": TOKEN,
            "amount": amount,
        }
        self.advance()
        return deal_id

    def advance(self, seconds: int = 2) -> None:
        self.number += 1
        self.timestamp += seconds

    def revoke(self, uid: str) -> None:
        self.attestations[uid]["revocation_time"] = self.timestamp
        self.advance()

    # ---- RPC surface ----

    def chain_id(self) -> int:
        return self.chain

    def block(self, tag: int | str = "latest") -> tuple[int, int]:
        return self.number, self.timestamp

    def balance(self, address: str) -> int:
        return 10**18

    def eth_call(self, to: str, data: bytes, block: int | str = "latest") -> bytes:
        sel = data[:4]
        if to == EAS and sel == selector("getAttestation(bytes32)"):
            fields = self.attestations.get(to_hex(data[4:36]))
            if fields is None:
                fields = {
                    "uid": "0x" + "00" * 32,
                    "schema": "0x" + "00" * 32,
                    "time": 0,
                    "expiration_time": 0,
                    "revocation_time": 0,
                    "ref_uid": "0x" + "00" * 32,
                    "recipient": "0x" + "00" * 20,
                    "attester": "0x" + "00" * 20,
                    "data": b"",
                }
            return _encode_attestation(fields)
        if to == ESCROW and sel == selector("getDeal(bytes32)"):
            deal = self.deals.get(to_hex(data[4:36])) or {
                "buyer": "0x" + "00" * 20,
                "deadline": 0,
                "status": 0,
                "payee": "0x" + "00" * 20,
                "deposited_at": 0,
                "token": "0x" + "00" * 20,
                "amount": 0,
            }
            order = ("buyer", "deadline", "status", "payee", "deposited_at", "token", "amount")
            return b"".join(_word(deal[name]) for name in order)
        if to == ESCROW and sel == selector("eas()"):
            return _word(EAS)
        if to == ESCROW and sel == selector("schemaUid()"):
            return self.escrow_schema
        if to == ESCROW and sel == selector("trustedAttesters(address)"):
            return _word(1 if "0x" + data[16:36].hex() in self.trusted else 0)
        if to == ORACLE and sel == selector("isSanctioned(address)"):
            if self.oracle_down:
                raise RpcError("eth_call failed: oracle unreachable")
            return _word(1 if "0x" + data[16:36].hex() in self.sanctioned else 0)
        raise RpcError(f"unexpected call to {to}")

    # ---- signer surface ----

    @property
    def address(self) -> str:
        return ATTESTER

    def attest(
        self,
        *,
        schema_uid: bytes,
        recipient: str,
        expiration_time: int,
        ref_uid: bytes,
        data: bytes,
    ) -> AttestationReceipt:
        if self.attest_down:
            raise UpstreamError("EAS attest failed: transaction reverted")
        if expiration_time <= self.timestamp:
            raise UpstreamError("EAS attest failed: InvalidExpirationTime")
        self.advance()
        uid = to_hex(keccak256(f"uid-{len(self.attestations)}-{self.number}".encode()))
        self.attestations[uid] = {
            "uid": uid,
            "schema": to_hex(schema_uid),
            "time": self.timestamp,
            "expiration_time": expiration_time,
            "revocation_time": 0,
            "ref_uid": to_hex(ref_uid),
            "recipient": recipient,
            "attester": ATTESTER,
            "data": data,
        }
        return AttestationReceipt(uid=uid, tx_hash="0x" + "bb" * 32, block_number=self.number)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        chain_id=CHAIN_ID,
        network="test",
        eas_address=EAS,
        escrow_address=ESCROW,
        sanctions_oracle=ORACLE,
        policy_file=POLICY_FILE,
        registry_file=REGISTRY_FILE,
        records_dir=str(tmp_path / "records"),
        api_keys=f"demo-integrator:{API_KEY}",
    )


@pytest.fixture
def chain() -> FakeChain:
    return FakeChain()


@pytest.fixture
def service(settings: Settings, chain: FakeChain, tmp_path: Path) -> AttesterService:
    return AttesterService(
        settings=settings,
        rpc=chain,
        signer=chain,
        store=RecordStore(tmp_path / "records"),
        pack=load_policy(REPO_ROOT / POLICY_FILE),
        registry=parse_registry((REPO_ROOT / REGISTRY_FILE).read_bytes()),
    )


@pytest.fixture
def client(service: AttesterService, settings: Settings):
    app.dependency_overrides[get_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: settings
    get_settings.cache_clear()
    import app.auth as auth

    original = auth.get_settings
    auth.get_settings = lambda: settings
    try:
        yield TestClient(app)
    finally:
        auth.get_settings = original
        app.dependency_overrides.clear()


def attest(client: TestClient, deal_id: str, **overrides: Any):
    body = {
        "chain_id": CHAIN_ID,
        "escrow": ESCROW,
        "deal_id": deal_id,
        "declared": {"jurisdiction": "TH"},
    }
    headers = {"X-API-Key": overrides.pop("api_key", API_KEY)}
    body.update(overrides)
    return client.post("/attest/settlement", json=body, headers=headers)
