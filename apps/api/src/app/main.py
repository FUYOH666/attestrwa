import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.demo_case import ANCHOR_CASE
from app.logging_config import configure_logging
from app.schemas.attester import (
    AttestRequest,
    AttestResponse,
    AttestationLookupResponse,
    AttesterHealthResponse,
)
from app.schemas.demo import (
    ClosingPassportResponse,
    DeveloperKnowledgeHubResponse,
    SupplierContrastResponse,
)
from app.services.attester_service import (
    AttesterError,
    DealRequest,
    attest_for_deal,
    attester_health,
    decide_for_deal,
)
from app.services.closing_passport_demo import build_closing_passport_demo
from app.services.data_loader import DataLoadError
from app.services.developer_knowledge import build_developer_knowledge_hub
from app.services.eas_client import EASClient
from app.services.rag import ingest_synthetic_documents, rag_health, run_scenario_with_rag
from app.services.scenarios import get_scenario_detail, list_scenarios, run_scenario
from app.services.supplier_contrast_demo import build_supplier_contrast_demo


logger = logging.getLogger(__name__)


def _cors_origins() -> list[str]:
    default_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://scanovich.ai",
        "https://www.scanovich.ai",
    ]
    configured = get_settings().bankable_cors_origins
    if not configured.strip():
        return default_origins
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def _data_unavailable_http() -> HTTPException:
    return HTTPException(status_code=503, detail="Synthetic demo data unavailable")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.bankable_log_level)
    logger.info("AttestRWA API starting version=%s", settings.bankable_api_version)
    yield


app = FastAPI(
    title="AttestRWA API",
    description=(
        "AttestRWA — Settlement Attestation Layer for RWA. Off-chain attester service that "
        "applies bank-grade verification rules (Property Shield, capital classification, "
        "RAG-assisted evidence) and signs on-chain EAS attestations consumed by the "
        "programmable settlement escrow on Base Sepolia."
    ),
    version=get_settings().bankable_api_version,
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


@app.get("/api/demo/closing-passport", response_model=ClosingPassportResponse)
def get_closing_passport_demo() -> dict[str, object]:
    logger.info("Demo endpoint hit path=/api/demo/closing-passport")
    try:
        return build_closing_passport_demo()
    except DataLoadError as exc:
        logger.error("Closing passport demo failed: %s", exc)
        raise _data_unavailable_http() from exc


@app.get("/api/demo/developer-knowledge-hub", response_model=DeveloperKnowledgeHubResponse)
def get_developer_knowledge_hub_demo() -> dict[str, object]:
    logger.info("Demo endpoint hit path=/api/demo/developer-knowledge-hub")
    try:
        return build_developer_knowledge_hub(ANCHOR_CASE)
    except DataLoadError as exc:
        logger.error("Developer knowledge hub failed: %s", exc)
        raise _data_unavailable_http() from exc


@app.get("/api/demo/supplier-contrast", response_model=SupplierContrastResponse)
def get_supplier_contrast_demo() -> dict[str, object]:
    logger.info("Demo endpoint hit path=/api/demo/supplier-contrast")
    try:
        return build_supplier_contrast_demo()
    except (DataLoadError, ValueError) as exc:
        logger.error("Supplier contrast demo failed: %s", exc)
        raise _data_unavailable_http() from exc


@app.get("/api/demo/evidence-pack")
def get_evidence_pack_export() -> dict[str, object]:
    logger.info("Demo endpoint hit path=/api/demo/evidence-pack")
    try:
        demo = build_closing_passport_demo()
    except DataLoadError as exc:
        logger.error("Evidence pack export failed: %s", exc)
        raise _data_unavailable_http() from exc

    closing_passport = demo["closing_passport"]

    return {
        "data_classification": "synthetic_demo_data",
        "export_type": "closing_passport_evidence_pack",
        "case_id": closing_passport["case_id"],
        "evidence_pack_hash": closing_passport["evidence_pack_hash"],
        "evidence": closing_passport["evidence"],
        "attestation": closing_passport["attestation"],
        "privacy_note": "This export contains extracted facts and status metadata only. It excludes raw bank statements, passports, contracts, and personal data.",
    }


@app.get("/api/scenarios")
def get_scenarios() -> dict[str, object]:
    try:
        return {"data_classification": "synthetic_demo_data", "scenarios": list_scenarios()}
    except DataLoadError as exc:
        logger.error("Scenario list failed: %s", exc)
        raise _data_unavailable_http() from exc


@app.get("/api/scenarios/{scenario_id}/run")
def run_synthetic_scenario(scenario_id: str) -> dict[str, object]:
    try:
        result = run_scenario(scenario_id)
    except DataLoadError as exc:
        logger.error("Scenario run failed: %s", exc)
        raise _data_unavailable_http() from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return result


@app.get("/api/scenarios/{scenario_id}/rag-run")
def run_synthetic_scenario_with_rag(scenario_id: str, mode: str = "auto") -> dict[str, object]:
    try:
        result = run_scenario_with_rag(scenario_id, mode=mode)
    except DataLoadError as exc:
        logger.error("Scenario RAG run failed: %s", exc)
        raise _data_unavailable_http() from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return result


@app.get("/api/scenarios/{scenario_id}")
def get_synthetic_scenario(scenario_id: str) -> dict[str, object]:
    try:
        detail = get_scenario_detail(scenario_id)
    except DataLoadError as exc:
        logger.error("Scenario detail failed: %s", exc)
        raise _data_unavailable_http() from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return detail


@app.get("/api/rag/health")
def get_rag_health() -> dict[str, object]:
    return rag_health()


@app.post("/api/rag/ingest")
def post_rag_ingest(dry_run: bool = False) -> dict[str, object]:
    return ingest_synthetic_documents(dry_run=dry_run)


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


# ---- Farcaster Frame --------------------------------------------------------

from fastapi import Request  # noqa: E402  (top-level import is fine but localised here)
from fastapi.responses import HTMLResponse, Response  # noqa: E402

from app.services.farcaster_frame import frame_html, status_svg  # noqa: E402


def _base_url(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


def _basescan_link_for_deal(deal_id: str | None) -> str:
    if not deal_id:
        return "https://base-sepolia.easscan.org/"
    return f"https://base-sepolia.easscan.org/attestation/view/{deal_id}"


@app.get("/api/frame/attest", response_class=HTMLResponse)
def frame_attest(request: Request, deal_id: str | None = None, decision: str | None = None) -> HTMLResponse:
    """Farcaster Frame entry point — renders status meta tags + SVG image."""
    base = _base_url(request)
    img_q = f"?deal_id={deal_id}" if deal_id else ""
    if decision:
        sep = "&" if img_q else "?"
        img_q += f"{sep}decision={decision}"
    image_url = f"{base}/api/frame/image{img_q}"
    post_url = f"{base}/api/frame/attest"
    return HTMLResponse(
        content=frame_html(
            image_url=image_url,
            post_url=post_url,
            button_2_link=_basescan_link_for_deal(deal_id),
        )
    )


@app.post("/api/frame/attest", response_class=HTMLResponse)
def frame_attest_post(request: Request) -> HTMLResponse:
    """Button-click handler — for the hackathon demo we just bounce back to GET."""
    return frame_attest(request)


@app.get("/api/frame/image")
def frame_image(deal_id: str | None = None, decision: str | None = None) -> Response:
    """Serve the dynamically rendered Frame status SVG."""
    svg = status_svg(decision=decision, deal_id=deal_id)
    return Response(content=svg, media_type="image/svg+xml")
