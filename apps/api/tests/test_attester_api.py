"""HTTP tests for the attester endpoints. On-chain submission is best-effort;
when the EAS RPC is unreachable, the endpoint returns the decision payload
without `attestation_uid` (logged as a warning).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


VALID_BODY = {
    "deal_id": "0x" + "ab" * 32,
    "buyer_wallet": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    "payee_wallet": "0x976EA74026E726554dB657fA54763abd0C3a0aa9",
    "token_address": "0xeba5CEc9257045Df0B44eA784F9a7Fa07DeeF6d4",
    "amount_base_units": 580_000_000,
    "developer_id": "developer-bangkok-landmark",
    "jurisdiction": "TH",
    "buyer_kyc_tier": 3,
    "expires_in_seconds": 86_400,
}


def test_attest_happy_body() -> None:
    response = client.post("/attest/settlement", json=VALID_BODY)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "approve"
    assert body["payee_verified"] is True
    assert body["capital_class"] == 0
    assert body["reasons"] == []
    assert body["evidence_hash"].startswith("0x")
    assert body["policy_pack_id"]
    assert body["policy_hash"].startswith("0x")
    assert "rule_results" in body and len(body["rule_results"]) > 0


def test_attest_payee_mismatch_reject() -> None:
    payload = {
        **VALID_BODY,
        "developer_id": "siam-riverside-living",
        "payee_wallet": "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
    }
    response = client.post("/attest/settlement", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "reject"
    assert body["payee_verified"] is False
    assert any("authorized_payee_wallets" in r for r in body["reasons"])


def test_attest_invalid_deal_id_format() -> None:
    payload = {**VALID_BODY, "deal_id": "0xdeadbeef"}
    response = client.post("/attest/settlement", json=payload)
    assert response.status_code == 422


def test_attest_unknown_developer_id_returns_400() -> None:
    payload = {**VALID_BODY, "developer_id": "developer-not-real"}
    response = client.post("/attest/settlement", json=payload)
    assert response.status_code == 400


def test_attest_healthz_responds() -> None:
    response = client.get("/attest/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body.get("service") == "attestrwa-attester"
    assert "policy_file" in body
    assert "repo_version" in body
    assert "dev_chain_reachable" in body
    assert body.get("status") in {"ok", "down"}


def test_attest_lookup_placeholder() -> None:
    response = client.get("/attest/0xabcd")
    assert response.status_code == 200
    body = response.json()
    assert body["attestation"] is None
    assert "indexer" in body["note"]
