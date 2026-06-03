"""Attester service — orchestrates AttestRWA settlement attestations.

The flow per deal:

1. Load the developer feed referenced by `developer_id` and verify the
   instructed payee wallet against `authorized_payee_wallets`.
2. Classify the buyer wallet via `wallet_taint`.
3. Evaluate the compliance DSL policy (default policy lives in
   `data/synthetic/policies/default_attestrwa_policy.yaml`).
4. Build a privacy-safe evidence pack (developer feed slice + policy rule
   results + taint signals + RAG citation IDs); hash it for the on-chain
   `evidenceHash` field.
5. Sign and broadcast an EAS `SettlementApproval` attestation.

The service is RPC-aware but EAS-side mistakes (revert, schema mismatch)
propagate as `AttesterError` for the FastAPI handler to translate.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.paths import repo_root, synthetic_root
from app.services.compliance_dsl import (
    DSLError,
    PolicyEvaluation,
    Rule,
    evaluate as evaluate_policy,
    parse_rules,
)
from app.services.data_loader import DataLoadError, load_json
from app.services.eas_client import (
    AttestationResult,
    EASClient,
    SettlementApprovalPayload,
    build_default_evidence_hash,
    current_expiration,
)
from app.services.wallet_taint import TaintReport, classify_wallet

logger = logging.getLogger(__name__)


class AttesterError(RuntimeError):
    """Generic attester-service error (developer feed missing, DSL bad, …)."""


@dataclass(slots=True)
class DealRequest:
    """Inputs to the attester decision."""

    deal_id: bytes  # 32 bytes
    buyer_wallet: str
    payee_wallet: str
    token_address: str
    amount_base_units: int
    developer_id: str
    jurisdiction: str = "TH"
    buyer_kyc_tier: int = 3
    expires_in_seconds: int = 86_400


@dataclass(slots=True)
class AttesterDecision:
    """Pure decision output before any on-chain action."""

    decision: str  # "approve" | "reject"
    capital_class: int
    payee_verified: bool
    rule_results: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    evidence_hash: bytes = b"\x00" * 32
    policy_pack_id: str = ""
    policy_hash: str = ""
    taint: TaintReport | None = None
    expires_at: int = 0


# ---- Policy loading --------------------------------------------------------

_DEFAULT_POLICY_PATH = (
    "policies/default_attestrwa_policy.yaml"
)


def _policy_path() -> Path:
    env_override = os.getenv("ATTESTRWA_POLICY_FILE")
    if env_override:
        path = Path(env_override)
        return path if path.is_absolute() else repo_root() / path
    return synthetic_root() / _DEFAULT_POLICY_PATH


def policy_file_display() -> str:
    """Resolved policy path for health/readiness endpoints."""
    return str(_policy_path())


def policy_provenance() -> tuple[str, str]:
    """Return (policy_pack_id, policy_hash) for the active policy file."""
    path = _policy_path()
    if not path.is_file():
        raise AttesterError(f"compliance policy file not found: {path}")
    content = path.read_bytes()
    policy_hash = "0x" + hashlib.sha256(content).hexdigest()
    pack_id = _extract_policy_pack_id(path, content)
    return pack_id, policy_hash


def _extract_policy_pack_id(path: Path, content: bytes) -> str:
    for line in content.decode("utf-8").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("# pack_id:"):
            return stripped.split(":", 1)[1].strip()
    return path.stem


def load_policy_rules() -> list[Rule]:
    path = _policy_path()
    if not path.is_file():
        raise AttesterError(f"compliance policy file not found: {path}")
    try:
        return parse_rules(path)
    except DSLError as exc:
        raise AttesterError(f"compliance policy DSL invalid: {exc}") from exc


# ---- Developer feed helpers -----------------------------------------------

_DEVELOPER_FEED_BY_ID: dict[str, str] = {
    "siam-riverside-living": "developers/siam-riverside-feed.json",
    "developer-bangkok-landmark": "developers/bangkok-landmark-feed.json",
    "developer-shadow-bay": "developers/shadow-bay-feed.json",
}


def _load_developer_feed(developer_id: str) -> dict[str, Any]:
    rel_path = _DEVELOPER_FEED_BY_ID.get(developer_id)
    if rel_path is None:
        raise AttesterError(f"unknown developer_id: {developer_id}")
    try:
        return load_json(rel_path)
    except DataLoadError as exc:
        raise AttesterError(f"developer feed unreadable: {exc}") from exc


def _payee_verified(feed: dict[str, Any], payee_wallet: str) -> bool:
    wallets = feed.get("authorized_payee_wallets") or []
    return any(w.lower() == payee_wallet.lower() for w in wallets)


# ---- Decision --------------------------------------------------------------


def decide_for_deal(request: DealRequest) -> AttesterDecision:
    """Pure decision: returns approve/reject without touching the chain."""
    feed = _load_developer_feed(request.developer_id)
    payee_verified = _payee_verified(feed, request.payee_wallet)
    taint = classify_wallet(request.buyer_wallet)
    policy_pack_id, policy_hash = policy_provenance()
    rules = load_policy_rules()
    context: dict[str, Any] = {
        "payee_verified": payee_verified,
        "capital_class": taint.capital_class,
        "amount_usdc": request.amount_base_units,
        "buyer_kyc_tier": request.buyer_kyc_tier,
        "jurisdiction": request.jurisdiction,
    }
    evaluation: PolicyEvaluation = evaluate_policy(rules, context)

    reasons: list[str] = []
    if not payee_verified:
        reasons.append(
            f"Instructed payee wallet {request.payee_wallet} is not in developer "
            f"{request.developer_id} authorized_payee_wallets."
        )
    if taint.capital_class >= 2:
        reasons.append(
            f"Buyer wallet capital_class=red — {taint.explanation}"
        )
    for result in evaluation.rule_results:
        if not result.passed:
            reasons.append(f"Rule '{result.rule_id}' failed: {result.explanation}")

    expires_at = current_expiration(request.expires_in_seconds)
    evidence_parts = [
        f"developer_feed={feed.get('developer_id')}",
        f"payee_verified={payee_verified}",
        f"capital_class={taint.capital_class}",
        f"taint_signals={','.join(taint.signals) or 'none'}",
        f"amount_base_units={request.amount_base_units}",
        f"jurisdiction={request.jurisdiction}",
        f"policy_pack_id={policy_pack_id}",
        f"policy_hash={policy_hash}",
        f"policy_decision={evaluation.decision}",
    ]
    evidence_hash = build_default_evidence_hash(*evidence_parts)

    decision_str = "approve" if evaluation.passed and payee_verified else "reject"

    return AttesterDecision(
        decision=decision_str,
        capital_class=taint.capital_class,
        payee_verified=payee_verified,
        rule_results=[
            {
                "rule_id": r.rule_id,
                "passed": r.passed,
                "explanation": r.explanation,
            }
            for r in evaluation.rule_results
        ],
        reasons=reasons,
        evidence_hash=evidence_hash,
        policy_pack_id=policy_pack_id,
        policy_hash=policy_hash,
        taint=taint,
        expires_at=expires_at,
    )


# ---- On-chain attestation --------------------------------------------------


def attest_for_deal(
    request: DealRequest,
    decision: AttesterDecision,
    client: EASClient | None = None,
) -> AttestationResult:
    """Sign and broadcast the EAS attestation that captures the decision."""
    client = client or EASClient()
    attester_address = client.attester_address
    payload = SettlementApprovalPayload(
        deal_id=request.deal_id,
        attester=attester_address,
        payee_address=request.payee_wallet,
        token_address=request.token_address,
        amount=request.amount_base_units,
        capital_class=decision.capital_class,
        evidence_hash=decision.evidence_hash,
        jurisdiction=request.jurisdiction,
        expires_at=decision.expires_at,
        payee_verified=decision.payee_verified,
    )
    return client.attest(payload, revocable=True, expiration_time=decision.expires_at)


def attester_health() -> dict[str, Any]:
    """Lightweight health: env config + EAS reachability + policy path."""
    policy = policy_file_display()
    try:
        from importlib.metadata import version

        repo_version = version("attestrwa-api")
    except Exception:
        repo_version = "unknown"

    try:
        client = EASClient()
    except Exception as exc:
        return {
            "status": "down",
            "service": "attestrwa-attester",
            "repo_version": repo_version,
            "policy_file": policy,
            "dev_chain_reachable": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    payload = client.health()
    payload["repo_version"] = repo_version
    payload["policy_file"] = policy
    payload["dev_chain_reachable"] = payload.get("status") == "ok"
    return payload
