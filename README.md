# Change Impact Forecaster

A FastAPI backend that assesses the **risk and impact of production changes before deployment**.

It’s designed as a lightweight change-management / SRE decision-support tool: **rule-based, explainable, and auditable** (not a “predict outages with AI” gimmick).

## Key features

- **/assess API**: accepts structured change data (environment, change type, services touched, rollback, monitoring, timing, etc.)
- **Explainable risk scoring (0–100)** with a mapped risk level (low / medium / high)
- **Dependency-aware blast radius** using a YAML service dependency graph (`data/dependencies.yaml`)
- **Auditable output**: factors + weights, confidence and reasons, mitigations, assumptions, and missing info

## Tech

Python 3.12 · FastAPI · Pydantic · PyYAML · Pytest · GitHub Actions (CI)

## Run locally

From the project root:

```bash
uvicorn cif.main:app --reload