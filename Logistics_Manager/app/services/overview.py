from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.db import Database, get_db
from app.services import matching
from app.services.fleet import list_fleet_live, route_polylines
from app.services.negotiation import run_negotiation


def build_overview(*, advance_fleet: bool = True, db: Database | None = None) -> dict[str, Any]:
    """Ops dashboard payload: KPIs, live fleet, ranked opportunities."""
    settings = get_settings()
    db = db or get_db()
    fleet = list_fleet_live(advance=advance_fleet, db=db, settings=settings)
    match = matching.match_shipments_to_vehicles(db=db, settings=settings)
    negotiation = run_negotiation(db=db, settings=settings)
    feasible = match.get("feasible_matches", [])
    summary = match.get("opportunities_summary", {})

    total_savings = float(summary.get("total_avoided_truck_savings") or 0)
    standalone_total = sum(
        float((m.get("consolidation_savings") or {}).get("standalone_truck_cost") or 0)
        for m in feasible
    )
    pct_saved = round((total_savings / standalone_total) * 100, 1) if standalone_total > 0 else 0.0

    unassigned = db.list_unassigned_shipments(limit=100)
    vehicles = fleet["vehicles"]
    in_transit = sum(1 for v in vehicles if v["availability"] == "in_transit")
    avg_util = (
        round(sum(v["utilization_pct"] for v in vehicles) / len(vehicles), 1) if vehicles else 0.0
    )

    opportunities = []
    for m in feasible:
        sav = m.get("consolidation_savings") or {}
        before = m.get("capacity_utilization_before") or {}
        after = m.get("capacity_utilization_after") or {}
        stand = float(sav.get("standalone_truck_cost") or 0)
        avoided = float(sav.get("avoided_truck_savings") or 0)
        legs = []
        for sid in m.get("shipment_ids") or []:
            ship = db.get_shipment(sid)
            if ship:
                legs.append(f"{ship.origin_id}→{ship.destination_id}")
        opportunities.append(
            {
                "match_id": m.get("match_id"),
                "vehicle_id": m.get("vehicle_id"),
                "shipment_ids": m.get("shipment_ids"),
                "shippers": m.get("shipper_names") or [],
                "title": " + ".join(dict.fromkeys(m.get("shipper_names") or []))
                or ",".join(m.get("shipment_ids") or []),
                "route_legs": legs,
                "rank_score": m.get("rank_score"),
                "incremental_km": m.get("incremental_distance_km"),
                "savings_inr": avoided,
                "pct_cost_saved": round((avoided / stand) * 100, 1) if stand else 0.0,
                "utilization_before_pct": round(max(before.get("kg") or 0, before.get("m3") or 0) * 100, 1),
                "utilization_after_pct": round(max(after.get("kg") or 0, after.get("m3") or 0) * 100, 1),
                "reasons": m.get("reasons") or [],
                "explanation": sav.get("explanation"),
                "currency": m.get("currency") or "INR",
            }
        )

    rejected_preview = [
        {
            "shipment_ids": r.get("shipment_ids"),
            "vehicle_id": r.get("vehicle_id"),
            "code": r.get("rejection_code"),
            "reasons": r.get("reasons"),
            "shippers": r.get("shipper_names"),
        }
        for r in match.get("rejected", [])[:8]
    ]

    return {
        "kpis": {
            "active_vehicles": len(vehicles),
            "vehicles_in_transit": in_transit,
            "open_shipments": len(unassigned),
            "opportunities": len(opportunities),
            "estimated_savings_inr": round(total_savings, 2),
            "pct_cost_saved": pct_saved,
            "avg_fleet_utilization_pct": avg_util,
            "currency": "INR",
            "label": "estimate",
        },
        "fleet": fleet,
        "routes": route_polylines(db),
        "opportunities": opportunities,
        "rejected_preview": rejected_preview,
        "unassigned_shipments": [
            {
                "shipment_id": s.shipment_id,
                "shipper_name": s.shipper_name,
                "origin_id": s.origin_id,
                "destination_id": s.destination_id,
                "weight_kg": s.weight_kg,
                "cargo_class": s.cargo_class.value if hasattr(s.cargo_class, "value") else s.cargo_class,
                "deadline": s.deadline.isoformat(),
            }
            for s in unassigned
        ],
        "data_class": settings.data_class,
        "live_mode": "simulated",
        "agent_activity": negotiation.get("activity", []),
        "recommendation": negotiation.get("recommendation"),
        "how_it_works": [
            "LoadLink finds shipments that fit spare capacity on trucks already on the road.",
            "It checks weight, volume, deadlines, detour limits, and cargo compatibility.",
            "Savings compare consolidating onto one truck vs running a second dedicated truck.",
            "RouteWise can re-sequence stops after you accept a match.",
            "Map positions are simulated live GPS for the demo — labeled as such.",
            "Company operator agents negotiate; Compliance blocks invalid merges; you approve commits.",
        ],
        "locations": db.list_locations(),
    }
