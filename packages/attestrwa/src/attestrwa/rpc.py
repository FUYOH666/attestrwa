"""Read-only chain access for the verifier.

Only ``eth_call`` and ``eth_chainId`` are used. Receipts and logs are
deliberately avoided: public RPC endpoints prune them, while state reads keep
working, so a third party can verify a record long after it was made.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from attestrwa.hashing import keccak256, to_hex


class RpcError(RuntimeError):
    """The RPC endpoint could not be reached or returned an error."""


def selector(signature: str) -> bytes:
    return keccak256(signature.encode("ascii"))[:4]


def _word(value: bytes | int | str) -> bytes:
    if isinstance(value, bytes):
        if len(value) != 32:
            raise ValueError("expected a 32-byte word")
        return value
    if isinstance(value, int):
        return value.to_bytes(32, "big")
    raw = bytes.fromhex(value[2:])
    return b"\x00" * (32 - len(raw)) + raw


def calldata(signature: str, *args: bytes | int | str) -> bytes:
    """Calldata for a function whose arguments are all single static words."""
    return selector(signature) + b"".join(_word(arg) for arg in args)


class JsonRpc:
    """Minimal JSON-RPC client over HTTP(S), standard library only."""

    def __init__(self, url: str, *, timeout: float = 20.0) -> None:
        if not url.startswith(("http://", "https://")):
            raise RpcError("RPC URL must start with http:// or https://")
        self.url = url
        self.timeout = timeout
        self._next_id = 0

    def request(self, method: str, params: list[Any]) -> Any:
        self._next_id += 1
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        ).encode("utf-8")
        http_request = urllib.request.Request(  # noqa: S310 - scheme checked in __init__
            self.url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "attestrwa-verifier"},
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout) as response:  # noqa: S310
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise RpcError(f"{method} failed: {exc}") from exc
        if not isinstance(body, dict):
            raise RpcError(f"{method} returned a malformed response")
        if body.get("error"):
            error = body["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise RpcError(f"{method} failed: {message}")
        return body.get("result")

    def chain_id(self) -> int:
        return int(self.request("eth_chainId", []), 16)

    def block_number(self) -> int:
        return int(self.request("eth_blockNumber", []), 16)

    def block(self, tag: int | str = "latest") -> tuple[int, int]:
        """Return ``(number, timestamp)`` of a block."""
        result = self.request(
            "eth_getBlockByNumber", [hex(tag) if isinstance(tag, int) else tag, False]
        )
        if not isinstance(result, dict):
            raise RpcError("eth_getBlockByNumber returned no block")
        return int(result["number"], 16), int(result["timestamp"], 16)

    def balance(self, address: str) -> int:
        return int(self.request("eth_getBalance", [address, "latest"]), 16)

    def eth_call(self, to: str, data: bytes, block: int | str = "latest") -> bytes:
        tag = hex(block) if isinstance(block, int) else block
        result = self.request("eth_call", [{"to": to, "data": to_hex(data)}, tag])
        if not isinstance(result, str) or not result.startswith("0x"):
            raise RpcError("eth_call returned a malformed result")
        return bytes.fromhex(result[2:])


# ---- EAS -------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Attestation:
    """The EAS ``Attestation`` struct."""

    uid: bytes
    schema: bytes
    time: int
    expiration_time: int
    revocation_time: int
    ref_uid: bytes
    recipient: str
    attester: str
    revocable: bool
    data: bytes

    @property
    def exists(self) -> bool:
        return self.uid != b"\x00" * 32


def _address_from_word(word: bytes) -> str:
    return "0x" + word[12:].hex()


def decode_attestation(raw: bytes) -> Attestation:
    """Decode the return data of ``EAS.getAttestation(bytes32)``."""
    if len(raw) < 32 * 12:
        raise RpcError("getAttestation returned too little data")
    start = int.from_bytes(raw[0:32], "big")
    head = raw[start : start + 32 * 10]
    if len(head) != 32 * 10:
        raise RpcError("getAttestation returned a truncated struct")
    words = [head[i : i + 32] for i in range(0, 320, 32)]
    data_offset = start + int.from_bytes(words[9], "big")
    length = int.from_bytes(raw[data_offset : data_offset + 32], "big")
    data = raw[data_offset + 32 : data_offset + 32 + length]
    if len(data) != length:
        raise RpcError("getAttestation returned truncated attestation data")
    return Attestation(
        uid=words[0],
        schema=words[1],
        time=int.from_bytes(words[2], "big"),
        expiration_time=int.from_bytes(words[3], "big"),
        revocation_time=int.from_bytes(words[4], "big"),
        ref_uid=words[5],
        recipient=_address_from_word(words[6]),
        attester=_address_from_word(words[7]),
        revocable=int.from_bytes(words[8], "big") != 0,
        data=data,
    )


def read_attestation(rpc: Any, eas: str, uid: str, block: int | str = "latest") -> Attestation:
    raw = rpc.eth_call(eas, calldata("getAttestation(bytes32)", uid), block)
    return decode_attestation(raw)


# ---- SettlementEscrow ------------------------------------------------------

DEAL_STATUS = ("none", "open", "released", "refunded")


@dataclass(slots=True, frozen=True)
class Deal:
    """The escrow's ``Deal`` struct."""

    buyer: str
    deadline: int
    status: int
    payee: str
    deposited_at: int
    token: str
    amount: int

    @property
    def status_name(self) -> str:
        return DEAL_STATUS[self.status] if self.status < len(DEAL_STATUS) else "unknown"


def decode_deal(raw: bytes) -> Deal:
    if len(raw) != 32 * 7:
        raise RpcError("getDeal returned an unexpected amount of data")
    words = [raw[i : i + 32] for i in range(0, 224, 32)]
    return Deal(
        buyer=_address_from_word(words[0]),
        deadline=int.from_bytes(words[1], "big"),
        status=int.from_bytes(words[2], "big"),
        payee=_address_from_word(words[3]),
        deposited_at=int.from_bytes(words[4], "big"),
        token=_address_from_word(words[5]),
        amount=int.from_bytes(words[6], "big"),
    )


def read_deal(rpc: Any, escrow: str, deal_id: str, block: int | str = "latest") -> Deal:
    return decode_deal(rpc.eth_call(escrow, calldata("getDeal(bytes32)", deal_id), block))


def read_escrow_eas(rpc: Any, escrow: str) -> str:
    raw = rpc.eth_call(escrow, calldata("eas()"))
    if len(raw) != 32:
        raise RpcError("eas() returned an unexpected amount of data")
    return _address_from_word(raw)


def read_escrow_schema_uid(rpc: Any, escrow: str) -> bytes:
    raw = rpc.eth_call(escrow, calldata("schemaUid()"))
    if len(raw) != 32:
        raise RpcError("schemaUid() returned an unexpected amount of data")
    return raw


def read_attester_trusted(rpc: Any, escrow: str, attester: str) -> bool:
    raw = rpc.eth_call(escrow, calldata("trustedAttesters(address)", attester))
    if len(raw) != 32:
        raise RpcError("trustedAttesters() returned an unexpected amount of data")
    return int.from_bytes(raw, "big") != 0
