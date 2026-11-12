import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.logging_config import configure_logging
from app.schemas.attester import (
    AttestRequest,
    AttestResponse,
    AttestationLookupResponse,
    AttesterHealthResponse,
)
from app.services.attester_service import (
    AttesterError,
    DealRequest,
    attest_for_deal,
    attester_health,
    decide_for_deal,
)
from app.services.eas_client import EASClient


logger = logging.getLogger(__name__)


def _cors_origins() -> list[str]:
    default_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    configured = get_settings().cors_origins
    if not configured.strip():
        return default_origins
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("AttestRWA API starting version=%s", settings.api_version)
    yield


app = FastAPI(
    title="AttestRWA API",
    description=(
        "AttestRWA attester: evaluates a settlement against a versioned policy and anchors "
        "the decision on-chain as an EAS attestation."
    ),
    version=get_settings().api_version,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "attestrwa-api"}


# ---- Attester endpoints -----------------------------------------------------


def _explorer_url(chain_id: int | None, uid: str) -> str | None:
    if chain_id == 84532:
        return f"https://base-sepolia.easscan.org/attestation/view/{uid}"
    if chain_id == 8453:
        return f"https://base.easscan.org/attestation/view/{uid}"
    return None


@app.post("/attest/settlement", response_model=AttestResponse)
def post_attest_settlement(body: AttestRequest) -> dict[str, object]:
    """Decide on a settlement and (optionally) submit an EAS attestation."""
    logger.info(
        "Attestation request deal=%s buyer=%s amount=%s developer=%s",
        body.deal_id,
        body.buyer_wallet,
        body.amount_base_units,
        body.developer_id,
    )
    request = DealRequest(
        deal_id=bytes.fromhex(body.deal_id[2:]),
        buyer_wallet=body.buyer_wallet,
        payee_wallet=body.payee_wallet,
        token_address=body.token_address,
        amount_base_units=body.amount_base_units,
        developer_id=body.developer_id,
        jurisdiction=body.jurisdiction,
        buyer_kyc_tier=body.buyer_kyc_tier,
        expires_in_seconds=body.expires_in_seconds,
    )
    try:
        decision = decide_for_deal(request)
    except AttesterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    chain_id: int | None = None
    attestation_uid: str | None = None
    tx_hash: str | None = None
    block_number: int | None = None
    gas_used: int | None = None

    submit_on_chain = (
        get_settings().attestrwa_submit_on_chain
        if hasattr(get_settings(), "attestrwa_submit_on_chain")
        else True
    )

    if submit_on_chain:
        try:
            client = EASClient()
            chain_id = client.config.chain_id
            result = attest_for_deal(request, decision, client=client)
            attestation_uid = result.uid
            tx_hash = result.tx_hash
            block_number = result.block_number
            gas_used = result.gas_used
        except Exception as exc:
            logger.warning("on-chain attest failed: %s — returning decision only", exc)

    explanation = (
        f"Decision {decision.decision} — payee_verified={decision.payee_verified} "
        f"capital_class={decision.capital_class}"
    )
    if decision.reasons:
        explanation += " :: " + "; ".join(decision.reasons)

    return {
        "decision": decision.decision,
        "deal_id": body.deal_id,
        "capital_class": decision.capital_class,
        "payee_verified": decision.payee_verified,
        "reasons": decision.reasons,
        "rule_results": decision.rule_results,
        "taint": {
            "wallet": decision.taint.wallet,
            "capital_class": decision.taint.capital_class,
            "signals": decision.taint.signals,
            "explanation": decision.taint.explanation,
        }
        if decision.taint is not None
        else None,
        "evidence_hash": "0x" + decision.evidence_hash.hex(),
        "policy_pack_id": decision.policy_pack_id,
        "policy_hash": decision.policy_hash,
        "expires_at": decision.expires_at,
        "attestation_uid": attestation_uid,
        "tx_hash": tx_hash,
        "block_number": block_number,
        "gas_used": gas_used,
        "chain_id": chain_id,
        "eas_explorer_url": _explorer_url(chain_id, attestation_uid) if attestation_uid else None,
        "explanation": explanation,
    }


@app.get("/attest/healthz", response_model=AttesterHealthResponse)
def get_attest_healthz() -> dict[str, object]:
    return attester_health()


@app.get("/attest/{deal_id}", response_model=AttestationLookupResponse)
def get_attestation_for_deal(deal_id: str) -> dict[str, object]:
    """Placeholder attestation lookup — Week 2.3 wires it to an indexer."""
    return {
        "deal_id": deal_id,
        "attestation": None,
        "note": "Per-deal attestation lookup is wired via the EAS indexer in Week 3.",
    }
