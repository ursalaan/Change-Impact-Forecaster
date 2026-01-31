from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException

from .models import ChangeInput, Factor, ForecastResult


def _dependency_graph_path() -> Path:
    """
    Resolve data/dependencies.yaml reliably regardless of the current working directory.
    Assumes repo layout:
      <repo_root>/data/dependencies.yaml
      <repo_root>/src/cif/engine.py
    """
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "data" / "dependencies.yaml"


def load_dependency_graph() -> dict[str, dict[str, Any]]:
    path = _dependency_graph_path()
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
        # Expected shape: { service_name: { depends_on: [..] } }
        if not isinstance(data, dict):
            return {}
        return data  # type: ignore[return-value]


def known_services(graph: dict[str, dict[str, Any]]) -> set[str]:
    return set(graph.keys())


def find_indirect_services(
    direct_services: list[str],
    graph: dict[str, dict[str, Any]],
) -> list[str]:
    """
    Finds downstream services that depend on the services being changed.
    """
    impacted: set[str] = set()
    q: deque[str] = deque(direct_services)

    while q:
        current = q.popleft()

        for service, meta in graph.items():
            deps = meta.get("depends_on", [])
            if current in deps and service not in impacted:
                impacted.add(service)
                q.append(service)

    return sorted(impacted)


def is_risky_window(window_start: datetime | None, environment: str) -> bool:
    """
    Risky if weekend or outside 08:00–18:00 (prod only).
    """
    if environment != "prod" or window_start is None:
        return False

    # Monday=0 ... Sunday=6
    if window_start.weekday() >= 5:
        return True

    hour = window_start.hour
    return hour < 8 or hour >= 18


def confidence_level(change: ChangeInput, indirect_services: list[str]) -> str:
    """
    Confidence reflects completeness/quality of info, not riskiness.
    """
    points = 0

    # Change window
    if change.window_start is not None:
        points += 1

    # Rollback quality
    rollback = change.rollback_quality.value
    if rollback == "tested":
        points += 2
    elif rollback == "partial":
        points += 1

    # Monitoring plan
    monitoring = change.monitoring_plan.value
    if monitoring == "strong":
        points += 2
    else:
        points += 1

    # Smaller blast radius is easier to reason about
    indirect_count = len(indirect_services)
    if indirect_count == 0:
        points += 2
    elif indirect_count <= 2:
        points += 1

    if points >= 7:
        return "high"
    if points >= 4:
        return "medium"
    return "low"


def _risk_level(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def assess_change(change: ChangeInput) -> ForecastResult:
    """
    v0.1 scoring: deterministic, explainable rules.
    Designed to support decision-making, not "predict outages".
    """
    score = 0
    graph = load_dependency_graph()

    known = known_services(graph)
    unknown = [s for s in change.services_touched if s not in known]

    if unknown:
        unknown_list = ", ".join(sorted(unknown))
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unknown_service",
                "message": f"One or more services are not in the dependency graph: {unknown_list}.",
                "known_services": sorted(known),
                "hint": "Check data/dependencies.yaml or fix the service name in services_touched.",
            },
        )

    indirect_services = find_indirect_services(change.services_touched, graph)

    factors: list[Factor] = []
    mitigations: list[str] = []

    assumptions: list[str] = [
        "Service dependencies are loaded from data/dependencies.yaml.",
        "Blast radius is estimated using direct + downstream dependencies.",
    ]
    missing_info: list[str] = []
    confidence_reasons: list[str] = []

    env = change.environment.value

    # Production changes carry more baseline risk (impact + recovery complexity).
    if env == "prod":
        score += 30
        factors.append(Factor(code="ENV_PROD", message="Production change", weight=30))
        mitigations.append("Make sure rollback steps are written and tested before starting.")

    # Weekend/out-of-hours changes are harder to support (staffing + escalation).
    if is_risky_window(change.window_start, env):
        score += 10
        factors.append(Factor(code="RISKY_WINDOW", message="Scheduled out-of-hours or on a weekend", weight=10))
        mitigations.append("If possible, schedule during staffed hours or add extra on-call cover.")

    if change.window_start is None:
        missing_info.append("window_start not provided")
    else:
        confidence_reasons.append("change window specified")

    # Change type weighting (rough but consistent).
    type_weights = {
        "config": 10,
        "deployment": 15,
        "infra": 25,
        "database": 30,
        "access": 20,
    }
    change_type = change.change_type.value
    w = type_weights.get(change_type, 10)
    score += w
    factors.append(Factor(code="TYPE", message=f"Change type: {change_type}", weight=w))

    # Touching many services widens coordination and failure surface area.
    if len(change.services_touched) >= 3:
        score += 15
        factors.append(Factor(code="SVC_MANY", message="Touches 3+ services", weight=15))
        mitigations.append("Consider splitting the change into smaller steps.")

    # Downstream impact widens blast radius further.
    if indirect_services:
        score += 10
        factors.append(
            Factor(
                code="BLAST_INDIRECT",
                message=f"Indirectly impacts {len(indirect_services)} additional service(s)",
                weight=10,
            )
        )

    # Confidence reasons based on blast size.
    indirect_count = len(indirect_services)
    if indirect_count == 0:
        confidence_reasons.append("no indirect service impact")
    elif indirect_count <= 2:
        confidence_reasons.append("limited indirect service impact")

    # Rollback and monitoring adjust both risk and confidence.
    rollback = change.rollback_quality.value
    if rollback == "tested":
        score -= 15
        factors.append(Factor(code="RB_TESTED", message="Rollback is tested", weight=-15))
        confidence_reasons.append("rollback plan tested")
    elif rollback == "partial":
        confidence_reasons.append("rollback plan partially defined")
    elif rollback == "none":
        score += 15
        factors.append(Factor(code="RB_NONE", message="No rollback plan", weight=15))
        mitigations.append("Add at least a basic rollback plan (and validate it).")
        missing_info.append("no rollback plan")

    monitoring = change.monitoring_plan.value
    if monitoring == "strong":
        score -= 10
        factors.append(Factor(code="MON_STRONG", message="Strong monitoring plan", weight=-10))
        confidence_reasons.append("strong monitoring in place")
    else:
        mitigations.append("Add extra monitoring (dashboards/alerts) for the change window.")
        missing_info.append("monitoring plan is not strong")

    score = max(0, min(100, score))
    level = _risk_level(score)
    confidence = confidence_level(change, indirect_services)

    blast_radius = {
        "direct": change.services_touched,
        "indirect": indirect_services,
    }

    # Deduplicate mitigations while preserving order.
    seen: set[str] = set()
    mitigations_clean: list[str] = []
    for m in mitigations:
        if m not in seen:
            mitigations_clean.append(m)
            seen.add(m)

    return ForecastResult(
        change_id=change.change_id,
        risk_score=score,
        risk_level=level,
        confidence=confidence,
        blast_radius=blast_radius,
        factors=factors,
        mitigations=mitigations_clean,
        assumptions=assumptions,
        missing_info=missing_info,
        confidence_reasons=confidence_reasons,
    )