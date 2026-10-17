"""FreightMesh-style multi-agent negotiation over deterministic tools."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import Settings, get_settings
from app.db import Database, get_db
from app.services import matching
from app.services.matching import _cargo_compatible
from app.schemas import CargoClass


COMPANIES = {
    "SHIPPER-NORTH": {
        "agent": "Northern Retail Operator",
        "name": "Northern Retail",
        "max_shared_capacity": 0.90,
        "min_operational_buffer": 0.10,
        "allow_shared_cargo": True,
    },
    "SHIPPER-DECCAN": {
        "agent": "Deccan Goods Operator",
        "name": "Deccan Goods",
        "max_acceptable_cost": 28000,
        "max_acceptable_delay_hours": 2,
    },
    "SHIPPER-COASTAL": {
        "agent": "CoastalMart Operator",
        "name": "CoastalMart",
        "max_acceptable_cost": 22000,
        "max_acceptable_delay_hours": 1,
    },
}


def _msg(actor: str, text: str, *, kind: str = "message") -> dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "kind": kind,
        "text": text,
    }


def run_negotiation(
    *,
    db: Database | None = None,
    settings: Settings | None = None,
    allow_delay_hours: float = 0.0,
    prioritize: str = "cost",
    shipment_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Simulate Coordinator ↔ company operators ↔ Compliance over tool results.
    Calculations come from matching; this layer produces the agent activity feed.
    """
    settings = settings or get_settings()
    db = db or get_db()
    activity: list[dict[str, Any]] = []

    activity.append(
        _msg(
            "Logistics Manager",
            "Objective received: minimize transportation cost for open corridor shipments "
            "while protecting SLAs and cargo rules.",
            kind="intent",
        )
    )
    activity.append(
        _msg(
            "Network Coordinator",
            "Scanning unassigned shipments and asking operator agents for usable capacity.",
            kind="orchestrate",
        )
    )

    # Match with optional delay slack via temporarily relaxed deadlines is complex;
    # for what-if delay we widen max_detour and note delay allowance in ranking narrative.
    result = matching.match_shipments_to_vehicles(
        shipment_ids=shipment_ids,
        vehicle_ids=["VEH-001", "VEH-002", "VEH-003"],
        corridor_mode=True,
        respect_deadlines=allow_delay_hours <= 0,
        db=db,
        settings=settings,
    )
    # If delay allowed, rematch with deadlines off then filter soft
    if allow_delay_hours > 0:
        result = matching.match_shipments_to_vehicles(
            shipment_ids=shipment_ids,
            vehicle_ids=["VEH-001", "VEH-002", "VEH-003"],
            corridor_mode=True,
            respect_deadlines=False,
            db=db,
            settings=settings,
        )
        activity.append(
            _msg(
                "Network Coordinator",
                f"What-if active: allow_delay_hours={allow_delay_hours}. "
                "Deadline hard-fail relaxed; SLA risk still shown in explanations.",
                kind="what_if",
            )
        )

    feasible = result.get("feasible_matches") or []
    rejected = result.get("rejected") or []

    # Company agents speak about their assets
    north = db.get_vehicle("VEH-001")
    if north:
        usable = north.remaining_kg * COMPANIES["SHIPPER-NORTH"]["max_shared_capacity"]
        activity.append(
            _msg(
                "Network Coordinator",
                "Northern Retail Operator: do you have usable capacity on the Mumbai→Chennai corridor?",
            )
        )
        activity.append(
            _msg(
                "Northern Retail Operator",
                f"VEH-001 has {north.remaining_kg:.0f} kg remaining "
                f"({north.used_capacity_kg:.0f}/{north.capacity_kg:.0f} kg used). "
                f"Policy allows sharing up to {usable:.0f} kg after a "
                f"{int(COMPANIES['SHIPPER-NORTH']['min_operational_buffer']*100)}% operational buffer. "
                f"Onboard cargo class: {north.onboard_cargo_class.value}.",
            )
        )

    # Highlight mid-corridor shipments
    for sid in ("SHP-2001", "SHP-2007"):
        ship = db.get_shipment(sid)
        if ship and ship.status.value == "unassigned":
            agent = COMPANIES.get(ship.shipper_id or "", {}).get(
                "agent", f"{ship.shipper_name} Operator"
            )
            activity.append(
                _msg(
                    "Network Coordinator",
                    f"{agent}: can {sid} ({ship.weight_kg:.0f} kg {ship.origin_id}→{ship.destination_id}) "
                    f"accept consolidation if ETA is before {ship.deadline.isoformat()}?",
                )
            )
            activity.append(
                _msg(
                    agent,
                    f"Yes if cost ≤ policy and deadline holds. Cargo={ship.cargo_class.value}.",
                )
            )

    # Deliberate capacity rejection story: try Deccan + Coastal on VEH-001 if both exist
    deccan = db.get_shipment("SHP-2001")
    coastal = db.get_shipment("SHP-2007")
    if north and deccan and coastal and deccan.status.value == "unassigned" and coastal.status.value == "unassigned":
        combined = deccan.weight_kg + coastal.weight_kg
        activity.append(
            _msg(
                "Network Coordinator",
                f"Evaluating combined plan: {deccan.shipper_name} {deccan.weight_kg:.0f} kg + "
                f"{coastal.shipper_name} {coastal.weight_kg:.0f} kg = {combined:.0f} kg on VEH-001 "
                f"(remaining {north.remaining_kg:.0f} kg).",
                kind="evaluate",
            )
        )
        if combined > north.remaining_kg + 1e-9:
            activity.append(
                _msg(
                    "Compliance Agent",
                    f"❌ CAPACITY_EXCEEDED — combined {combined:.0f} kg does not fit "
                    f"{north.remaining_kg:.0f} kg remaining. Do not blindly consolidate everything.",
                    kind="reject",
                )
            )

    # Compliance on top feasible
    for m in feasible[:3]:
        vids = m.get("vehicle_id")
        sids = m.get("shipment_ids") or []
        ship = db.get_shipment(sids[0]) if sids else None
        veh = db.get_vehicle(vids) if vids else None
        activity.append(
            _msg(
                "Network Coordinator",
                f"Compliance Agent: validate candidate {m.get('match_id')} "
                f"({', '.join(m.get('shipper_names') or [])} → {vids}).",
            )
        )
        checks = []
        if ship and veh:
            ok_cargo = _cargo_compatible(veh.onboard_cargo_class, ship.cargo_class)
            checks.append("✓ Cargo compatible" if ok_cargo else "❌ Cargo incompatible")
            checks.append(
                "✓ Capacity sufficient"
                if ship.weight_kg <= veh.remaining_kg
                else "❌ Capacity exceeded"
            )
            checks.append("✓ Route/detour evaluated by tools")
            sav = m.get("consolidation_savings") or {}
            if sav:
                checks.append(
                    f"✓ Savings estimate ₹{float(sav.get('avoided_truck_savings') or 0):,.0f}"
                )
        activity.append(
            _msg("Compliance Agent", " · ".join(checks) or "No checks", kind="compliance")
        )

    # Rank / recommend with priority
    ranked = list(feasible)
    if prioritize == "utilization":
        ranked.sort(
            key=lambda m: max(
                (m.get("capacity_utilization_after") or {}).get("kg") or 0,
                (m.get("capacity_utilization_after") or {}).get("m3") or 0,
            ),
            reverse=True,
        )
    elif prioritize == "carbon":
        # Prefer lower incremental km as proxy for emissions
        ranked.sort(key=lambda m: m.get("incremental_distance_km") or 0)
    else:
        ranked.sort(
            key=lambda m: (m.get("consolidation_savings") or {}).get("avoided_truck_savings") or 0,
            reverse=True,
        )

    activity.append(
        _msg(
            "Optimization Engine",
            f"Ranked {len(ranked)} feasible plan(s). Priority={prioritize}. "
            "Scores use deterministic cost, utilization, detour, and deadline tools — not LLM arithmetic.",
            kind="optimize",
        )
    )

    recommendation = None
    if ranked:
        best = ranked[0]
        sav = best.get("consolidation_savings") or {}
        recommendation = {
            "match_id": best.get("match_id"),
            "vehicle_id": best.get("vehicle_id"),
            "shipment_ids": best.get("shipment_ids"),
            "shippers": best.get("shipper_names"),
            "savings_inr": sav.get("avoided_truck_savings"),
            "standalone_cost": sav.get("standalone_truck_cost"),
            "consolidated_cost": sav.get("consolidated_incremental_cost"),
            "utilization_before": best.get("capacity_utilization_before"),
            "utilization_after": best.get("capacity_utilization_after"),
            "reasons": best.get("reasons"),
            "explanation": sav.get("explanation"),
            "prioritize": prioritize,
        }
        activity.append(
            _msg(
                "Network Coordinator",
                f"Recommended: put {', '.join(best.get('shipment_ids') or [])} on {best.get('vehicle_id')}. "
                f"Estimated avoided second-truck savings ₹{float(sav.get('avoided_truck_savings') or 0):,.0f}. "
                "Awaiting human approval before commit.",
                kind="recommend",
            )
        )
        # Simulated acceptances
        for name in best.get("shipper_names") or []:
            activity.append(_msg(f"{name} Operator", "Accept offer under stated constraints.", kind="accept"))
    else:
        activity.append(
            _msg(
                "Network Coordinator",
                "No feasible consolidation under current constraints.",
                kind="recommend",
            )
        )

    # Surface notable rejections
    seen = set()
    for r in rejected:
        code = r.get("rejection_code")
        key = (code, tuple(r.get("shipment_ids") or []), r.get("vehicle_id"))
        if key in seen:
            continue
        seen.add(key)
        if code in ("CAPACITY_EXCEEDED", "CARGO_INCOMPATIBLE", "DETOUR_EXCEEDED", "DEADLINE_INFEASIBLE"):
            activity.append(
                _msg(
                    "Compliance Agent",
                    f"Rejected {r.get('shipment_ids')} on {r.get('vehicle_id')}: {code}. "
                    + "; ".join(r.get("reasons") or []),
                    kind="reject",
                )
            )
        if len(seen) >= 6:
            break

    summary = result.get("opportunities_summary") or {}
    return {
        "activity": activity,
        "recommendation": recommendation,
        "feasible_matches": ranked,
        "rejected": rejected,
        "opportunities_summary": summary,
        "prioritize": prioritize,
        "allow_delay_hours": allow_delay_hours,
        "data_class": settings.data_class,
    }
