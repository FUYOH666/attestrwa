"""Policy evolution — eligibility proofs change; escrow state is not mutated here."""

from __future__ import annotations

import os
from pathlib import Path

from app.services.attester_service import DealRequest, decide_for_deal

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_POLICY = REPO_ROOT / "data/synthetic/policies/default_attestrwa_policy.yaml"
ASEAN_POLICY = REPO_ROOT / "data/policies/asean-property-settlement-v1.yaml"
ASEAN_STRICT = REPO_ROOT / "data/policies/asean-property-settlement-v1-strict.yaml"

BUYER_CLEAN = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
PAYEE_LANDMARK_OK = "0x976EA74026E726554dB657fA54763abd0C3a0aa9"
MOCK_USDC = "0xeba5CEc9257045Df0B44eA784F9a7Fa07DeeF6d4"

# Borderline: SG deal above relaxed ASEAN cap, KYC tier 3 (passes v1, fails strict).
DEAL_ID = b"\xde\xad" * 16
BORDERLINE_AMOUNT = 600_000_000_000


def _borderline_request() -> DealRequest:
    return DealRequest(
        deal_id=DEAL_ID,
        buyer_wallet=BUYER_CLEAN,
        payee_wallet=PAYEE_LANDMARK_OK,
        token_address=MOCK_USDC,
        amount_base_units=BORDERLINE_AMOUNT,
        developer_id="developer-bangkok-landmark",
        jurisdiction="SG",
        buyer_kyc_tier=3,
        expires_in_seconds=86_400,
    )


def test_policy_evolution_approve_then_reject_without_escrow_mutation(monkeypatch) -> None:
    """Same deal context: relaxed pack approves, strict pack rejects; hashes differ."""
    monkeypatch.setenv("ATTESTRWA_POLICY_FILE", str(ASEAN_POLICY))
    first = decide_for_deal(_borderline_request())
    assert first.decision == "approve"
    assert first.policy_pack_id == "asean-property-settlement-v1"

    monkeypatch.setenv("ATTESTRWA_POLICY_FILE", str(ASEAN_STRICT))
    second = decide_for_deal(_borderline_request())
    assert second.decision == "reject"
    assert second.policy_pack_id == "asean-property-settlement-v1-strict"
    assert first.policy_hash != second.policy_hash
    assert first.evidence_hash != second.evidence_hash


def test_jurisdiction_pack_swap_default_to_asean(monkeypatch) -> None:
    """AE allowed in default pack; ASEAN pack rejects — proof migration path."""
    req = DealRequest(
        deal_id=DEAL_ID,
        buyer_wallet=BUYER_CLEAN,
        payee_wallet=PAYEE_LANDMARK_OK,
        token_address=MOCK_USDC,
        amount_base_units=580_000_000,
        developer_id="developer-bangkok-landmark",
        jurisdiction="AE",
        buyer_kyc_tier=3,
        expires_in_seconds=86_400,
    )
    monkeypatch.setenv("ATTESTRWA_POLICY_FILE", str(DEFAULT_POLICY))
    assert decide_for_deal(req).decision == "approve"

    monkeypatch.setenv("ATTESTRWA_POLICY_FILE", str(ASEAN_POLICY))
    assert decide_for_deal(req).decision == "reject"
