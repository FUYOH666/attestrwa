#!/usr/bin/env python3
"""Run AttestRWA RWA scenarios from data/synthetic/rwa/scenarios.json.

Writes docs/RWA_SCENARIO_REPORT.md. Uses local attester logic (no API required).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "docs" / "RWA_SCENARIO_REPORT.md"
SCENARIOS_PATH = ROOT / "data" / "synthetic" / "rwa" / "scenarios.json"
MOCK_USDC = "0xeba5CEc9257045Df0B44eA784F9a7Fa07DeeF6d4"


def _load_scenarios() -> list[dict]:
    data = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    return data["scenarios"]


def _scenario_to_request(scenario: dict):
    sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
    from app.services.attester_service import DealRequest  # noqa: E402

    deal_hex = "0x" + hashlib.sha256(scenario["id"].encode("utf-8")).hexdigest()
    prop = scenario["property"]
    buyer = scenario["buyer"]
    payee = scenario["instructed_payee"]
    amount = int(prop["price_usdc"]) * 1_000_000  # USDC 6 decimals

    return DealRequest(
        deal_id=bytes.fromhex(deal_hex[2:]),
        buyer_wallet=buyer["wallet"],
        payee_wallet=payee["wallet"],
        token_address=MOCK_USDC,
        amount_base_units=amount,
        developer_id=prop.get("developer_id", "developer-bangkok-landmark"),
        jurisdiction=prop.get("jurisdiction", "TH"),
        buyer_kyc_tier=3,
        expires_in_seconds=86_400,
    )


def _run_local(scenarios: list[dict]) -> list[dict]:
    sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
    from app.services.attester_service import decide_for_deal  # noqa: E402

    results: list[dict] = []
    for scenario in scenarios:
        expected = scenario["expected_attester_decision"]
        decision = decide_for_deal(_scenario_to_request(scenario))
        ok = (
            decision.decision == expected["decision"]
            and decision.capital_class == expected["capital_class"]
            and decision.payee_verified == expected["payee_verified"]
        )
        results.append(
            {
                "id": scenario["id"],
                "title": scenario["title"],
                "ok": ok,
                "expected": expected,
                "actual": {
                    "decision": decision.decision,
                    "capital_class": decision.capital_class,
                    "payee_verified": decision.payee_verified,
                    "policy_pack_id": decision.policy_pack_id,
                    "policy_hash": decision.policy_hash,
                },
            }
        )
    return results


def _format_report(results: list[dict]) -> str:
    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    lines = [
        "# RWA Scenario Simulation Report",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        f"**Result:** {passed}/{total} scenarios matched expected attester outcomes.",
        "",
        "Source: [`data/synthetic/rwa/scenarios.json`](../data/synthetic/rwa/scenarios.json)",
        "",
        "Regenerate:",
        "",
        "```bash",
        "uv run --directory apps/api python ../../scripts/run_rwa_scenarios.py",
        "```",
        "",
    ]
    for row in results:
        status = "PASS" if row["ok"] else "FAIL"
        lines.append(f"## `{row['id']}` — {status}")
        lines.append("")
        lines.append(f"**{row['title']}**")
        lines.append("")
        lines.append("| Field | Expected | Actual |")
        lines.append("|-------|----------|--------|")
        for key in ("decision", "capital_class", "payee_verified"):
            lines.append(
                f"| {key} | {row['expected'][key]} | {row['actual'][key]} |"
            )
        lines.append(f"| policy_pack_id | — | {row['actual']['policy_pack_id']} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RWA scenario matrix")
    parser.add_argument(
        "--report",
        type=Path,
        default=REPORT_PATH,
        help="Output markdown report path",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if any scenario fails",
    )
    args = parser.parse_args()

    scenarios = _load_scenarios()
    results = _run_local(scenarios)
    args.report.write_text(_format_report(results), encoding="utf-8")
    print(f"Wrote {args.report}")

    failed = [r["id"] for r in results if not r["ok"]]
    if failed:
        print("Failed:", ", ".join(failed), file=sys.stderr)
        return 1 if args.check else 0
    print(f"All {len(results)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
