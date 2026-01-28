from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

app = FastAPI(title="Change Impact Forecaster")


class ChangeInput(BaseModel):
    change_id: str
    change_type: str
    environment: str
    change_summary: str
    deployment_method: str
    affected_components: List[str]


@app.post("/assess")
def assess_change(change: ChangeInput):
    return {
        "change_id": change.change_id,
        "risk_score": 5,
        "risk_level": "medium",
        "uncertainty": "high",
        "blast_radius": {
            "direct": change.affected_components,
            "indirect": []
        },
        "explanation": [
            "This is a placeholder assessment.",
            "Risk logic has not been implemented yet."
        ]
    }
