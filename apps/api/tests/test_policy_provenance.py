"""Policy pack provenance — pack_id, policy_hash, evidence binding."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services.attester_service import (
    DealRequest,
    decide_for_deal,
    policy_provenance,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ASEAN_POLICY = REPO_ROOT / "data/policies/asean-property-settlement-v1.yaml"
DEFAULT_POLICY = REPO_ROOT / "data/synthetic/policies/default_attestrwa_policy.yaml"

BUYER_CLEAN = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
PAYEE_LANDMARK_OK = "0x976EA74026E726554dB657fA54763abd0C3a0aa9"
MOCK_USDC = "0xeba5CEc9257045Df0B44eA784F9a7Fa07DeeF6d4"


def _request(**overrides):
    base = {
        "deal_id": b"\xab" * 32,
        "buyer_wallet": BUYER_CLEAN,
        "payee_wallet": PAYEE_LANDMARK_OK,
        "token_address": MOCK_USDC,
        "amount_base_units": 580_000_000,
        "developer_id": "developer-bangkok-landmark",
        "jurisdiction": "TH",
        "buyer_kyc_tier": 3,
        "expires_in_seconds": 86_400,
    }
    base.update(overrides)
    return DealRequest(**base)


def test_policy_provenance_reads_pack_id_from_comment(monkeypatch) -> None:
    monkeypatch.setenv("ATTESTRWA_POLICY_FILE", str(ASEAN_POLICY))
    pack_id, policy_hash = policy_provenance()
    assert pack_id == "asean-property-settlement-v1"
    assert policy_hash.startswith("0x")
    assert len(policy_hash) == 66


def test_policy_hash_differs_between_packs(monkeypatch) -> None:
    monkeypatch.setenv("ATTESTRWA_POLICY_FILE", str(DEFAULT_POLICY))
    _, hash_default = policy_provenance()
    monkeypatch.setenv("ATTESTRWA_POLICY_FILE", str(ASEAN_POLICY))
    _, hash_asean = policy_provenance()
    assert hash_default != hash_asean


def test_decision_includes_policy_fields(monkeypatch) -> None:
    monkeypatch.setenv("ATTESTRWA_POLICY_FILE", str(ASEAN_POLICY))
    decision = decide_for_deal(_request())
    assert decision.policy_pack_id == "asean-property-settlement-v1"
    assert decision.policy_hash.startswith("0x")


def test_evidence_hash_changes_when_policy_changes(monkeypatch) -> None:
    monkeypatch.setenv("ATTESTRWA_POLICY_FILE", str(DEFAULT_POLICY))
    hash_default = decide_for_deal(_request()).evidence_hash
    monkeypatch.setenv("ATTESTRWA_POLICY_FILE", str(ASEAN_POLICY))
    hash_asean = decide_for_deal(_request()).evidence_hash
    assert hash_default != hash_asean
