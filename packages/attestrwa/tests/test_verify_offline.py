import pytest

from attestrwa.verify import FAIL, PASS, SKIP, verify

from .conftest import clone, envelope_for


def _status(report, check_id):
    matches = [check for check in report.checks if check.id == check_id]
    assert matches, f"no check {check_id!r} in {[c.id for c in report.checks]}"
    return matches[0].status


def test_untouched_record_verifies_offline(approve_envelope, pack, registry) -> None:
    report = verify(approve_envelope, policy=pack, registry=registry)
    assert report.ok
    assert report.count(FAIL) == 0
    for check_id in (
        "record.structure",
        "record.hash",
        "record.inputs",
        "record.replay",
        "record.decision",
        "policy.match",
        "registry.match",
    ):
        assert _status(report, check_id) == PASS
    assert _status(report, "chain.network") == SKIP
    assert report.record_hash == approve_envelope["record_hash"]
    assert report.summary["decision"] == "approve"
    assert not report.anchored
    assert report.verdict == "CONSISTENT (not checked against the chain)"


def test_reject_record_verifies_and_names_the_failed_rule(reject_body, pack, registry) -> None:
    report = verify(envelope_for(reject_body), policy=pack, registry=registry)
    assert report.ok
    decision = next(c for c in report.checks if c.id == "record.decision")
    assert "REJECT" in decision.detail and "payee-is-registered" in decision.detail


def test_bare_record_body_is_accepted(approve_body) -> None:
    report = verify(approve_body)
    assert report.ok and _status(report, "record.hash") == PASS


def test_without_policy_and_registry_those_checks_are_skipped(approve_envelope) -> None:
    report = verify(approve_envelope)
    assert report.ok
    assert _status(report, "policy.match") == SKIP
    assert _status(report, "registry.match") == SKIP


def test_strict_mode_turns_skips_into_failure(approve_envelope, pack, registry) -> None:
    assert not verify(approve_envelope, strict=True).ok
    assert not verify(approve_envelope, policy=pack, registry=registry, strict=True).ok  # no RPC


def test_edited_body_no_longer_matches_the_stated_hash(approve_envelope) -> None:
    tampered = clone(approve_envelope)
    tampered["record"]["attester"]["software"] = "something-else/9.9"
    report = verify(tampered)
    assert not report.ok and _status(report, "record.hash") == FAIL


def test_flipped_input_is_caught_by_the_replay_even_if_the_hash_is_recomputed(approve_body):
    """An attacker who rewrites both the input and the envelope hash still fails replay."""
    tampered = clone(approve_body)
    tampered["inputs"][4]["value"] = "US"  # declared jurisdiction outside the policy
    report = verify(envelope_for(tampered))
    assert not report.ok
    assert _status(report, "record.hash") == PASS
    assert _status(report, "record.replay") == FAIL


def test_flipped_rule_result_is_caught(approve_body) -> None:
    tampered = clone(approve_body)
    tampered["rules"][0]["result"] = False
    report = verify(tampered)
    assert _status(report, "record.replay") == FAIL


def test_decision_that_does_not_follow_from_the_rules_is_caught(reject_body) -> None:
    tampered = clone(reject_body)
    tampered["decision"] = {"outcome": "approve", "code": 1, "failed_rules": []}
    report = verify(tampered)
    assert _status(report, "record.replay") == PASS
    assert _status(report, "record.decision") == FAIL


def test_rule_expression_swapped_for_a_weaker_one_fails_the_policy_check(approve_body, pack):
    tampered = clone(approve_body)
    tampered["rules"][3]["expression"] = "amount <= 999999999999999"
    report = verify(tampered, policy=pack)
    assert _status(report, "record.replay") == PASS
    assert _status(report, "policy.match") == FAIL


def test_wrong_policy_file_fails(approve_envelope, strict_pack) -> None:
    report = verify(approve_envelope, policy=strict_pack)
    assert not report.ok and _status(report, "policy.match") == FAIL


def test_input_moved_to_a_weaker_source_fails_the_policy_check(approve_body, pack) -> None:
    tampered = clone(approve_body)
    tampered["inputs"][2]["source"] = {"kind": "declared", "by": "buyer"}
    report = verify(tampered, policy=pack)
    assert _status(report, "policy.match") == FAIL


def test_input_that_contradicts_its_source_fails(approve_body) -> None:
    tampered = clone(approve_body)
    tampered["inputs"][3]["value"] = "1"
    report = verify(tampered)
    assert _status(report, "record.inputs") == FAIL


def test_registry_claim_is_rechecked_against_the_file(reject_body, registry) -> None:
    tampered = clone(reject_body)
    tampered["inputs"][0]["value"] = True  # claims the unregistered payee is registered
    tampered["rules"][0]["result"] = True
    tampered["decision"] = {"outcome": "approve", "code": 1, "failed_rules": []}
    report = verify(tampered, registry=registry)
    assert _status(report, "record.replay") == PASS
    assert _status(report, "registry.match") == FAIL


def test_registry_file_with_a_different_hash_fails(approve_body, registry) -> None:
    tampered = clone(approve_body)
    tampered["inputs"][0]["source"]["sha256"] = "0x" + "11" * 32
    report = verify(tampered, registry=registry)
    assert _status(report, "registry.match") == FAIL


def test_structurally_invalid_record_stops_early() -> None:
    report = verify({"record": {"spec": "nope"}})
    assert not report.ok
    assert [check.id for check in report.checks] == ["record.structure"]


def test_rule_with_disallowed_syntax_cannot_be_replayed(approve_body) -> None:
    tampered = clone(approve_body)
    tampered["rules"][0]["expression"] = "__import__('os').getcwd() == ''"
    report = verify(tampered)
    assert _status(report, "record.replay") == FAIL


@pytest.mark.parametrize(
    "document",
    [
        {"record": {}, "attestation": "x"},
        {"record": {}, "attestation": {"uid": 7}},
        {"record": {}, "record_hash": ["not", "a", "hash"]},
        {"record": None},
        {"record": []},
        {"record": "text"},
        [],
        "text",
        None,
        7,
    ],
)
def test_malformed_documents_fail_cleanly(document) -> None:
    report = verify(document)
    assert not report.ok
    assert [check.id for check in report.checks] == ["record.structure"]


def test_non_hex_uid_argument_fails_cleanly(approve_envelope) -> None:
    report = verify(approve_envelope, uid="x")
    assert not report.ok and _status(report, "record.structure") == FAIL


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b["decision"].__setitem__("outcome", ["approve"]),
        lambda b: b["decision"].__setitem__("outcome", {"a": 1}),
        lambda b: b["inputs"][0].__setitem__("type", ["bool"]),
        lambda b: b["inputs"][0]["source"].__setitem__("kind", ["registry"]),
        lambda b: b["inputs"][3]["source"].__setitem__("field", ["amount"]),
        lambda b: b["subject"].__setitem__("amount", "9" * 5000),
        lambda b: b["inputs"][3].__setitem__("value", "9" * 5000),
        lambda b: b["attester"].__setitem__("software", "lone surrogate \ud800"),
        lambda b: b["inputs"][4].__setitem__("value", "lone surrogate \ud800"),
        lambda b: b["rules"][0].__setitem__("id", "\ud800"),
        lambda b: b.__setitem__("inputs", {"not": "a list"}),
        lambda b: b.__setitem__("subject", "text"),
    ],
)
def test_hostile_values_inside_a_record_fail_cleanly(approve_body, mutation) -> None:
    """Untrusted records must never crash the verifier (they become HTTP 500s otherwise)."""
    tampered = clone(approve_body)
    mutation(tampered)
    report = verify(tampered)
    assert not report.ok
    assert report.checks[0].id == "record.structure" and report.checks[0].status == FAIL


def test_registry_lookup_of_another_address_fails_the_policy_check(approve_body, pack, registry):
    """Right rules, wrong facts: membership of some other registered address."""
    tampered = clone(approve_body)
    tampered["inputs"][0]["source"]["key"] = "0x976ea74026e726554db657fa54763abd0c3a0aa9"
    report = verify(tampered, policy=pack, registry=registry)
    assert _status(report, "registry.match") == PASS, "the other address is registered"
    assert _status(report, "policy.match") == FAIL


def test_sanctions_call_about_another_wallet_fails_the_policy_check(approve_body, pack) -> None:
    tampered = clone(approve_body)
    data = tampered["inputs"][1]["source"]["data"]
    tampered["inputs"][1]["source"]["data"] = data[:-40] + "11" * 20
    report = verify(tampered, policy=pack)
    assert _status(report, "record.inputs") == PASS
    assert _status(report, "policy.match") == FAIL


def test_sanctions_call_to_another_contract_fails_the_policy_check(approve_body, pack) -> None:
    tampered = clone(approve_body)
    tampered["inputs"][1]["source"]["to"] = "0x" + "22" * 20
    assert _status(verify(tampered, policy=pack), "policy.match") == FAIL


def test_amount_read_from_another_subject_field_fails_the_policy_check(approve_body, pack):
    tampered = clone(approve_body)
    tampered["inputs"][3]["source"]["field"] = "deadline"
    tampered["inputs"][3]["value"] = str(tampered["subject"]["deadline"])
    report = verify(tampered, policy=pack)
    assert _status(report, "record.inputs") == PASS
    assert _status(report, "policy.match") == FAIL


def test_chain_read_from_another_block_breaks_the_snapshot(approve_body) -> None:
    tampered = clone(approve_body)
    tampered["inputs"][1]["source"]["block_number"] -= 1000
    assert _status(verify(tampered), "record.inputs") == FAIL


def test_chain_read_from_another_chain_breaks_the_snapshot(approve_body) -> None:
    tampered = clone(approve_body)
    tampered["inputs"][2]["source"]["chain_id"] = 1
    assert _status(verify(tampered), "record.inputs") == FAIL


@pytest.mark.parametrize("offset", [-1, 86_400, 10**9])
def test_evaluation_outside_the_life_of_the_deal_is_rejected(approve_body, offset) -> None:
    tampered = clone(approve_body)
    tampered["evaluation"]["evaluated_at"] = tampered["subject"]["deposited_at"] + offset
    report = verify(tampered)
    assert _status(report, "record.structure") == FAIL


def test_registry_other_than_the_one_the_policy_names_fails(approve_envelope, pack) -> None:
    from attestrwa.registry import parse_registry

    from .conftest import REGISTRY_FILE

    other = parse_registry(REGISTRY_FILE.read_bytes().replace(b"demo-payees", b"other-payees"))
    report = verify(approve_envelope, policy=pack, registry=other)
    assert _status(report, "registry.match") == FAIL


def test_report_serialises(approve_envelope) -> None:
    data = verify(approve_envelope).to_dict()
    assert data["ok"] is True
    assert data["counts"][PASS] >= 5
    assert {"id", "group", "status", "detail"} <= set(data["checks"][0])
