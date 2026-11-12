"""Chain access for the attester: state reads at a fixed block, and the one write."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Protocol

from eth_account import Account
from web3 import Web3

from app.errors import UpstreamError

logger = logging.getLogger(__name__)

ZERO_UID = b"\x00" * 32

_EAS_WRITE_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "stateMutability": "payable",
        "name": "attest",
        "inputs": [
            {
                "name": "request",
                "type": "tuple",
                "components": [
                    {"name": "schema", "type": "bytes32"},
                    {
                        "name": "data",
                        "type": "tuple",
                        "components": [
                            {"name": "recipient", "type": "address"},
                            {"name": "expirationTime", "type": "uint64"},
                            {"name": "revocable", "type": "bool"},
                            {"name": "refUID", "type": "bytes32"},
                            {"name": "data", "type": "bytes"},
                            {"name": "value", "type": "uint256"},
                        ],
                    },
                ],
            }
        ],
        "outputs": [{"name": "", "type": "bytes32"}],
    },
    {
        "type": "event",
        "name": "Attested",
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "recipient", "type": "address"},
            {"indexed": True, "name": "attester", "type": "address"},
            {"indexed": False, "name": "uid", "type": "bytes32"},
            {"indexed": True, "name": "schemaUID", "type": "bytes32"},
        ],
    },
]


class Rpc(Protocol):
    """The read surface the attester needs; ``attestrwa.rpc.JsonRpc`` satisfies it."""

    def chain_id(self) -> int: ...

    def block(self, tag: int | str = "latest") -> tuple[int, int]: ...

    def balance(self, address: str) -> int: ...

    def eth_call(self, to: str, data: bytes, block: int | str = "latest") -> bytes: ...


@dataclass(slots=True, frozen=True)
class AttestationReceipt:
    uid: str
    tx_hash: str
    block_number: int


class Signer(Protocol):
    """Writes the attestation. The key never leaves this object."""

    @property
    def address(self) -> str: ...

    def attest(
        self,
        *,
        schema_uid: bytes,
        recipient: str,
        expiration_time: int,
        ref_uid: bytes,
        data: bytes,
    ) -> AttestationReceipt: ...


class EasSigner:
    """Sends ``EAS.attest`` transactions from the attester key."""

    def __init__(
        self,
        *,
        rpc_url: str,
        private_key: str,
        eas_address: str,
        chain_id: int,
        receipt_timeout: int = 60,
    ) -> None:
        self._account = Account.from_key(private_key)
        self._w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        self._eas = self._w3.eth.contract(
            address=Web3.to_checksum_address(eas_address), abi=_EAS_WRITE_ABI
        )
        self._chain_id = chain_id
        self._receipt_timeout = receipt_timeout
        # One transaction at a time: the nonce is read as "pending" and must not
        # be handed to two requests.
        self._lock = threading.Lock()

    @property
    def address(self) -> str:
        return self._account.address.lower()

    def attest(
        self,
        *,
        schema_uid: bytes,
        recipient: str,
        expiration_time: int,
        ref_uid: bytes,
        data: bytes,
    ) -> AttestationReceipt:
        request = (
            schema_uid,
            (
                Web3.to_checksum_address(recipient),
                int(expiration_time),
                True,
                ref_uid,
                data,
                0,
            ),
        )
        with self._lock:
            try:
                nonce = self._w3.eth.get_transaction_count(self._account.address, "pending")
                tx = self._eas.functions.attest(request).build_transaction(
                    {
                        "from": self._account.address,
                        "nonce": nonce,
                        "chainId": self._chain_id,
                        "value": 0,
                    }
                )
                signed = self._account.sign_transaction(tx)
                tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = self._w3.eth.wait_for_transaction_receipt(
                    tx_hash, timeout=self._receipt_timeout
                )
            except Exception as exc:  # noqa: BLE001 - every chain failure fails closed
                raise UpstreamError(f"EAS attest failed: {type(exc).__name__}: {exc}") from exc
        if receipt.status != 1:
            raise UpstreamError(f"EAS attest reverted in transaction 0x{tx_hash.hex()}")
        events = self._eas.events.Attested().process_receipt(receipt)
        if not events:
            raise UpstreamError("EAS attest receipt has no Attested event")
        uid = events[0]["args"]["uid"]
        logger.info("attested uid=0x%s block=%s", uid.hex(), receipt.blockNumber)
        return AttestationReceipt(
            uid="0x" + uid.hex(),
            tx_hash="0x" + tx_hash.hex().removeprefix("0x"),
            block_number=int(receipt.blockNumber),
        )
