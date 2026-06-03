"""Pydantic schemas for the AttestRWA attester endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class AttestRequest(BaseModel):
    """POST /attest/settlement input."""

    deal_id: str = Field(..., description="32-byte hex (0x-prefixed) deal identifier.")
    buyer_wallet: str = Field(..., description="Buyer EOA (0x-prefixed).")
    payee_wallet: str = Field(..., description="Instructed payee wallet (0x-prefixed).")
    token_address: str = Field(..., description="ERC-20 token used for settlement.")
    amount_base_units: int = Field(..., gt=0, description="Amount in token base units.")
    developer_id: str = Field(..., description="Developer feed ID under data/synthetic/developers/.")
    jurisdiction: str = Field("TH", min_length=2, max_length=2)
    buyer_kyc_tier: int = Field(3, ge=0, le=4)
    expires_in_seconds: int = Field(86_400, ge=60, le=7 * 86_400)

    @field_validator("deal_id", "buyer_wallet", "payee_wallet", "token_address")
    @classmethod
    def _must_be_hex(cls, value: str) -> str:
        if not value.startswith("0x"):
            raise ValueError("must be 0x-prefixed hex")
        try:
            int(value, 16)
        except ValueError as exc:  # pragma: no cover — pydantic surfaces
            raise ValueError("must be valid hex") from exc
        return value

    @field_validator("deal_id")
    @classmethod
    def _deal_id_length(cls, value: str) -> str:
        if len(value) != 66:
            raise ValueError("deal_id must be 32 bytes (66 hex chars incl. 0x prefix)")
        return value


class RuleResultPayload(BaseModel):
    rule_id: str
    passed: bool
    explanation: str


class TaintReportPayload(BaseModel):
    wallet: str
    capital_class: int
    signals: list[str]
    explanation: str


class AttestResponse(BaseModel):
    """POST /attest/settlement output."""

    decision: str
    deal_id: str
    capital_class: int
    payee_verified: bool
    reasons: list[str]
    rule_results: list[RuleResultPayload]
    taint: TaintReportPayload | None
    evidence_hash: str
    policy_pack_id: str
    policy_hash: str
    expires_at: int
    attestation_uid: str | None = None
    tx_hash: str | None = None
    block_number: int | None = None
    gas_used: int | None = None
    chain_id: int | None = None
    eas_explorer_url: str | None = None
    explanation: str


class AttesterHealthResponse(BaseModel):
    """GET /attest/healthz output."""

    status: str
    service: str
    repo_version: str | None = None
    policy_file: str | None = None
    dev_chain_reachable: bool | None = None
    rpc_url: str | None = None
    chain_id: int | None = None
    block_number: int | None = None
    eas_address: str | None = None
    schema_uid: str | None = None
    attester_address: str | None = None
    attester_balance_eth: float | None = None
    error: str | None = None


class AttestationLookupResponse(BaseModel):
    """GET /attest/{dealId} output (chain-side reader stub)."""

    deal_id: str
    attestation: dict[str, Any] | None = None
    note: str | None = None
