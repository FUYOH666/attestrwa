import pytest

from attestrwa.registry import RegistryError, parse_registry

from .conftest import PAYEE, REGISTRY_FILE, UNREGISTERED_PAYEE


def test_shipped_registry_parses(registry) -> None:
    assert registry.registry_id == "demo-payees"
    assert registry.contains(PAYEE)
    assert registry.contains(PAYEE.upper().replace("0X", "0x"))
    assert not registry.contains(UNREGISTERED_PAYEE)
    assert registry.entry(PAYEE)["id"] == "siam-riverside-living"


def test_registry_hash_covers_the_exact_bytes(registry) -> None:
    content = REGISTRY_FILE.read_bytes()
    assert parse_registry(content + b"\n").sha256 != registry.sha256


@pytest.mark.parametrize(
    "content",
    [
        b"[]",
        b'{"version": "1", "payees": []}',
        b'{"registry_id": "r", "payees": []}',
        b'{"registry_id": "r", "version": "1", "payees": {}}',
        b'{"registry_id": "r", "version": "1", "payees": [{"address": "0x123"}]}',
        b'{"registry_id": "r", "version": "1", "payees": ["0x00"]}',
        b'{"registry_id": "r", "version": "1", "payees": ['
        b'{"address": "0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc"},'
        b'{"address": "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"}]}',
        b"not json",
    ],
)
def test_malformed_registries_are_rejected(content: bytes) -> None:
    with pytest.raises(RegistryError):
        parse_registry(content)
