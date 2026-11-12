"""Ed25519 signatures over record hashes."""

import pytest
from Crypto.PublicKey import ECC
from Crypto.Signature import eddsa

from attestrwa.signing import (
    PUBLISHED_TEST_KEYS,
    RFC8032_TEST_PUBLIC_KEY,
    RFC8032_TEST_SEED,
    SigningError,
    generate_seed,
    is_usable_public_key,
    public_key_from_seed,
    sign_hash,
    signing_message,
    verify_signature,
)

HASH = bytes(range(32))
OTHER_HASH = bytes(range(1, 33))
SEED = bytes(range(64, 96))
PUBLIC = public_key_from_seed(SEED)

# RFC 8032, section 7.1, TEST 1: the signature of the empty message.
RFC8032_TEST_SIGNATURE = bytes.fromhex(
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
)


def test_the_published_test_key_is_the_rfc_8032_one() -> None:
    assert public_key_from_seed(RFC8032_TEST_SEED) == RFC8032_TEST_PUBLIC_KEY
    assert RFC8032_TEST_PUBLIC_KEY in PUBLISHED_TEST_KEYS
    key = ECC.construct(curve="Ed25519", seed=RFC8032_TEST_SEED)
    assert eddsa.new(key, "rfc8032").sign(b"") == RFC8032_TEST_SIGNATURE


def test_a_signature_verifies_and_is_deterministic() -> None:
    signature = sign_hash(SEED, HASH)
    assert len(signature) == 64
    assert signature == sign_hash(SEED, HASH)
    assert verify_signature(PUBLIC, HASH, signature)


def test_a_signature_does_not_verify_for_another_hash_or_key() -> None:
    signature = sign_hash(SEED, HASH)
    assert not verify_signature(PUBLIC, OTHER_HASH, signature)
    assert not verify_signature(public_key_from_seed(bytes(32)), HASH, signature)


def test_one_flipped_bit_breaks_the_signature() -> None:
    signature = bytearray(sign_hash(SEED, HASH))
    signature[10] ^= 0x01
    assert not verify_signature(PUBLIC, HASH, bytes(signature))


def test_the_signed_message_is_domain_separated() -> None:
    assert signing_message(HASH).endswith(HASH)
    assert signing_message(HASH) != HASH
    key = ECC.construct(curve="Ed25519", seed=SEED)
    bare = eddsa.new(key, "rfc8032").sign(HASH)
    assert not verify_signature(PUBLIC, HASH, bare)


@pytest.mark.parametrize(
    ("public_key", "signature"),
    [
        (b"", bytes(64)),
        (bytes(31), bytes(64)),
        (bytes(32), bytes(63)),
        (bytes(32), b""),
        (b"\xff" * 32, b"\xff" * 64),
    ],
)
def test_malformed_keys_and_signatures_are_simply_invalid(public_key, signature) -> None:
    assert verify_signature(public_key, HASH, signature) is False


def test_wrong_sizes_are_refused_when_signing() -> None:
    with pytest.raises(SigningError):
        sign_hash(bytes(31), HASH)
    with pytest.raises(SigningError):
        sign_hash(SEED, bytes(31))
    with pytest.raises(SigningError):
        public_key_from_seed(b"")


def test_generated_keys_are_distinct_and_usable() -> None:
    first, second = generate_seed(), generate_seed()
    assert first != second and len(first) == 32
    assert verify_signature(public_key_from_seed(first), HASH, sign_hash(first, HASH))


def test_the_signed_message_is_the_label_a_zero_byte_and_the_hash() -> None:
    message = signing_message(HASH)
    assert message == b"attestrwa.decision-record.signature/1" + b"\x00" + HASH
    assert len(message) == 70


# The eight points of small order on Ed25519, in their canonical encodings.
SMALL_ORDER_KEYS = [
    "0100000000000000000000000000000000000000000000000000000000000000",
    "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
    "0000000000000000000000000000000000000000000000000000000000000080",
    "0000000000000000000000000000000000000000000000000000000000000000",
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a",
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac03fa",
    "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05",
    "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc85",
]


def test_the_identity_key_cannot_sign_everything() -> None:
    """With the identity as the public key, one constant "signature" satisfies
    the Ed25519 equation for every message. Nobody holds a private key for it."""
    identity = bytes([1]) + bytes(31)
    constant = bytes([1]) + bytes(63)
    assert not is_usable_public_key(identity)
    assert not verify_signature(identity, HASH, constant)
    assert not verify_signature(identity, OTHER_HASH, constant)


@pytest.mark.parametrize("encoded", SMALL_ORDER_KEYS)
def test_keys_of_small_order_are_refused(encoded: str) -> None:
    key = bytes.fromhex(encoded)
    assert not is_usable_public_key(key)
    assert not verify_signature(key, HASH, bytes(64))


def test_a_key_outside_the_prime_order_group_is_refused() -> None:
    honest = ECC.construct(curve="Ed25519", seed=SEED).pointQ
    torsion = eddsa.import_public_key(encoded=bytes.fromhex(SMALL_ORDER_KEYS[4])).pointQ
    mixed = ECC.construct(
        curve="Ed25519", point_x=(honest + torsion).x, point_y=(honest + torsion).y
    )
    assert not is_usable_public_key(mixed.public_key().export_key(format="raw"))


@pytest.mark.parametrize(
    "key",
    [
        (2**255 - 19 + 1).to_bytes(32, "little"),  # the identity again, not reduced
        b"\xff" * 32,
        bytes(31),
        bytes(33),
        "00" * 32,
        None,
    ],
)
def test_things_that_are_not_public_keys_are_refused(key) -> None:
    assert not is_usable_public_key(key)


def test_honest_keys_are_usable() -> None:
    assert is_usable_public_key(PUBLIC)
    assert is_usable_public_key(RFC8032_TEST_PUBLIC_KEY)
    assert is_usable_public_key(public_key_from_seed(generate_seed()))
