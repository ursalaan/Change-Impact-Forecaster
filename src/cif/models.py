from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


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

    window_start: Optional[datetime] = Field(default=None)
    window_end: Optional[datetime] = Field(default=None)

    services_touched: List[str] = Field(default_factory=list)

    deployment_method: Optional[str] = None

    rollback_quality: RollbackQuality = RollbackQuality.partial
    monitoring_plan: MonitoringPlan = MonitoringPlan.basic

    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_change(self):
        if not self.services_touched:
            raise ValueError("services_touched must contain at least one service")

        if self.window_start and self.window_end and self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")

        if len(self.services_touched) > 10:
            raise ValueError("Too many services in a single change; consider splitting it")

        return self


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
