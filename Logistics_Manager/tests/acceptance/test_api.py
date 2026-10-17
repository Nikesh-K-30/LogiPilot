from fastapi.testclient import TestClient

from app.api import app
from app.config import get_settings
from app.db import reset_db_singleton
from database.seed import seed


def test_health_and_match_flow(tmp_path, monkeypatch):
    path = tmp_path / "api.db"
    monkeypatch.setenv("LOGIPILOT_DATABASE_PATH", str(path))
    monkeypatch.setenv("LOGIPILOT_ENV", "development")
    monkeypatch.setenv("LOGIPILOT_APPROVAL_SECRET", "test-secret")
    get_settings.cache_clear()
    reset_db_singleton()
    seed(reset=True)

    client = TestClient(app)
    assert client.get("/health").json()["ok"] is True

    match = client.post(
        "/loads/match",
        json={"shipment_ids": ["SHP-2001"], "vehicle_ids": ["VEH-001"]},
    )
    assert match.status_code == 200
    assert len(match.json()["feasible_matches"]) >= 1

    opt = client.post(
        "/routes/optimize",
        json={"depot_id": "LOC-MUM", "vehicle_id": "VEH-001", "route_id": "RTE-100"},
    )
    assert opt.status_code == 200
    body = opt.json()
    assert "baseline" in body and "optimized" in body

    denied = client.post(
        "/loads/assign",
        json={
            "vehicle_id": "VEH-001",
            "shipment_ids": ["SHP-2001"],
            "actor": "user:dispatcher-01",
            "approval_token": "invalid",
            "rationale": "nope",
        },
    )
    assert denied.status_code == 403

    token = client.post(
        "/loads/approval-token",
        params={"actor": "user:dispatcher-01", "vehicle_id": "VEH-001"},
    ).json()["approval_token"]
    ok = client.post(
        "/loads/assign",
        json={
            "vehicle_id": "VEH-001",
            "shipment_ids": ["SHP-2001"],
            "actor": "user:dispatcher-01",
            "approval_token": token,
            "rationale": "accepted pooling match",
        },
    )
    assert ok.status_code == 200

    chat = client.post(
        "/chat",
        json={"message": "Can we reduce costs for Chennai deliveries today?"},
    )
    assert chat.status_code == 200
    body = chat.json()
    ans = body["answer"].lower()
    assert any(k in ans for k in ("loadlink", "consolidat", "saving", "chennai", "veh-"))
    assert "₹" in body["answer"] or "inr" in ans or "save" in ans

    ov = client.get("/api/overview?advance=false")
    assert ov.status_code == 200
    assert ov.json()["live_mode"] == "simulated"
    assert "opportunities" in ov.json()
    live = client.get("/api/fleet/live?advance=true")
    assert live.status_code == 200
    assert any(v.get("latitude") is not None for v in live.json()["vehicles"])

    get_settings.cache_clear()
    reset_db_singleton()
