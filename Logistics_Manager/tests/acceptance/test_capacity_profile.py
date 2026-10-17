
from fastapi.testclient import TestClient

from app.api import app
from app.config import get_settings
from app.db import reset_db_singleton
from app.services.capacity_profile import build_capacity_profile
from database.seed import seed


def test_veh001_stop_timeline(tmp_path, monkeypatch):
    path = tmp_path / "cap.db"
    monkeypatch.setenv("LOGIPILOT_DATABASE_PATH", str(path))
    get_settings.cache_clear()
    reset_db_singleton()
    seed(reset=True)

    profile = build_capacity_profile("VEH-001")
    assert profile["capacity_kg"] == 13000
    assert len(profile["timeline"]) >= 4  # depot + stops
    # After Mumbai pickups onboard should be ~8000
    mum = profile["timeline"][0]
    assert mum["onboard_kg"] >= 7900
    # After Pune drop, spare should increase
    pun = next(s for s in profile["timeline"] if s["location_id"] == "LOC-PUN")
    assert pun["remaining_kg"] > mum["remaining_kg"] - 1

    client = TestClient(app)
    r = client.get("/vehicles/VEH-001/capacity-profile")
    assert r.status_code == 200
    assert "timeline" in r.json()

    get_settings.cache_clear()
    reset_db_singleton()
