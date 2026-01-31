from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request, Response

from .engine import assess_change
from .models import ChangeInput, ForecastResult


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Change Impact Forecaster")


@app.middleware("http")
async def request_timing(request: Request, call_next) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "request | method=%s path=%s status=%s duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/assess", response_model=ForecastResult)
def assess(change: ChangeInput) -> ForecastResult:
    logger.info("Assessing change %s", change.change_id)

    result = assess_change(change)

    logger.info(
        "Assessment complete | change=%s score=%s level=%s",
        result.change_id,
        result.risk_score,
        result.risk_level,
    )

    return result