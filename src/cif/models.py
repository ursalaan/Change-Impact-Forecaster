from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Environment(str, Enum):
    dev = "dev"
    staging = "staging"
    prod = "prod"


class ChangeType(str, Enum):
    config = "config"
    deployment = "deployment"
    infra = "infra"
    database = "database"
    access = "access"


class RollbackQuality(str, Enum):
    none = "none"
    partial = "partial"
    tested = "tested"


class MonitoringPlan(str, Enum):
    basic = "basic"
    strong = "strong"


class ChangeInput(BaseModel):
    change_id: str = Field(..., examples=["CHG-1024"])
    title: str = Field(..., examples=["Update auth service timeout settings"])
    change_type: ChangeType
    environment: Environment

    window_start: Optional[datetime] = Field(
        default=None, description="Planned start time (ISO 8601)."
    )
    window_end: Optional[datetime] = Field(
        default=None, description="Planned end time (ISO 8601)."
    )

    services_touched: List[str] = Field(default_factory=list, examples=[["auth", "api"]])

    deployment_method: Optional[str] = Field(
        default=None,
        examples=["manual", "pipeline", "terraform", "ansible"],
    )

    rollback_quality: RollbackQuality = RollbackQuality.partial
    monitoring_plan: MonitoringPlan = MonitoringPlan.basic

    notes: Optional[str] = Field(
        default=None,
        description="Free text. Useful for extra context, but not required.",
    )


class Factor(BaseModel):
    code: str
    message: str
    weight: int


class ForecastResult(BaseModel):
    change_id: str
    risk_score: int
    risk_level: str
    confidence: str
    blast_radius: dict
    factors: List[Factor]
    mitigations: List[str]
    assumptions: List[str]
    missing_info: List[str]
    confidence_reasons: List[str]