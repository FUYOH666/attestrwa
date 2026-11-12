"""HTTP surface of the reference attester."""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from attestrwa.canonical import CanonicalError, loads_strict
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import require_integrator
from app.config import get_settings
from app.errors import AttesterError
from app.logging_config import configure_logging
from app.schemas import AttestRequest, AttestResponse
from app.service import AttesterService

logger = logging.getLogger(__name__)

_BYTES32_RE = re.compile(r"0x[0-9a-fA-F]{64}")
MAX_RECORD_BYTES = 256 * 1024
_service: AttesterService | None = None
_service_lock = threading.Lock()


def get_service() -> AttesterService:
    """Build the service on first use, so importing the app needs no chain."""
    global _service
    with _service_lock:
        if _service is None:
            _service = AttesterService.from_settings(get_settings())
        return _service


def _cors_origins() -> list[str]:
    configured = get_settings().cors_origins
    if configured.strip():
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


def _bytes32(value: str, what: str) -> str:
    if not _BYTES32_RE.fullmatch(value):
        raise HTTPException(status_code=422, detail=f"{what} must be 0x followed by 64 hex digits")
    return value.lower()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("AttestRWA attester starting version=%s", settings.api_version)
    yield


app = FastAPI(
    title="AttestRWA attester",
    description=(
        "Reference attester for AttestRWA decision records. It reads a deal from the "
        "escrow, evaluates a versioned policy over inputs with recorded sources, stores "
        "the decision record and anchors its hash on-chain as an EAS attestation."
    ),
    version=get_settings().api_version,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.exception_handler(AttesterError)
async def attester_error_handler(_request: Request, exc: AttesterError) -> JSONResponse:
    if exc.status >= 500:
        logger.error("%s: %s", type(exc).__name__, exc)
    return JSONResponse(status_code=exc.status, content={"detail": str(exc)})


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness. Does not touch the chain."""
    return {"status": "ok", "service": "attestrwa-api"}


@app.get("/attest/healthz")
def attester_health(service: AttesterService = Depends(get_service)) -> dict[str, Any]:
    """Readiness: chain reachable, escrow wired to the schema, attester trusted."""
    return service.health()


@app.post("/attest/settlement", response_model=AttestResponse)
def attest_settlement(
    body: AttestRequest,
    caller: str = Depends(require_integrator),
    service: AttesterService = Depends(get_service),
) -> dict[str, Any]:
    """Decide about one escrowed deal and anchor the decision.

    Idempotent: while a decision for the deal is live on-chain, the stored
    record is returned and no new attestation is made.
    """
    outcome = service.attest(
        chain_id=body.chain_id,
        escrow=body.escrow,
        deal_id=body.deal_id,
        declared=dict(body.declared),
        caller=caller,
    )
    envelope = outcome.envelope
    decision = envelope["record"]["decision"]
    return {
        "deal_id": body.deal_id,
        "decision": decision["outcome"],
        "decision_code": decision["code"],
        "failed_rules": decision["failed_rules"],
        "record_hash": envelope["record_hash"],
        "attestation_uid": envelope["attestation"]["uid"],
        "tx_hash": envelope["attestation"].get("tx_hash"),
        "reused": outcome.reused,
        "envelope": envelope,
    }


@app.get("/attest/{deal_id}")
def get_decisions(deal_id: str, service: AttesterService = Depends(get_service)) -> dict[str, Any]:
    """Decisions made about a deal, with their current on-chain state."""
    return service.lookup(_bytes32(deal_id, "deal_id"))


@app.get("/records/by-hash/{record_hash}")
def get_record_by_hash(
    record_hash: str, service: AttesterService = Depends(get_service)
) -> dict[str, Any]:
    envelope = service.record_by_hash(_bytes32(record_hash, "record_hash"))
    if envelope is None:
        raise HTTPException(status_code=404, detail="no record with this hash")
    return envelope


@app.get("/records/{deal_id}")
def get_record(deal_id: str, service: AttesterService = Depends(get_service)) -> dict[str, Any]:
    """The latest decision record for a deal."""
    envelope = service.record(_bytes32(deal_id, "deal_id"))
    if envelope is None:
        raise HTTPException(status_code=404, detail="no decision recorded for this deal")
    return envelope


@app.post("/verify")
async def verify_record(
    request: Request, service: AttesterService = Depends(get_service)
) -> dict[str, Any]:
    """Run the independent verifier on a record, against this attester's chain,
    policy file and registry file. The same checks as ``attestrwa verify``.

    The body is parsed strictly: a record with duplicate keys or floats is
    ambiguous and is refused, exactly as the command line tool refuses it.
    """
    raw = await request.body()
    if len(raw) > MAX_RECORD_BYTES:
        raise HTTPException(status_code=413, detail="record is larger than 256 KB")
    try:
        document = loads_strict(raw)
    except CanonicalError as exc:
        raise HTTPException(status_code=422, detail=f"not a decision record: {exc}") from exc
    return await run_in_threadpool(service.verify, document)
