from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import HTTPException

from .models import ChangeInput, Factor, ForecastResult


def load_dependency_graph() -> dict:
    """
    Loads the service dependency graph from disk.
    Keeping this as data makes it easy to update without touching code.
    """
    path = Path("data/dependencies.yaml")
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def find_indirect_services(direct_services: list[str], graph: dict) -> list[str]:
    """
    Finds services that depend on the services being changed (downstream impact).
    """
    impacted: set[str] = set()
    queue = list(direct_services)

    while queue:
        current = queue.pop(0)

        for service, meta in graph.items():
            deps = meta.get("depends_on", [])
            if current in deps and service not in impacted:
                impacted.add(service)
                queue.append(service)

    return sorted(impacted)


def known_services(graph: dict) -> set[str]:
    return set(graph.keys())


def is_risky_window(window_start, environment: str) -> bool:
    """
    Simple time-window rule:
    - Only applies to prod
    - Risky if it's weekend or outside 08:00–18:00
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
    Confidence is about how complete the info is, not how risky the change is.
    """
    points = 0

    # Basic planning info
    if change.window_start is not None:
        points += 1

    # Rollback
    if change.rollback_quality.value == "tested":
        points += 2
    elif change.rollback_quality.value == "partial":
        points += 1

    # Monitoring
    if change.monitoring_plan.value == "strong":
        points += 2
    else:
        points += 1

    # Smaller blast radius = usually easier to reason about
    if len(indirect_services) == 0:
        points += 2
    elif len(indirect_services) <= 2:
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
    v0.1 scoring: simple, explainable rules.
    The goal is not perfect prediction yet — it's a consistent baseline.
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

    assumptions: list[str] = []
    missing_info: list[str] = []
    confidence_reasons: list[str] = []

    assumptions.append("Service dependencies are loaded from data/dependencies.yaml.")
    assumptions.append("Blast radius is estimated using direct + downstream dependencies.")

    # Production changes carry more risk by default.
    if change.environment.value == "prod":
        score += 30
        factors.append(Factor(code="ENV_PROD", message="Production change", weight=30))
        mitigations.append("Make sure rollback steps are written and tested before starting.")

    # Out-of-hours/weekend changes are harder to support.
    if is_risky_window(change.window_start, change.environment.value):
        score += 10
        factors.append(
            Factor(
                code="RISKY_WINDOW",
                message="Scheduled out-of-hours or on a weekend",
                weight=10,
            )
        )
        mitigations.append("If possible, schedule during staffed hours or add extra on-call cover.")

    if change.window_start is None:
        missing_info.append("window_start not provided")
    else:
        confidence_reasons.append("change window specified")

    # Change type rough weighting (placeholder but useful).
    type_weights = {
        "config": 10,
        "deployment": 15,
        "infra": 25,
        "database": 30,
        "access": 20,
    }
    w = type_weights.get(change.change_type.value, 10)
    score += w
    factors.append(Factor(code="TYPE", message=f"Change type: {change.change_type.value}", weight=w))

    # Touching more services tends to widen the blast radius.
    if len(change.services_touched) >= 3:
        score += 15
        factors.append(Factor(code="SVC_MANY", message="Touches 3+ services", weight=15))
        mitigations.append("Consider splitting the change into smaller steps.")

    # Indirect impact widens the blast radius further.
    if indirect_services:
        score += 10
        factors.append(
            Factor(
                code="BLAST_INDIRECT",
                message=f"Indirectly impacts {len(indirect_services)} additional service(s)",
                weight=10,
            )
        )

    # Confidence reasons based on blast size (helps explain "why medium?")
    if len(indirect_services) == 0:
        confidence_reasons.append("no indirect service impact")
    elif len(indirect_services) <= 2:
        confidence_reasons.append("limited indirect service impact")

    # Rollback and monitoring adjust risk (and should improve confidence).
    if change.rollback_quality.value == "tested":
        score -= 15
        factors.append(Factor(code="RB_TESTED", message="Rollback is tested", weight=-15))
        confidence_reasons.append("rollback plan tested")
    elif change.rollback_quality.value == "partial":
        confidence_reasons.append("rollback plan partially defined")
    elif change.rollback_quality.value == "none":
        score += 15
        factors.append(Factor(code="RB_NONE", message="No rollback plan", weight=15))
        mitigations.append("Add at least a basic rollback plan (and validate it).")
        missing_info.append("no rollback plan")

    if change.monitoring_plan.value == "strong":
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

    # Make mitigations unique and readable.
    seen = set()
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
