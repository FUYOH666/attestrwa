"""Request and response models of the attester API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _lower_hex(value: str, digits: int, what: str) -> str:
    text = value.lower()
    if not text.startswith("0x") or len(text) != 2 + digits:
        raise ValueError(f"{what} must be 0x followed by {digits} hex digits")
    try:
        int(text, 16)
    except ValueError as exc:
        raise ValueError(f"{what} must be hex") from exc
    return text


class AttestRequest(BaseModel):
    """``POST /attest/settlement``. The deal is named, never described."""

    model_config = ConfigDict(extra="forbid")

    chain_id: int = Field(..., description="Chain the escrow lives on.")
    escrow: str = Field(..., description="Escrow contract address.")
    deal_id: str = Field(..., description="32-byte deal identifier returned by deposit().")
    declared: dict[str, bool | int | str] = Field(
        default_factory=dict,
        description="Values for the inputs the policy accepts as declarations.",
    )

    @field_validator("escrow")
    @classmethod
    def _escrow(cls, value: str) -> str:
        return _lower_hex(value, 40, "escrow")

    @field_validator("deal_id")
    @classmethod
    def _deal_id(cls, value: str) -> str:
        return _lower_hex(value, 64, "deal_id")


class AttestResponse(BaseModel):
    deal_id: str
    decision: str
    decision_code: int
    failed_rules: list[str]
    record_hash: str
    attestation_uid: str
    tx_hash: str | None
    reused: bool = Field(
        ..., description="True when a live decision already existed and was returned."
    )
    envelope: dict[str, Any] = Field(..., description="The decision record file.")


class ErrorResponse(BaseModel):
    detail: str
