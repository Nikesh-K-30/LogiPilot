from fastapi.testclient import TestClient

from app.api import app
from app.config import get_settings
from app.db import reset_db_singleton
from database.seed import seed


def test_create_vehicle_and_admin_page(tmp_path, monkeypatch):
    path = tmp_path / "admin.db"
    monkeypatch.setenv("LOGIPILOT_DATABASE_PATH", str(path))
    monkeypatch.setenv("LOGIPILOT_ENV", "development")
    monkeypatch.setenv("LOGIPILOT_APPROVAL_SECRET", "test-secret")
    get_settings.cache_clear()
    reset_db_singleton()
    seed(reset=True)

    client = TestClient(app)
    assert client.get("/admin").status_code == 200

    before = client.get("/vehicles").json()
    n = len(before)

    created = client.post(
        "/vehicles",
        json={
            "capacity_kg": 6000,
            "capacity_m3": 18,
            "current_location_id": "LOC-BLR",
            "availability": "available",
            "primary_shipper_name": "AdminFleet Co",
            "onboard_cargo_class": "general",
            "route_stop_ids": ["LOC-MAA"],
            "fixed_cost": 4000,
            "variable_cost_per_km": 18,
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["ok"] is True
    assert body["event"] == "NEW_VEHICLE"
    assert body["route_id"]
    vid = body["vehicle_id"]

    after = client.get("/vehicles").json()
    assert len(after) == n + 1
    assert any(v["vehicle_id"] == vid for v in after)

    live = client.get("/api/fleet/live?advance=false").json()
    assert any(v["vehicle_id"] == vid and v.get("latitude") is not None for v in live["vehicles"])

    get_settings.cache_clear()
    reset_db_singleton()
