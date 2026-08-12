from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok"
    }


def test_text_analysis():
    test_text = (
        "Singapore is introducing "
        "a new $500 tax next week."
    )

    response = client.post(
        "/analysis/text",
        json={
            "text": test_text
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["extracted_claim"] == test_text
    assert data["concern_label"] == "Needs Caution"
    assert data["misinformation_risk_score"] == 50
    assert data["uncertainty"] == "High"
    assert data["result_id"]
    assert data["evidence"] == []