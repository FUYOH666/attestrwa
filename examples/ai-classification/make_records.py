"""Build and sign the two example decision records.

Run from the repository root:

    uv run --with ./packages/attestrwa examples/ai-classification/make_records.py

The script is the whole integration: hash the material, state where each
input came from, let the policy decide, sign the result. Everything here is
synthetic. The records are signed with the RFC 8032 test key, whose private
half is public, so they prove nothing about who made them; a real pipeline
signs with its own key (`attestrwa keygen`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from attestrwa.hashing import sha256, to_hex
from attestrwa.policy import load_policy
from attestrwa.record import build_case_record, make_envelope, record_hash
from attestrwa.signing import RFC8032_TEST_SEED, public_key_from_seed, sign_hash

HERE = Path(__file__).resolve().parent
POLICY_URI = "examples/ai-classification/policy.yaml"
SOFTWARE = "attestrwa-example/ai-classification"
REVIEWER = "broker:R-07 (fictional licensed customs broker)"

CASES = {
    "approve": {
        "directory": "case-approve",
        "case_id": "CLS-2026-000412",
        "title": "HS classification: stainless steel vacuum bottle VB-500",
        "evaluated_at": 1_794_303_000,  # 2026-11-10 09:30:00 UTC
        "supporting": ["commercial-invoice.txt", "packing-list.txt", "product-datasheet.txt"],
        "customs_value_usd": "18400",
        "reviewer_approved": True,
        "reviewed_at": 1_794_302_400,
    },
    "reject": {
        "directory": "case-reject",
        "case_id": "CLS-2026-000413",
        "title": "HS classification: insulated bottle with loudspeaker SB-700",
        "evaluated_at": 1_794_306_600,  # 2026-11-10 10:30:00 UTC
        "supporting": ["commercial-invoice.txt"],
        "customs_value_usd": "3200",
        "reviewer_approved": False,
        "reviewed_at": 1_794_306_000,
    },
}


def digest(path: Path) -> str:
    return to_hex(sha256(path.read_bytes()))


def model_input(name: str, field: str, model: str, folder: Path, output: str) -> dict[str, Any]:
    """A value read from one field of a model's JSON output."""
    answer = json.loads((folder / output).read_text(encoding="utf-8"))
    value = answer[field]
    return {
        "name": name,
        "type": "int" if isinstance(value, int) else "string",
        "value": str(value) if isinstance(value, int) else value,
        "source": {
            "kind": "model",
            "provider": "example",
            "model": model,
            "prompt_sha256": digest(folder / "prompt.txt"),
            "output_sha256": digest(folder / output),
            "field": field,
        },
    }


def document(folder: Path, name: str, locator: str | None = None) -> dict[str, str]:
    item = {"ref": f"{folder.name}/{name}", "sha256": digest(folder / name)}
    if locator:
        item["locator"] = locator
    return item


def build(case: dict[str, Any]) -> dict[str, Any]:
    folder = HERE / case["directory"]
    inputs = [
        model_input("hs_code", "hs_code", "classifier-demo-1", folder, "model-output.json"),
        model_input(
            "confidence_pct", "confidence_pct", "classifier-demo-1", folder, "model-output.json"
        ),
        model_input(
            "hs_code_check", "hs_code", "classifier-demo-2", folder, "model-output-check.json"
        ),
        {
            "name": "supporting_documents",
            "type": "int",
            "value": str(len(case["supporting"])),
            "source": {
                "kind": "document",
                "reading": "count",
                "items": [document(folder, name) for name in case["supporting"]],
            },
        },
        {
            "name": "customs_value_usd",
            "type": "int",
            "value": case["customs_value_usd"],
            "source": {
                "kind": "document",
                "reading": "extract",
                "items": [document(folder, "commercial-invoice.txt", "line 'Total'")],
            },
        },
        {
            "name": "reviewer_approved",
            "type": "bool",
            "value": case["reviewer_approved"],
            "source": {"kind": "human", "by": REVIEWER, "at": case["reviewed_at"]},
        },
    ]
    body = build_case_record(
        case_id=case["case_id"],
        title=case["title"],
        digest=digest(folder / "line-item.json"),
        evaluated_at=case["evaluated_at"],
        pack=load_policy(HERE / "policy.yaml"),
        policy_uri=POLICY_URI,
        inputs=inputs,
        public_key=to_hex(public_key_from_seed(RFC8032_TEST_SEED)),
        software=SOFTWARE,
        # Fixed so that the published example is reproducible byte for byte.
        # A real record leaves this out and gets 16 random bytes.
        nonce=to_hex(sha256(case["case_id"].encode())[:16]),
    )
    signature = sign_hash(RFC8032_TEST_SEED, record_hash(body))
    return make_envelope(body, signature=to_hex(signature), links={"policy": POLICY_URI})


def build_all() -> dict[str, dict[str, Any]]:
    return {name: build(case) for name, case in CASES.items()}


def dump(envelope: dict[str, Any]) -> str:
    return json.dumps(envelope, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    for name, envelope in build_all().items():
        path = HERE / "records" / f"{name}.json"
        path.write_text(dump(envelope), encoding="utf-8")
        outcome = envelope["record"]["decision"]["outcome"]
        print(f"{path.relative_to(HERE)}: {outcome} {envelope['record_hash']}")


if __name__ == "__main__":
    main()
