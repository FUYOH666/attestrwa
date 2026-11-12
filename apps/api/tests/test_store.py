import pytest

from app.store import RecordStore

DEAL = "0x" + "d1" * 32


def _envelope(n: int, decision: str = "approve") -> dict:
    return {
        "record": {"subject": {"deal_id": DEAL}, "decision": {"outcome": decision}},
        "record_hash": "0x" + f"{n:02x}" * 32,
        "attestation": {"uid": "0x" + f"{n + 16:02x}" * 32},
    }


def test_store_round_trip_and_history_order(tmp_path) -> None:
    store = RecordStore(tmp_path)
    assert store.latest(DEAL) is None and store.history(DEAL) == []

    store.save(_envelope(1, "reject"))
    store.save(_envelope(2, "approve"))

    assert store.latest(DEAL) == _envelope(2)
    assert store.by_hash("0x" + "01" * 32) == _envelope(1, "reject")
    assert [entry["decision"] for entry in store.history(DEAL)] == ["reject", "approve"]
    assert not list(tmp_path.rglob("*.tmp"))


def test_store_survives_a_restart(tmp_path) -> None:
    RecordStore(tmp_path).save(_envelope(1))
    assert RecordStore(tmp_path).latest(DEAL) == _envelope(1)


@pytest.mark.parametrize(
    "key", ["../../etc/passwd", "0x1234", "0x" + "AB" * 32, "", "0x" + "g" * 64]
)
def test_store_refuses_keys_that_are_not_bytes32(tmp_path, key) -> None:
    store = RecordStore(tmp_path)
    with pytest.raises(ValueError):
        store.by_hash(key)
    with pytest.raises(ValueError):
        store.history(key)
