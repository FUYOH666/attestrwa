"""Payee registries.

A registry is a JSON file listing the addresses a policy accepts as payees::

    {
      "registry_id": "demo-payees",
      "version": "2026-11-12",
      "payees": [{"address": "0x...", "id": "...", "name": "..."}]
    }

A decision record refers to a registry by the sha256 of the file's exact
bytes, so anyone holding the same file can re-check the membership claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from attestrwa.canonical import CanonicalError, loads_strict
from attestrwa.hashing import HexError, normalize_address, sha256, to_hex


class RegistryError(ValueError):
    """A registry file is malformed."""


@dataclass(slots=True, frozen=True)
class Registry:
    registry_id: str
    version: str
    sha256: str
    entries: dict[str, dict[str, Any]]

    def contains(self, address: str) -> bool:
        return address.lower() in self.entries

    def entry(self, address: str) -> dict[str, Any] | None:
        return self.entries.get(address.lower())


def parse_registry(content: bytes) -> Registry:
    """Parse the exact bytes of a registry file."""
    try:
        doc = loads_strict(content)
    except CanonicalError as exc:
        raise RegistryError(f"cannot read registry: {exc}") from exc
    if not isinstance(doc, dict):
        raise RegistryError("registry must be a JSON object")
    registry_id = doc.get("registry_id")
    version = doc.get("version")
    payees = doc.get("payees")
    if not isinstance(registry_id, str) or not registry_id:
        raise RegistryError("registry needs a string 'registry_id'")
    if not isinstance(version, str) or not version:
        raise RegistryError("registry needs a string 'version'")
    if not isinstance(payees, list):
        raise RegistryError("registry needs a 'payees' array")
    entries: dict[str, dict[str, Any]] = {}
    for item in payees:
        if not isinstance(item, dict):
            raise RegistryError("each payee must be an object")
        try:
            address = normalize_address(item.get("address"))  # type: ignore[arg-type]
        except HexError as exc:
            raise RegistryError(f"payee entry has an invalid address: {exc}") from exc
        if address in entries:
            raise RegistryError(f"duplicate payee address {address}")
        entries[address] = item
    return Registry(
        registry_id=registry_id,
        version=version,
        sha256=to_hex(sha256(content)),
        entries=entries,
    )
