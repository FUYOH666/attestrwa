"""Hash and hex helpers shared by the record, policy and chain code."""

from __future__ import annotations

import hashlib
import re

from Crypto.Hash import keccak as _keccak

_HEX_RE = re.compile(r"0x[0-9a-f]*")


class HexError(ValueError):
    """A value is not the lowercase 0x-prefixed hex string the format requires."""


def keccak256(data: bytes) -> bytes:
    """Keccak-256 as used by Ethereum (not NIST SHA3-256)."""
    return _keccak.new(digest_bits=256, data=data).digest()


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def to_hex(data: bytes) -> str:
    return "0x" + data.hex()


def from_hex(value: str, length: int | None = None, *, what: str = "value") -> bytes:
    """Decode a lowercase ``0x`` hex string, optionally enforcing a byte length."""
    if not isinstance(value, str) or not _HEX_RE.fullmatch(value) or len(value) % 2:
        raise HexError(f"{what} must be lowercase 0x-prefixed hex with an even number of digits")
    raw = bytes.fromhex(value[2:])
    if length is not None and len(raw) != length:
        raise HexError(f"{what} must be {length} bytes, got {len(raw)}")
    return raw


def is_hex(value: object, length: int | None = None) -> bool:
    try:
        from_hex(value, length)  # type: ignore[arg-type]
    except HexError:
        return False
    return True


def normalize_address(value: str) -> str:
    """Lowercase an address. Records store addresses without EIP-55 casing."""
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise HexError(f"not a 20-byte address: {value!r}")
    return value.lower()
