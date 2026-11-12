"""File store for decision records.

Records are immutable: ``by-hash/<record_hash>.json`` is written once and
never changed. ``by-deal/<deal_id>.json`` is the ordered list of decisions
made about a deal (more than one only after a revocation).
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from attestrwa.canonical import loads_strict

_BYTES32_RE = re.compile(r"0x[0-9a-f]{64}")


class RecordStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._by_hash = root / "by-hash"
        self._by_deal = root / "by-deal"
        self._lock = threading.Lock()

    @staticmethod
    def _key(value: str) -> str:
        if not _BYTES32_RE.fullmatch(value):
            raise ValueError("expected a lowercase 0x-prefixed 32-byte hex value")
        return value

    def _write(self, path: Path, document: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)

    def save(self, envelope: dict[str, Any]) -> None:
        """Store an attested record and append it to its deal's history."""
        record_hash = self._key(envelope["record_hash"])
        deal_id = self._key(envelope["record"]["subject"]["deal_id"])
        with self._lock:
            self._write(self._by_hash / f"{record_hash}.json", envelope)
            index_path = self._by_deal / f"{deal_id}.json"
            history = self._read(index_path) or {"deal_id": deal_id, "records": []}
            history["records"].append(
                {
                    "record_hash": record_hash,
                    "attestation_uid": envelope["attestation"]["uid"],
                    "decision": envelope["record"]["decision"]["outcome"],
                }
            )
            self._write(index_path, history)

    @staticmethod
    def _read(path: Path) -> Any | None:
        try:
            return loads_strict(path.read_bytes())
        except FileNotFoundError:
            return None

    def by_hash(self, record_hash: str) -> dict[str, Any] | None:
        return self._read(self._by_hash / f"{self._key(record_hash)}.json")

    def history(self, deal_id: str) -> list[dict[str, Any]]:
        index = self._read(self._by_deal / f"{self._key(deal_id)}.json")
        return list(index["records"]) if index else []

    def latest(self, deal_id: str) -> dict[str, Any] | None:
        history = self.history(deal_id)
        return self.by_hash(history[-1]["record_hash"]) if history else None
