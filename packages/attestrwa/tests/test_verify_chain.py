import pytest

from attestrwa.eas import DecisionData, decode_decision, encode_decision
from attestrwa.rpc import RpcError, decode_attestation, decode_deal
from attestrwa.verify import FAIL, PASS, SKIP, verify

from .conftest import ESCROW, UID, FakeChain, encode_attestation, envelope_for, make_body


def _status(report, check_id):
    matches = [check for check in report.checks if check.id == check_id]
    assert matches, f"no check {check_id!r} in {[c.id for c in report.checks]}"
    return matches[0].status


def _replace(chain: FakeChain, **changes) -> None:
    data = decode_decision(chain.attestation["data"])
    fields = {name: getattr(data, name) for name in DecisionData.__slots__}
    fields.update(changes)
    chain.attestation["data"] = encode_decision(DecisionData(**fields))


ONCHAIN_CHECKS = (
    "chain.network",
    "attestation.exists",
    "attestation.schema",
    "attestation.record_hash",
    "attestation.policy_hash",
    "attestation.deal",
    "attestation.decision",
    "attestation.recipient",
    "attestation.attester",
    "attestation.not_revoked",
    "attestation.time",
    "attestation.supersedes",
    "evaluation.block",
    "escrow.config",
    "escrow.deal",
    "escrow.attester_trusted",
)


def test_record_verifies_against_the_chain(approve_envelope, chain, pack, registry) -> None:
    report = verify(approve_envelope, rpc=chain, policy=pack, registry=registry)
    assert report.ok
    for check_id in ONCHAIN_CHECKS:
        assert _status(report, check_id) == PASS, check_id
    assert _status(report, "inputs.onchain") == SKIP
    assert report.summary["deal_status"] == "open"
    assert report.summary["attestation_uid"] == UID
    assert report.anchored and report.verdict == "VERIFIED"


def test_fully_checked_record_passes_strict_mode(approve_envelope, chain, pack, registry) -> None:
    report = verify(
        approve_envelope,
        rpc=chain,
        policy=pack,
        registry=registry,
        recheck_inputs=True,
        strict=True,
    )
    assert report.ok and report.count(SKIP) == 0
    assert _status(report, "inputs.onchain") == PASS


def test_core_checks_use_state_reads_at_latest_only(approve_envelope, chain) -> None:
    verify(approve_envelope, rpc=chain)
    assert chain.calls and all(block == "latest" for _, _, block in chain.calls)


def test_reject_record_verifies_against_the_chain(reject_body) -> None:
    report = verify(envelope_for(reject_body), rpc=FakeChain(reject_body))
    assert report.ok
    assert _status(report, "attestation.decision") == PASS


def test_uid_argument_overrides_the_envelope(approve_envelope, chain) -> None:
    other = "0x" + "c3" * 32
    report = verify(approve_envelope, rpc=chain, uid=other)
    assert _status(report, "attestation.exists") == FAIL


def test_missing_uid_fails(approve_body, chain) -> None:
    report = verify(approve_body, rpc=chain)
    assert not report.ok and _status(report, "attestation.exists") == FAIL


def test_wrong_network_fails_before_any_contract_read(approve_envelope, chain) -> None:
    chain.chain = 8453
    report = verify(approve_envelope, rpc=chain)
    assert _status(report, "chain.network") == FAIL
    assert chain.calls == []


def test_record_anchored_to_another_schema_fails(approve_envelope, chain) -> None:
    approve_envelope["record"]["anchor"]["schema_uid"] = "0x" + "12" * 32
    report = verify(approve_envelope, rpc=chain)
    assert _status(report, "attestation.schema") == FAIL


def test_attestation_under_another_schema_fails(approve_envelope, chain) -> None:
    chain.attestation["schema"] = "0x" + "12" * 32
    assert _status(verify(approve_envelope, rpc=chain), "attestation.schema") == FAIL


def test_malformed_attestation_data_fails(approve_envelope, chain) -> None:
    chain.attestation["data"] = chain.attestation["data"][:-32]
    assert _status(verify(approve_envelope, rpc=chain), "attestation.data") == FAIL


def test_attestation_committing_to_another_record_fails(approve_envelope, chain) -> None:
    _replace(chain, record_hash=b"\x99" * 32)
    assert _status(verify(approve_envelope, rpc=chain), "attestation.record_hash") == FAIL


def test_edited_record_no_longer_matches_the_onchain_commitment(approve_body, chain) -> None:
    approve_body["attester"]["software"] = "edited/1.0"
    report = verify(envelope_for(approve_body), rpc=chain)
    assert _status(report, "record.hash") == PASS
    assert _status(report, "attestation.record_hash") == FAIL


def test_policy_hash_mismatch_fails(approve_envelope, chain) -> None:
    _replace(chain, policy_hash=b"\x77" * 32)
    assert _status(verify(approve_envelope, rpc=chain), "attestation.policy_hash") == FAIL


@pytest.mark.parametrize(
    "changes",
    [
        {"deal_id": b"\x01" * 32},
        {"payee": "0x" + "02" * 20},
        {"token": "0x" + "03" * 20},
        {"amount": 1},
    ],
)
def test_attestation_about_a_different_deal_fails(approve_envelope, chain, changes) -> None:
    _replace(chain, **changes)
    assert _status(verify(approve_envelope, rpc=chain), "attestation.deal") == FAIL


def test_decision_mismatch_fails(approve_envelope, chain) -> None:
    _replace(chain, decision=2)
    assert _status(verify(approve_envelope, rpc=chain), "attestation.decision") == FAIL


def test_attestation_addressed_elsewhere_fails(approve_envelope, chain) -> None:
    chain.attestation["recipient"] = "0x" + "04" * 20
    assert _status(verify(approve_envelope, rpc=chain), "attestation.recipient") == FAIL


def test_attestation_by_someone_else_fails(approve_envelope, chain) -> None:
    chain.attestation["attester"] = "0x" + "05" * 20
    report = verify(approve_envelope, rpc=chain)
    assert _status(report, "attestation.attester") == FAIL
    assert _status(report, "escrow.attester_trusted") == FAIL


def test_revoked_attestation_fails(approve_envelope, chain) -> None:
    chain.attestation["revocation_time"] = chain.attestation["time"] + 10
    assert _status(verify(approve_envelope, rpc=chain), "attestation.not_revoked") == FAIL


def test_attestation_older_than_the_deposit_fails(approve_envelope, chain) -> None:
    chain.attestation["time"] = approve_envelope["record"]["subject"]["deposited_at"] - 1
    assert _status(verify(approve_envelope, rpc=chain), "attestation.time") == FAIL


def test_attestation_older_than_the_claimed_evaluation_fails(approve_envelope, chain) -> None:
    """Inputs from one moment cannot be passed off as a later evaluation."""
    chain.attestation["time"] = approve_envelope["record"]["evaluation"]["evaluated_at"] - 1
    assert _status(verify(approve_envelope, rpc=chain), "attestation.time") == FAIL


def test_evaluation_time_must_be_the_timestamp_of_the_evaluation_block(approve_envelope, chain):
    block = approve_envelope["record"]["evaluation"]["block_number"]
    chain.block_times[block] += 5
    assert _status(verify(approve_envelope, rpc=chain), "evaluation.block") == FAIL


def test_unavailable_evaluation_block_is_skipped_not_failed(approve_envelope, chain) -> None:
    chain.block_times.clear()
    report = verify(approve_envelope, rpc=chain)
    assert _status(report, "evaluation.block") == SKIP and report.ok


def test_supersedes_must_match_the_attestation_reference(pack, registry) -> None:
    earlier = "0x" + "5e" * 32
    body = make_body(pack, registry, supersedes=earlier)

    honest = FakeChain(body)
    honest.attestation["ref_uid"] = earlier
    assert _status(verify(envelope_for(body), rpc=honest), "attestation.supersedes") == PASS

    unrelated = FakeChain(body)  # refUID stays zero
    assert _status(verify(envelope_for(body), rpc=unrelated), "attestation.supersedes") == FAIL


def test_attestation_referencing_something_the_record_does_not_name_fails(approve_envelope, chain):
    chain.attestation["ref_uid"] = "0x" + "5e" * 32
    assert _status(verify(approve_envelope, rpc=chain), "attestation.supersedes") == FAIL


def test_escrow_wired_to_another_schema_fails(approve_envelope, chain) -> None:
    chain.escrow_schema = "0x" + "06" * 32
    assert _status(verify(approve_envelope, rpc=chain), "escrow.config") == FAIL


def test_unknown_deal_fails(approve_envelope, chain) -> None:
    chain.deal["status"] = 0
    assert _status(verify(approve_envelope, rpc=chain), "escrow.deal") == FAIL


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("buyer", "0x" + "07" * 20),
        ("payee", "0x" + "08" * 20),
        ("token", "0x" + "09" * 20),
        ("amount", 1),
        ("deadline", 5),
        ("deposited_at", 5),
    ],
)
def test_escrow_deal_that_differs_from_the_record_fails(approve_envelope, chain, field, value):
    chain.deal[field] = value
    assert _status(verify(approve_envelope, rpc=chain), "escrow.deal") == FAIL


def test_settled_deal_still_verifies(approve_envelope, chain) -> None:
    chain.deal["status"] = 2
    report = verify(approve_envelope, rpc=chain)
    assert report.ok and report.summary["deal_status"] == "released"


def test_attester_no_longer_trusted_fails(approve_envelope, chain) -> None:
    chain.trusted.clear()
    assert _status(verify(approve_envelope, rpc=chain), "escrow.attester_trusted") == FAIL


def test_recheck_detects_an_input_the_chain_contradicts(approve_envelope, chain) -> None:
    chain.sanctioned.add(approve_envelope["record"]["subject"]["payee"])
    report = verify(approve_envelope, rpc=chain, recheck_inputs=True)
    assert _status(report, "inputs.onchain") == FAIL


def test_recheck_uses_the_recorded_block(approve_envelope, chain) -> None:
    verify(approve_envelope, rpc=chain, recheck_inputs=True)
    blocks = {block for to, _, block in chain.calls if to != ESCROW and isinstance(block, int)}
    assert blocks == {approve_envelope["record"]["evaluation"]["block_number"]}


def test_pruned_history_is_reported_as_unverifiable_not_as_a_mismatch(approve_envelope, chain):
    chain.history_available = False
    report = verify(approve_envelope, rpc=chain, recheck_inputs=True)
    assert _status(report, "inputs.onchain") == SKIP
    assert report.ok
    assert not verify(approve_envelope, rpc=chain, recheck_inputs=True, strict=True).ok


def test_attestation_decoding_round_trips(chain) -> None:
    decoded = decode_attestation(encode_attestation(chain.attestation))
    assert decoded.exists and decoded.revocable
    assert decoded.recipient == chain.attestation["recipient"]
    assert decoded.data == chain.attestation["data"]
    assert decoded.time == chain.attestation["time"]


@pytest.mark.parametrize("raw", [b"", b"\x00" * 64, b"\x00" * 31])
def test_truncated_attestation_is_an_rpc_error(raw: bytes) -> None:
    with pytest.raises(RpcError):
        decode_attestation(raw)


def test_truncated_deal_is_an_rpc_error() -> None:
    with pytest.raises(RpcError):
        decode_deal(b"\x00" * 100)
