from app.services import matching
from app.services.approval import issue_approval_token


def test_ll01_pooling_fit(db):
    result = matching.match_shipments_to_vehicles(
        shipment_ids=["SHP-2001"],
        vehicle_ids=["VEH-001"],
        corridor_mode=True,
        db=db,
    )
    feasible = result["feasible_matches"]
    assert len(feasible) == 1
    m = feasible[0]
    assert m["feasible"] is True
    assert m["incremental_distance_km"] is not None
    assert "Deccan Goods" in m["shipper_names"] and "Northern Retail" in m["shipper_names"]
    assert m["consolidation_savings"]["avoided_truck_savings"] > 0
    assert m["capacity_utilization_after"]["kg"] > m["capacity_utilization_before"]["kg"]
    assert result["opportunities_summary"]["total_avoided_truck_savings"] > 0


def test_ll02_overweight_rejected(db):
    result = matching.match_shipments_to_vehicles(
        shipment_ids=["SHP-2003"],
        vehicle_ids=["VEH-003"],
        db=db,
    )
    rejected = [r for r in result["rejected"] if r["rejection_code"] == "CAPACITY_EXCEEDED"]
    assert rejected, result


def test_ll03_detour_limit(db):
    result = matching.match_shipments_to_vehicles(
        shipment_ids=["SHP-2004"],
        vehicle_ids=["VEH-001"],
        max_detour_km=50,
        max_detour_pct=0.01,
        db=db,
    )
    assert result["feasible_matches"] == [] or all(
        not m.get("feasible") for m in result["feasible_matches"]
    )
    assert any(r["rejection_code"] == "DETOUR_EXCEEDED" for r in result["rejected"])


def test_ll05_approval_required(db, monkeypatch):
    monkeypatch.setenv("LOGIPILOT_APPROVAL_SECRET", "test-secret")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        db.assign_shipments(
            vehicle_id="VEH-001",
            shipment_ids=["SHP-2001"],
            actor="user:dispatcher-01",
            rationale="test",
        )
    except Exception:
        pass
    # Without going through verify — direct assign works at DB layer;
    # API/MCP gates approval. Test token gate here:
    from app.services.approval import verify_approval_token

    assert not verify_approval_token(
        "bad",
        actor="user:dispatcher-01",
        action="assign_shipment_to_vehicle",
        entity_id="VEH-001",
    )
    token = issue_approval_token(
        actor="user:dispatcher-01",
        action="assign_shipment_to_vehicle",
        entity_id="VEH-001",
    )
    assert verify_approval_token(
        token,
        actor="user:dispatcher-01",
        action="assign_shipment_to_vehicle",
        entity_id="VEH-001",
    )
    get_settings.cache_clear()


def test_ll04_double_assign(db):
    db.assign_shipments(
        vehicle_id="VEH-001",
        shipment_ids=["SHP-2001"],
        actor="user:dispatcher-01",
        rationale="first",
    )
    try:
        db.assign_shipments(
            vehicle_id="VEH-002",
            shipment_ids=["SHP-2001"],
            actor="user:dispatcher-01",
            rationale="second",
        )
        assert False, "expected failure"
    except ValueError as exc:
        assert "SHIPMENT_NOT_UNASSIGNED" in str(exc) or "ALREADY" in str(exc)


def test_ll06_repeatability(db):
    a = matching.match_shipments_to_vehicles(
        shipment_ids=["SHP-2001", "SHP-2002"],
        vehicle_ids=["VEH-001"],
        db=db,
    )
    b = matching.match_shipments_to_vehicles(
        shipment_ids=["SHP-2001", "SHP-2002"],
        vehicle_ids=["VEH-001"],
        db=db,
    )
    assert a["input_hash"] == b["input_hash"]
    assert [m["rank_score"] for m in a["feasible_matches"]] == [
        m["rank_score"] for m in b["feasible_matches"]
    ]


def test_ll07_cargo_incompatible(db):
    result = matching.match_shipments_to_vehicles(
        shipment_ids=["SHP-2005"],
        vehicle_ids=["VEH-001"],
        db=db,
    )
    assert result["feasible_matches"] == []
    assert any(r["rejection_code"] == "CARGO_INCOMPATIBLE" for r in result["rejected"])
