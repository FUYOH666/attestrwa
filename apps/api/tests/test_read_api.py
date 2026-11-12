"""Read routes: records, decision lookup, verification, readiness."""

from __future__ import annotations

import copy
import json

import pytest

from .conftest import ATTESTER, ESCROW, IMPOSTOR, attest


def test_record_is_served_by_deal_and_by_hash(client, chain) -> None:
    deal_id = chain.open_deal()
    made = attest(client, deal_id).json()

    by_deal = client.get(f"/records/{deal_id}")
    by_hash = client.get(f"/records/by-hash/{made['record_hash']}")
    assert by_deal.status_code == by_hash.status_code == 200
    assert by_deal.json() == by_hash.json() == made["envelope"]


def test_unknown_record_is_404_and_bad_ids_are_422(client) -> None:
    assert client.get("/records/0x" + "ab" * 32).status_code == 404
    assert client.get("/records/by-hash/0x" + "ab" * 32).status_code == 404
    assert client.get("/records/nope").status_code == 422
    assert client.get("/records/by-hash/..%2F..%2Fetc").status_code in (404, 422)
    assert client.get("/attest/nope").status_code == 422


def test_uppercase_ids_are_normalised(client, chain) -> None:
    deal_id = chain.open_deal()
    attest(client, deal_id)
    assert client.get(f"/records/0x{deal_id[2:].upper()}").status_code == 200


def test_lookup_reports_live_onchain_state(client, chain) -> None:
    deal_id = chain.open_deal(payee=IMPOSTOR)
    uid = attest(client, deal_id).json()["attestation_uid"]

    lookup = client.get(f"/attest/{deal_id}").json()
    assert lookup["deal_status"] == "open"
    assert lookup["decisions"] == [
        {
            "attestation_uid": uid,
            "record_hash": lookup["decisions"][0]["record_hash"],
            "decision": "reject",
            "on_chain": True,
            "attester": ATTESTER,
            "time": chain.attestations[uid]["time"],
            "expiration_time": chain.attestations[uid]["expiration_time"],
            "revoked": False,
            "decision_code": 2,
        }
    ]

    chain.revoke(uid)
    chain.deals[deal_id]["status"] = 3
    lookup = client.get(f"/attest/{deal_id}").json()
    assert lookup["deal_status"] == "refunded"
    assert lookup["decisions"][0]["revoked"] is True


def test_lookup_for_a_deal_without_decisions_is_empty(client, chain) -> None:
    deal_id = chain.open_deal()
    assert client.get(f"/attest/{deal_id}").json() == {
        "deal_id": deal_id,
        "deal_status": "open",
        "decisions": [],
    }


def test_verify_endpoint_confirms_an_issued_record(client, chain) -> None:
    envelope = attest(client, chain.open_deal()).json()["envelope"]
    report = client.post("/verify", json=envelope).json()

    assert report["ok"] is True and report["anchored"] is True
    assert report["verdict"] == "VERIFIED"
    assert report["counts"] == {"pass": report["counts"]["pass"], "fail": 0, "skip": 0}


def test_verify_endpoint_rejects_an_edited_record(client, chain) -> None:
    envelope = attest(client, chain.open_deal()).json()["envelope"]
    edited = copy.deepcopy(envelope)
    edited["record"]["inputs"][4]["value"] = "SG"
    report = client.post("/verify", json=edited).json()

    assert report["ok"] is False and report["verdict"] == "NOT VERIFIED"
    failed = {check["id"] for check in report["checks"] if check["status"] == "fail"}
    assert {"record.hash", "attestation.record_hash"} <= failed


def test_verify_endpoint_handles_garbage(client) -> None:
    report = client.post("/verify", json={"record": {"spec": "nope"}}).json()
    assert report["ok"] is False
    assert [check["id"] for check in report["checks"]] == ["record.structure"]


@pytest.mark.parametrize(
    "document",
    [
        {"record": {}, "attestation": "x"},
        {"record": {"decision": {"outcome": ["approve"]}}},
        {"record": None, "record_hash": 7},
        [],
        "text",
    ],
)
def test_verify_endpoint_never_answers_500_on_malformed_documents(client, document) -> None:
    response = client.post("/verify", json=document)
    assert response.status_code == 200
    assert response.json()["ok"] is False


def test_verify_endpoint_refuses_duplicate_keys(client, chain) -> None:
    """An HTTP parser would keep the last duplicate; the record would be ambiguous."""
    envelope = attest(client, chain.open_deal()).json()["envelope"]
    text = json.dumps(envelope).replace(
        '"outcome": "approve"', '"outcome": "reject", "outcome": "approve"', 1
    )
    assert '"outcome": "reject", "outcome": "approve"' in text

    response = client.post("/verify", content=text, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "duplicate" in response.json()["detail"]


@pytest.mark.parametrize("body", [b"{not json", b'{"record": {"x": 1.5}}', b"\xff\xfe"])
def test_verify_endpoint_refuses_unparseable_bodies(client, body: bytes) -> None:
    response = client.post("/verify", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422


def test_verify_endpoint_refuses_oversized_bodies(client) -> None:
    response = client.post(
        "/verify", content=b" " * (256 * 1024 + 1), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


def test_readiness_reports_wiring(client, chain, service) -> None:
    health = client.get("/attest/healthz").json()
    assert health["status"] == "ok"
    assert health["escrow"] == ESCROW and health["attester"] == ATTESTER
    assert health["attester_trusted"] is True and health["escrow_schema_matches"] is True
    assert health["policy"] == {
        "pack_id": "settlement-demo",
        "version": "2.0.0",
        "sha256": service.pack.sha256,
    }
    assert "rpc_url" not in health and "private" not in str(health).lower()


def test_readiness_is_degraded_when_the_escrow_does_not_trust_the_attester(client, chain):
    chain.trusted.clear()
    health = client.get("/attest/healthz").json()
    assert health["status"] == "degraded" and health["attester_trusted"] is False


def test_readiness_is_degraded_when_the_escrow_uses_another_schema(client, chain) -> None:
    chain.escrow_schema = b"\x01" * 32
    assert client.get("/attest/healthz").json()["status"] == "degraded"
