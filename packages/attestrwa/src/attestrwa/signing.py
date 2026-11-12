"""Ed25519 signatures over record hashes (the ``signature`` anchor of format 0.2).

A signed record needs no blockchain: the signer's public key is part of the
hashed record, and the signature over the record hash travels in the envelope.
Whoever verifies must decide which public keys they trust; a valid signature
by an unknown key proves only that the holder of that key signed.
"""

from __future__ import annotations

import secrets

from Crypto.PublicKey import ECC
from Crypto.Signature import eddsa

SIGNATURE_SCHEME = "ed25519"
SEED_BYTES = 32
PUBLIC_KEY_BYTES = 32
SIGNATURE_BYTES = 64

# Domain separation: a key used here cannot be tricked into signing something
# that is valid in another protocol, and the reverse.
_DOMAIN = b"attestrwa.decision-record.signature/1\x00"

# RFC 8032, section 7.1, TEST 1. The private half is printed in the RFC, so
# anyone can sign with it. The example records and the test vectors of this
# repository are signed with it; nothing else ever should be.
RFC8032_TEST_SEED = bytes.fromhex(
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
)
RFC8032_TEST_PUBLIC_KEY = bytes.fromhex(
    "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
)
PUBLISHED_TEST_KEYS = frozenset({RFC8032_TEST_PUBLIC_KEY})

# Order of the prime-order group of Ed25519.
_GROUP_ORDER = 2**252 + 27742317777372353535851937790883648493


class SigningError(ValueError):
    """A key or a signature has the wrong shape."""


def generate_seed() -> bytes:
    """A new private key: 32 random bytes."""
    return secrets.token_bytes(SEED_BYTES)


def _private_key(seed: bytes) -> ECC.EccKey:
    if len(seed) != SEED_BYTES:
        raise SigningError(f"a signing key is {SEED_BYTES} bytes")
    return ECC.construct(curve="Ed25519", seed=seed)


def public_key_from_seed(seed: bytes) -> bytes:
    return _private_key(seed).public_key().export_key(format="raw")


def signing_message(record_hash: bytes) -> bytes:
    if len(record_hash) != 32:
        raise SigningError("a record hash is 32 bytes")
    return _DOMAIN + record_hash


def sign_hash(seed: bytes, record_hash: bytes) -> bytes:
    """Sign a record hash. Ed25519 is deterministic: same key, same hash, same bytes."""
    return eddsa.new(_private_key(seed), "rfc8032").sign(signing_message(record_hash))


def is_usable_public_key(public_key: bytes) -> bool:
    """True for the canonical encoding of a point of prime order.

    The identity and the other points of small order "verify" signatures that
    nobody had to make: for the identity, one constant signature is valid for
    every message. No private key corresponds to such a point, so a record
    that names one is committed to by nobody.
    """
    if not isinstance(public_key, bytes) or len(public_key) != PUBLIC_KEY_BYTES:
        return False
    try:
        point = eddsa.import_public_key(encoded=public_key).pointQ
        return not point.is_point_at_infinity() and (point * _GROUP_ORDER).is_point_at_infinity()
    except (ValueError, TypeError):
        return False


def verify_signature(public_key: bytes, record_hash: bytes, signature: bytes) -> bool:
    """True if ``signature`` is a valid signature of ``record_hash`` by ``public_key``."""
    if len(signature) != SIGNATURE_BYTES or not is_usable_public_key(public_key):
        return False
    try:
        key = eddsa.import_public_key(encoded=public_key)
        eddsa.new(key, "rfc8032").verify(signing_message(record_hash), signature)
    except (ValueError, TypeError):
        return False
    return True
