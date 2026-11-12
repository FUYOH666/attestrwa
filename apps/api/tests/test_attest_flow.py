"""POST /attest/settlement: the decision, its record and its anchor."""

from __future__ import annotations

import pytest
from attestrwa.eas import decode_decision
from attestrwa.verify import verify

from .conftest import (
    API_KEY,
    ATTESTER,
    BUYER,
    CHAIN_ID,
    ESCROW,
    IMPOSTOR,
    PAYEE,
    TOKEN,
    attest,
)


def _fully_verified(service, envelope) -> bool:
    report = verify(
        envelope,
        rpc=service.rpc,
        policy=service.pack,
        registry=service.registry,
        recheck_inputs=True,
        strict=True,
    )
    return report.ok and report.anchored


def test_registered_payee_is_approved_and_the_record_verifies(client, chain, service) -> None:
    deal_id = chain.open_deal()
    response = attest(client, deal_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "approve" and body["decision_code"] == 1
    assert body["failed_rules"] == [] and body["reused"] is False
    assert _fully_verified(service, body["envelope"])

    on_chain = chain.attestations[body["attestation_uid"]]
    data = decode_decision(on_chain["data"])
    assert on_chain["recipient"] == ESCROW
    assert (data.payee, data.token, data.amount, data.decision) == (PAYEE, TOKEN, 580_000_000, 1)
    assert "0x" + data.record_hash.hex() == body["record_hash"]
    assert "0x" + data.policy_hash.hex() == service.pack.sha256


def test_the_record_describes_the_deal_as_the_escrow_holds_it(client, chain) -> None:
    deal_id = chain.open_deal(amount=123_456_789)
    record = attest(client, deal_id).json()["envelope"]["record"]
    deal = chain.deals[deal_id]

    assert record["subject"] == {
        "kind": "escrow_deal",
        "chain_id": CHAIN_ID,
        "escrow": ESCROW,
        "deal_id": deal_id,
        "buyer": BUYER,
        "payee": PAYEE,
        "token": TOKEN,
        "amount": "123456789",
        "deadline": deal["deadline"],
        "deposited_at": deal["deposited_at"],
    }
    assert record["attester"]["address"] == ATTESTER
    sources = {item["name"]: item["source"]["kind"] for item in record["inputs"]}
    assert sources == {
        "payee_registered": "registry",
        "payee_sanctioned": "onchain",
        "buyer_sanctioned": "onchain",
        "amount": "subject",
        "jurisdiction": "declared",
    }
    declared = next(i for i in record["inputs"] if i["name"] == "jurisdiction")
    assert declared["source"]["by"] == "integrator:demo-integrator"
    onchain = next(i for i in record["inputs"] if i["name"] == "payee_sanctioned")
    assert onchain["source"]["block_number"] == record["evaluation"]["block_number"]


def test_unregistered_payee_is_rejected_with_the_failing_rule(client, chain, service) -> None:
    deal_id = chain.open_deal(payee=IMPOSTOR)
    body = attest(client, deal_id).json()

    assert body["decision"] == "reject" and body["decision_code"] == 2
    assert body["failed_rules"] == ["payee-is-registered"]
    assert decode_decision(chain.attestations[body["attestation_uid"]]["data"]).decision == 2
    assert _fully_verified(service, body["envelope"])


@pytest.mark.parametrize(
    ("party", "rule"),
    [(PAYEE, "payee-not-sanctioned"), (BUYER, "buyer-not-sanctioned")],
)
def test_sanctioned_party_is_rejected_from_the_oracle_reading(client, chain, party, rule) -> None:
    chain.sanctioned.add(party)
    body = attest(client, chain.open_deal()).json()
    assert body["decision"] == "reject" and body["failed_rules"] == [rule]


def test_amount_over_the_policy_limit_is_rejected(client, chain) -> None:
    body = attest(client, chain.open_deal(amount=1_000_000_000_001)).json()
    assert body["failed_rules"] == ["amount-within-limit"]


def test_declared_jurisdiction_outside_the_policy_is_rejected(client, chain) -> None:
    body = attest(client, chain.open_deal(), declared={"jurisdiction": "US"}).json()
    assert body["decision"] == "reject" and body["failed_rules"] == ["supported-jurisdiction"]


# ---- the caller cannot describe the deal -----------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        {"payee_wallet": IMPOSTOR},
        {"buyer_wallet": "0x" + "01" * 20},
        {"amount_base_units": 1},
        {"buyer_kyc_tier": 4},
        {"token_address": TOKEN},
    ],
)
def test_request_fields_describing_the_deal_are_refused(client, chain, extra) -> None:
    deal_id = chain.open_deal()
    response = attest(client, deal_id, **extra)
    assert response.status_code == 422
    assert chain.attestations == {}


@pytest.mark.parametrize(
    "declared",
    [
        {"jurisdiction": "TH", "buyer_sanctioned": False},
        {"jurisdiction": "TH", "payee_registered": True},
        {"jurisdiction": "TH", "amount": 1},
        {"jurisdiction": "TH", "made_up": "x"},
    ],
)
def test_inputs_the_policy_takes_from_elsewhere_cannot_be_declared(client, chain, declared):
    """Screening bypass attempt: declare a value the policy reads from the chain."""
    chain.sanctioned.add(BUYER)
    response = attest(client, chain.open_deal(), declared=declared)
    assert response.status_code == 422
    assert "cannot be declared" in response.json()["detail"]
    assert chain.attestations == {}


@pytest.mark.parametrize("declared", [{}, {"jurisdiction": 7}, {"jurisdiction": ""}])
def test_missing_or_mistyped_declaration_is_refused(client, chain, declared) -> None:
    response = attest(client, chain.open_deal(), declared=declared)
    assert response.status_code == 422
    assert chain.attestations == {}


def test_self_serve_rejection_is_not_possible(client, chain) -> None:
    """A buyer cannot steer the decision: for an honest deal the answer is APPROVE
    whatever the request body says about the payee."""
    deal_id = chain.open_deal()
    assert attest(client, deal_id, payee_wallet=IMPOSTOR).status_code == 422
    assert attest(client, deal_id).json()["decision"] == "approve"


# ---- authentication and targeting ------------------------------------------


@pytest.mark.parametrize("key", [None, "", "wrong-key", API_KEY + "x"])
def test_write_route_needs_a_valid_api_key(client, chain, key) -> None:
    headers = {} if key is None else {"X-API-Key": key}
    response = client.post(
        "/attest/settlement",
        json={"chain_id": CHAIN_ID, "escrow": ESCROW, "deal_id": chain.open_deal()},
        headers=headers,
    )
    assert response.status_code == 401
    assert chain.attestations == {}


def test_attester_without_configured_keys_refuses_everyone(client, chain, settings) -> None:
    settings.api_keys = ""
    assert attest(client, chain.open_deal()).status_code == 503


@pytest.mark.parametrize("overrides", [{"chain_id": 8453}, {"escrow": "0x" + "99" * 20}])
def test_another_escrow_or_chain_is_refused(client, chain, overrides) -> None:
    response = attest(client, chain.open_deal(), **overrides)
    assert response.status_code == 422
    assert "this attester serves" in response.json()["detail"]


@pytest.mark.parametrize("deal_id", ["0x1234", "not-hex", "0x" + "zz" * 32])
def test_malformed_deal_id_is_refused(client, deal_id) -> None:
    assert attest(client, deal_id).status_code == 422


# ---- deal state -------------------------------------------------------------


def test_unknown_deal_is_404(client) -> None:
    response = attest(client, "0x" + "12" * 32)
    assert response.status_code == 404


@pytest.mark.parametrize("status", [2, 3])
def test_settled_deal_is_409(client, chain, status) -> None:
    deal_id = chain.open_deal()
    chain.deals[deal_id]["status"] = status
    assert attest(client, deal_id).status_code == 409
    assert chain.attestations == {}


def test_deal_at_its_deadline_is_409(client, chain) -> None:
    deal_id = chain.open_deal(lifetime=20)
    assert attest(client, deal_id).status_code == 409


def test_attestation_expiry_never_outlives_the_deadline(client, chain, settings) -> None:
    settings.attestation_ttl_seconds = 30 * 86_400
    deal_id = chain.open_deal(lifetime=3_600)
    uid = attest(client, deal_id).json()["attestation_uid"]
    assert chain.attestations[uid]["expiration_time"] == chain.deals[deal_id]["deadline"]


def test_short_ttl_expires_before_the_deadline(client, chain, settings) -> None:
    settings.attestation_ttl_seconds = 600
    deal_id = chain.open_deal(lifetime=86_400)
    uid = attest(client, deal_id).json()["attestation_uid"]
    assert chain.attestations[uid]["expiration_time"] < chain.deals[deal_id]["deadline"]


# ---- one live decision per deal ---------------------------------------------


def test_repeat_request_returns_the_stored_decision(client, chain) -> None:
    deal_id = chain.open_deal()
    first = attest(client, deal_id).json()
    second = attest(client, deal_id, declared={"jurisdiction": "US"}).json()

    assert second["reused"] is True
    assert second["attestation_uid"] == first["attestation_uid"]
    assert second["decision"] == "approve", "a later request cannot flip a live decision"
    assert len(chain.attestations) == 1


def test_new_decision_only_after_revocation_and_it_names_what_it_replaces(client, chain, service):
    deal_id = chain.open_deal(payee=IMPOSTOR)
    first = attest(client, deal_id).json()
    assert first["decision"] == "reject"

    chain.revoke(first["attestation_uid"])
    chain.deals[deal_id]["payee"] = PAYEE  # stands in for "the facts changed"
    second = attest(client, deal_id).json()

    assert second["reused"] is False and second["decision"] == "approve"
    assert second["envelope"]["record"]["supersedes"] == first["attestation_uid"]
    assert chain.attestations[second["attestation_uid"]]["ref_uid"] == first["attestation_uid"]
    assert [d["decision"] for d in service.store.history(deal_id)] == ["reject", "approve"]


def test_record_from_a_reset_chain_does_not_block_a_new_decision(client, chain) -> None:
    deal_id = chain.open_deal()
    first = attest(client, deal_id).json()
    chain.attestations.clear()

    second = attest(client, deal_id).json()
    assert first["reused"] is False and second["reused"] is False
    assert second["envelope"]["record"]["supersedes"] is None
    assert list(chain.attestations) == [second["attestation_uid"]]


# ---- fail closed -------------------------------------------------------------


def test_unreadable_screening_source_makes_no_decision(client, chain) -> None:
    chain.oracle_down = True
    deal_id = chain.open_deal()
    response = attest(client, deal_id)

    assert response.status_code == 502
    assert "sanctions oracle" in response.json()["detail"]
    assert chain.attestations == {}
    assert client.get(f"/records/{deal_id}").status_code == 404


def test_failed_transaction_is_an_error_not_a_decision(client, chain) -> None:
    chain.attest_down = True
    deal_id = chain.open_deal()
    response = attest(client, deal_id)

    assert response.status_code == 502
    assert client.get(f"/records/{deal_id}").status_code == 404

    chain.attest_down = False
    assert attest(client, deal_id).status_code == 200


def test_instance_without_a_key_cannot_attest(client, chain, service) -> None:
    service.signer = None
    assert attest(client, chain.open_deal()).status_code == 503
