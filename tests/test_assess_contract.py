from fastapi.testclient import TestClient

from cif.api import app

client = TestClient(app)


def test_assess_returns_expected_shape():
    payload = {
        "change_id": "CHG-001",
        "title": "Deploy service-a",
        "environment": "prod",
        "change_type": "deployment",
        "services_touched": ["api"],
        "out_of_hours": False,
        "rollback": {"available": True, "tested": False},
        "monitoring": {"dashboards": True, "alerts": True},
        "timing": {"day": "weekday"},
    }

    response = client.post("/assess", json=payload)
    if response.status_code != 200:
        print("STATUS:", response.status_code)
        print("BODY:", response.json())
    assert response.status_code == 200

    data = response.json()

    required_fields = [
        "risk_score",
        "risk_level",
        "confidence",
        "blast_radius",
        "factors",
        "mitigations",
        "assumptions",
        "missing_info",
        "confidence_reasons",
    ]

    for field in required_fields:
        assert field in data


def test_unknown_service_returns_422():
    payload = {
        "change_id": "CHG-001",
        "title": "Deploy service-a",
        "environment": "prod",
        "change_type": "deployment",
        "services_touched": ["not-a-real-service"],
        "out_of_hours": False,
        "rollback": {"available": True, "tested": False},
        "monitoring": {"dashboards": True, "alerts": True},
        "timing": {"day": "weekday"},
    }

    response = client.post("/assess", json=payload)
    assert response.status_code == 422