
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api import app
from app.config import get_settings
from app.db import reset_db_singleton
from database.seed import seed


def test_create_shipment_and_negotiate(tmp_path, monkeypatch):
    path = tmp_path / "ui.db"
    monkeypatch.setenv("LOGIPILOT_DATABASE_PATH", str(path))
    monkeypatch.setenv("LOGIPILOT_ENV", "development")
    monkeypatch.setenv("LOGIPILOT_APPROVAL_SECRET", "test-secret")
    get_settings.cache_clear()
    reset_db_singleton()
    seed(reset=True)

    client = TestClient(app)
    locs = client.get("/api/locations")
    assert locs.status_code == 200
    assert len(locs.json()) >= 5

    deadline = (datetime.now(timezone.utc) + timedelta(days=4)).isoformat()
    created = client.post(
        "/shipments",
        json={
            "origin_id": "LOC-HYD",
            "destination_id": "LOC-MAA",
            "weight_kg": 500,
            "volume_m3": 1.0,
            "deadline": deadline,
            "shipper_name": "TestShipper",
            "cargo_class": "food",
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["event"] == "NEW_SHIPMENT"
    sid = created.json()["shipment"]["shipment_id"]

    ov = client.get("/api/overview?advance=false")
    assert ov.status_code == 200
    body = ov.json()
    assert any(s["shipment_id"] == sid for s in body["unassigned_shipments"])
    assert body.get("agent_activity")
    assert "recommendation" in body

    chat = client.post("/chat", json={"message": "Why this plan?"})
    assert chat.status_code == 200
    assert chat.json()["answer"]

    neg = client.post("/api/what-if", json={"prioritize": "carbon", "allow_delay_hours": 2})
    assert neg.status_code == 200
    assert "activity" in neg.json()

    get_settings.cache_clear()
    reset_db_singleton()
