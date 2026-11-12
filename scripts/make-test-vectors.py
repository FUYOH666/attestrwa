"""Regenerate spec/test-vectors from the reference implementation.

Run from the repository root:

    cd packages/attestrwa && uv run python ../../scripts/make-test-vectors.py

The vectors are deterministic (fixed nonce, fixed block and timestamps), so a
second implementation of the format can be checked against them byte for byte.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "attestrwa"))

from attestrwa.canonical import canonicalize  # noqa: E402
from attestrwa.hashing import keccak256, to_hex  # noqa: E402
from attestrwa.record import make_envelope  # noqa: E402
from tests.conftest import UNREGISTERED_PAYEE, make_body  # noqa: E402
from attestrwa.policy import load_policy  # noqa: E402
from attestrwa.registry import parse_registry  # noqa: E402

OUT = ROOT / "spec" / "test-vectors"

CANONICAL_CASES = [
    ("empty object", {}),
    ("key order", {"b": 1, "a": 2, "c": [3, 2, 1]}),
    ("nested", {"z": {"y": [True, False, None], "x": {"w": "v"}}, "a": []}),
    ("integers", {"zero": 0, "negative": -17, "max_safe": 9007199254740991}),
    ("large amount as string", {"amount": str(2**256 - 1)}),
    ("string escapes", {"s": 'quote " backslash \\ tab \t newline \n nul \u0000 unit \u001f'}),
    ("unicode", {"s": "ริเวอร์ไซด์ — Öl € 😀  "}),
    ("address and hash", {"a": "0x" + "ab" * 20, "h": "0x" + "cd" * 32}),
    ("array of mixed scalars", [1, "1", True, None, {"k": []}]),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    vectors = []
    for name, value in CANONICAL_CASES:
        canonical = canonicalize(value)
        vectors.append(
            {
                "name": name,
                "value": value,
                "canonical": canonical.decode("utf-8"),
                "keccak256": to_hex(keccak256(canonical)),
            }
        )
    (OUT / "canonical.json").write_text(
        json.dumps(
            {
                "description": (
                    "Canonicalisation vectors for Decision Record v0.1. `canonical` is the exact "
                    "UTF-8 text that must be hashed; `keccak256` is the hash of those bytes."
                ),
                "vectors": vectors,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    pack = load_policy(ROOT / "data" / "policies" / "settlement-demo-v2.yaml")
    registry = parse_registry((ROOT / "data" / "registry" / "payees.json").read_bytes())
    cases = {
        "record-approve.json": make_body(pack, registry),
        "record-reject.json": make_body(pack, registry, payee=UNREGISTERED_PAYEE),
    }
    for filename, body in cases.items():
        envelope = make_envelope(body, network="test-vector")
        (OUT / filename).write_text(
            json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"{filename}: {envelope['record_hash']}")


if __name__ == "__main__":
    main()
