"""The attester: read the deal, evaluate the policy, record, attest.

The decision itself is made by ``attestrwa.record.build_record``; this module
only gathers what that function needs and anchors what it returns. Nothing
about the deal is taken from the caller: buyer, payee, token and amount are
read from the escrow at a fixed block.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from attestrwa import rpc as chain_reads
from attestrwa.eas import DecisionData, decode_decision, encode_decision, schema_uid
from attestrwa.hashing import to_hex
from attestrwa.policy import DSLError, PolicyPack, load_policy
from attestrwa.record import RecordError, build_record, make_envelope, record_hash
from attestrwa.registry import Registry, RegistryError, parse_registry
from attestrwa.rpc import RpcError
from attestrwa.verify import verify

from app.chain import ZERO_UID, Rpc, Signer
from app.config import Settings
from app.errors import (
    ConfigError,
    DealNotActionable,
    DealNotFound,
    InputError,
    UpstreamError,
)
from app.paths import resolve
from app.providers import resolve_inputs
from app.store import RecordStore

logger = logging.getLogger(__name__)

# A decision must be usable: refuse deals whose deadline is this close.
MIN_SECONDS_BEFORE_DEADLINE = 30

_EXPLORERS = {
    "base-sepolia": ("https://base-sepolia.easscan.org", "https://sepolia.basescan.org"),
    "base": ("https://base.easscan.org", "https://basescan.org"),
}


@dataclass(slots=True, frozen=True)
class Outcome:
    envelope: dict[str, Any]
    reused: bool


class AttesterService:
    def __init__(
        self,
        *,
        settings: Settings,
        rpc: Rpc,
        signer: Signer | None,
        store: RecordStore,
        pack: PolicyPack,
        registry: Registry,
    ) -> None:
        self.settings = settings
        self.rpc = rpc
        self.signer = signer
        self.store = store
        self.pack = pack
        self.registry = registry
        self.escrow = settings.escrow_address.lower()
        self.eas = settings.eas_address.lower()
        self.schema_uid = schema_uid()
        # One decision at a time keeps "one live decision per deal" race-free.
        self._lock = threading.Lock()

    # ---- construction ------------------------------------------------------

    @classmethod
    def from_settings(cls, settings: Settings) -> AttesterService:
        from attestrwa.rpc import JsonRpc

        from app.chain import EasSigner

        if not settings.escrow_address:
            raise ConfigError("ATTESTRWA_ESCROW_ADDRESS is not set")
        try:
            pack = load_policy(resolve(settings.policy_file))
            registry = parse_registry(resolve(settings.registry_file).read_bytes())
        except (DSLError, RegistryError, OSError) as exc:
            raise ConfigError(f"cannot load policy or registry: {exc}") from exc
        signer = None
        if settings.attester_private_key:
            signer = EasSigner(
                rpc_url=settings.rpc_url,
                private_key=settings.attester_private_key,
                eas_address=settings.eas_address,
                chain_id=settings.chain_id,
                receipt_timeout=settings.receipt_timeout_seconds,
            )
        return cls(
            settings=settings,
            rpc=JsonRpc(settings.rpc_url),
            signer=signer,
            store=RecordStore(Path(resolve(settings.records_dir))),
            pack=pack,
            registry=registry,
        )

    # ---- deciding ----------------------------------------------------------

    def _require_target(self, chain_id: int, escrow: str) -> None:
        if chain_id != self.settings.chain_id or escrow.lower() != self.escrow:
            raise InputError(
                f"this attester serves escrow {self.escrow} on chain {self.settings.chain_id}"
            )

    def _live_decision(self, deal_id: str) -> tuple[dict[str, Any] | None, str | None]:
        """Return ``(live envelope, uid to supersede)`` for a deal."""
        latest = self.store.latest(deal_id)
        if latest is None:
            return None, None
        uid = latest["attestation"]["uid"]
        attestation = chain_reads.read_attestation(self.rpc, self.eas, uid)
        if not attestation.exists:
            # The chain does not know this attestation (a reset dev chain).
            return None, None
        if attestation.revocation_time == 0:
            return latest, None
        return None, uid

    def attest(
        self, *, chain_id: int, escrow: str, deal_id: str, declared: dict[str, Any], caller: str
    ) -> Outcome:
        """Decide about one deal and anchor the decision. Idempotent per deal."""
        self._require_target(chain_id, escrow)
        if self.signer is None:
            raise ConfigError(
                "ATTESTRWA_ATTESTER_PRIVATE_KEY is not set; this instance cannot attest"
            )
        with self._lock:
            try:
                return self._attest_locked(deal_id, declared, caller)
            except RpcError as exc:
                raise UpstreamError(f"chain read failed: {exc}") from exc

    def _attest_locked(self, deal_id: str, declared: dict[str, Any], caller: str) -> Outcome:
        live, supersedes = self._live_decision(deal_id)
        if live is not None:
            return Outcome(envelope=live, reused=True)

        block_number, block_time = self.rpc.block("latest")
        deal = chain_reads.read_deal(self.rpc, self.escrow, deal_id, block_number)
        if deal.status == 0:
            raise DealNotFound(f"escrow {self.escrow} has no deal {deal_id}")
        if deal.status != 1:
            raise DealNotActionable(f"deal {deal_id} is already {deal.status_name}")
        if deal.deadline - block_time < MIN_SECONDS_BEFORE_DEADLINE:
            raise DealNotActionable(f"deal {deal_id} is at or too close to its deadline")

        subject = {
            "chain_id": self.settings.chain_id,
            "escrow": self.escrow,
            "deal_id": deal_id,
            "buyer": deal.buyer,
            "payee": deal.payee,
            "token": deal.token,
            "amount": str(deal.amount),
            "deadline": deal.deadline,
            "deposited_at": deal.deposited_at,
        }
        inputs = resolve_inputs(
            pack=self.pack,
            subject=subject,
            block_number=block_number,
            declared=declared,
            declared_by=f"integrator:{caller}",
            rpc=self.rpc,
            registry=self.registry,
            registry_ref=self.settings.registry_file,
        )
        try:
            body = build_record(
                subject=subject,
                evaluation={"block_number": block_number, "evaluated_at": block_time},
                pack=self.pack,
                policy_uri=self.settings.policy_file,
                inputs=inputs,
                attester_address=self.signer.address,
                software=f"attestrwa-attester/{self.settings.api_version}",
                anchor={
                    "chain_id": self.settings.chain_id,
                    "eas": self.eas,
                    "schema_uid": to_hex(self.schema_uid),
                },
                supersedes=supersedes,
            )
        except (RecordError, DSLError) as exc:
            raise ConfigError(f"policy and inputs do not produce a valid record: {exc}") from exc

        digest = record_hash(body)
        receipt = self.signer.attest(
            schema_uid=self.schema_uid,
            recipient=self.escrow,
            expiration_time=min(block_time + self.settings.attestation_ttl_seconds, deal.deadline),
            ref_uid=bytes.fromhex(supersedes[2:]) if supersedes else ZERO_UID,
            data=encode_decision(
                DecisionData(
                    deal_id=bytes.fromhex(deal_id[2:]),
                    payee=deal.payee,
                    token=deal.token,
                    amount=deal.amount,
                    decision=body["decision"]["code"],
                    policy_hash=bytes.fromhex(self.pack.sha256[2:]),
                    record_hash=digest,
                )
            ),
        )
        envelope = make_envelope(
            body,
            network=self.settings.network,
            attestation={"uid": receipt.uid, "tx_hash": receipt.tx_hash},
            links=self._links(receipt.uid, receipt.tx_hash),
        )
        self.store.save(envelope)
        logger.info(
            "decision deal=%s outcome=%s record=%s uid=%s",
            deal_id,
            body["decision"]["outcome"],
            envelope["record_hash"],
            receipt.uid,
        )
        return Outcome(envelope=envelope, reused=False)

    def _links(self, uid: str, tx_hash: str) -> dict[str, str]:
        explorers = _EXPLORERS.get(self.settings.network)
        if explorers is None:
            return {}
        eas_scan, block_explorer = explorers
        return {
            "attestation": f"{eas_scan}/attestation/view/{uid}",
            "transaction": f"{block_explorer}/tx/{tx_hash}",
            "escrow": f"{block_explorer}/address/{self.escrow}",
        }

    # ---- reading -----------------------------------------------------------

    def record(self, deal_id: str) -> dict[str, Any] | None:
        return self.store.latest(deal_id)

    def record_by_hash(self, record_hash_hex: str) -> dict[str, Any] | None:
        return self.store.by_hash(record_hash_hex)

    def lookup(self, deal_id: str) -> dict[str, Any]:
        """Stored decisions for a deal, each with its live on-chain state."""
        try:
            deal = chain_reads.read_deal(self.rpc, self.escrow, deal_id)
            decisions = []
            for entry in self.store.history(deal_id):
                attestation = chain_reads.read_attestation(
                    self.rpc, self.eas, entry["attestation_uid"]
                )
                item: dict[str, Any] = {
                    "attestation_uid": entry["attestation_uid"],
                    "record_hash": entry["record_hash"],
                    "decision": entry["decision"],
                    "on_chain": attestation.exists,
                }
                if attestation.exists:
                    item.update(
                        {
                            "attester": attestation.attester,
                            "time": attestation.time,
                            "expiration_time": attestation.expiration_time,
                            "revoked": attestation.revocation_time != 0,
                            "decision_code": decode_decision(attestation.data).decision,
                        }
                    )
                decisions.append(item)
        except RpcError as exc:
            raise UpstreamError(f"chain read failed: {exc}") from exc
        return {"deal_id": deal_id, "deal_status": deal.status_name, "decisions": decisions}

    def verify(self, document: dict[str, Any]) -> dict[str, Any]:
        """Run the independent verifier with this instance's chain, policy and registry."""
        try:
            report = verify(
                document,
                rpc=self.rpc,
                policy=self.pack,
                registry=self.registry,
                recheck_inputs=True,
            )
        except RpcError as exc:
            raise UpstreamError(f"chain read failed: {exc}") from exc
        return report.to_dict()

    def health(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "status": "ok",
            "service": "attestrwa-attester",
            "version": self.settings.api_version,
            "network": self.settings.network,
            "chain_id": self.settings.chain_id,
            "escrow": self.escrow,
            "eas": self.eas,
            "schema_uid": to_hex(self.schema_uid),
            "policy": {
                "pack_id": self.pack.pack_id,
                "version": self.pack.version,
                "sha256": self.pack.sha256,
            },
            "registry": {
                "registry_id": self.registry.registry_id,
                "version": self.registry.version,
                "sha256": self.registry.sha256,
            },
            "attester": self.signer.address if self.signer else None,
        }
        try:
            number, _ = self.rpc.block("latest")
            info["block_number"] = number
            info["chain_matches"] = self.rpc.chain_id() == self.settings.chain_id
            info["escrow_schema_matches"] = (
                chain_reads.read_escrow_schema_uid(self.rpc, self.escrow) == self.schema_uid
            )
            if self.signer:
                info["attester_trusted"] = chain_reads.read_attester_trusted(
                    self.rpc, self.escrow, self.signer.address
                )
                info["attester_balance_wei"] = str(self.rpc.balance(self.signer.address))
        except RpcError as exc:
            info["status"] = "degraded"
            info["error"] = str(exc)
            return info
        ready = (
            info["chain_matches"]
            and info["escrow_schema_matches"]
            and info.get("attester_trusted", False)
        )
        if not ready:
            info["status"] = "degraded"
        return info
