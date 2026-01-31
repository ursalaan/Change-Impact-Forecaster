from __future__ import annotations

from fastapi import FastAPI

from .engine import assess_change
from .models import ChangeInput, ForecastResult

app = FastAPI(
    title="Change Impact Forecaster",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/assess", response_model=ForecastResult)
def assess(change: ChangeInput) -> ForecastResult:
    return assess_change(change)
