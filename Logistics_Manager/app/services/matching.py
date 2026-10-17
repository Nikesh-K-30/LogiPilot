from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Sequence

from app.config import Settings, get_settings
from app.db import Database, get_db
from app.schemas import (
    CapacityUtilization,
    CargoClass,
    ConsolidationSavings,
    MatchProposal,
    Shipment,
    Vehicle,
)
from app.services.geo import road_distance_km


DEFAULT_WEIGHTS = {
    "incremental_km": 0.30,
    "deadline_slack": 0.15,
    "incremental_cost": 0.20,
    "utilization": 0.15,
    "avoided_savings": 0.20,
}

# food may not share a trailer with hazardous cargo
_INCOMPATIBLE_CARGO = {frozenset({CargoClass.food, CargoClass.hazardous})}


def _loc_coords(db: Database, location_id: str) -> tuple[float, float]:
    loc = db.get_location(location_id)
    if loc is None:
        raise ValueError(f"LOCATION_NOT_FOUND:{location_id}")
    return loc["latitude"], loc["longitude"]


def _corridor_path(db: Database, vehicle: Vehicle) -> list[str]:
    route = db.get_route(vehicle_id=vehicle.vehicle_id)
    if route is None:
        return [vehicle.current_location_id]
    return [route.depot_id] + list(route.stop_location_ids)


def _path_distance(db: Database, path: Sequence[str], road_factor: float) -> float:
    if len(path) < 2:
        return 0.0
    total = 0.0
    for a, b in zip(path, path[1:]):
        la, lo = _loc_coords(db, a)
        lb, ln = _loc_coords(db, b)
        total += road_distance_km(la, lo, lb, ln, road_factor)
    return round(total, 3)


def _best_insertion(
    db: Database,
    corridor: list[str],
    origin: str,
    destination: str,
    road_factor: float,
) -> tuple[list[str], float]:
    """Insert origin then destination into corridor with minimal detour.

    If origin/destination already on corridor, reuse those nodes (no duplicate).
    """
    base = _path_distance(db, corridor, road_factor)
    best_path = corridor[:]
    best_detour = float("inf")

    # Candidate paths: insert origin at i, destination at j > i (or same node reuse)
    n = len(corridor)

    def insert_unique(path: list[str], idx: int, node: str) -> list[str]:
        if node in path:
            return path[:]
        out = path[:]
        out.insert(idx, node)
        return out

    for i in range(n + 1):
        path_o = insert_unique(corridor, i, origin)
        # find origin index after insert
        oi = path_o.index(origin)
        for j in range(oi, len(path_o) + 1):
            path_od = insert_unique(path_o, j, destination)
            # destination must be at or after origin
            if path_od.index(destination) < path_od.index(origin):
                continue
            dist = _path_distance(db, path_od, road_factor)
            detour = dist - base
            if detour < best_detour:
                best_detour = detour
                best_path = path_od

    if best_detour == float("inf"):
        return corridor[:], 0.0
    return best_path, round(max(0.0, best_detour), 3)



def _cargo_compatible(onboard: CargoClass, incoming: CargoClass) -> bool:
    return frozenset({onboard, incoming}) not in _INCOMPATIBLE_CARGO


def _utilization(vehicle: Vehicle, extra_kg: float = 0.0, extra_m3: float = 0.0) -> CapacityUtilization:
    kg = (vehicle.used_capacity_kg + extra_kg) / vehicle.capacity_kg if vehicle.capacity_kg else 0.0
    m3 = (vehicle.used_capacity_m3 + extra_m3) / vehicle.capacity_m3 if vehicle.capacity_m3 else 0.0
    return CapacityUtilization(kg=round(kg, 3), m3=round(m3, 3))


def _standalone_truck_cost(
    *,
    db: Database,
    settings: Settings,
    shipment: Shipment,
    preferred_alt_vehicle_id: str = "VEH-002",
) -> tuple[float, str | None]:
    """Cost of running a dedicated truck for this shipment alone (estimate)."""
    oa, oo = _loc_coords(db, shipment.origin_id)
    da, dn = _loc_coords(db, shipment.destination_id)
    dist = road_distance_km(oa, oo, da, dn, settings.road_factor)
    alt = db.get_vehicle(preferred_alt_vehicle_id)
    if alt is None:
        # Fallback tariff if counterfactual truck missing
        return round(8000.0 + 25.0 * dist, 2), None
    return round(alt.fixed_cost + alt.variable_cost_per_km * dist, 2), alt.vehicle_id


def _base_proposal(
    *,
    match_id: str,
    vehicle: Vehicle,
    shipment: Shipment,
    settings: Settings,
    now,
    feasible: bool,
    reasons: list[str],
    rejection_code: str | None,
    assumptions: list[str],
    **kwargs,
) -> MatchProposal:
    names = [n for n in [vehicle.primary_shipper_name, shipment.shipper_name] if n]
    return MatchProposal(
        match_id=match_id,
        vehicle_id=vehicle.vehicle_id,
        shipment_ids=[shipment.shipment_id],
        feasible=feasible,
        reasons=reasons,
        rejection_code=rejection_code,
        assumptions=assumptions,
        algorithm_version=settings.loadlink_algorithm_version,
        computed_at=now,
        ranking_weights=DEFAULT_WEIGHTS,
        data_class=settings.data_class,
        shipper_names=names,
        primary_shipper_name=vehicle.primary_shipper_name,
        cargo_classes=[vehicle.onboard_cargo_class.value, shipment.cargo_class.value],
        capacity_utilization_before=_utilization(vehicle),
        **kwargs,
    )


def _evaluate_pair(
    *,
    db: Database,
    settings: Settings,
    vehicle: Vehicle,
    shipment: Shipment,
    max_detour_km: float,
    max_detour_pct: float,
    respect_deadlines: bool,
    corridor_mode: bool,
) -> MatchProposal:
    now = datetime.now(timezone.utc)
    assumptions = [
        "haversine_distance_v1",
        f"road_factor={settings.road_factor}",
        f"avg_speed_kmh={settings.avg_speed_kmh}",
        "standalone_truck_cost=fixed+variable*direct_od",
    ]
    match_id = f"MAT-{uuid.uuid4().hex[:8]}"

    if vehicle.availability.value not in ("available", "in_transit"):
        return _base_proposal(
            match_id=match_id,
            vehicle=vehicle,
            shipment=shipment,
            settings=settings,
            now=now,
            feasible=False,
            reasons=["Vehicle not available"],
            rejection_code="VEHICLE_UNAVAILABLE",
            assumptions=assumptions,
        )

    if not _cargo_compatible(vehicle.onboard_cargo_class, shipment.cargo_class):
        return _base_proposal(
            match_id=match_id,
            vehicle=vehicle,
            shipment=shipment,
            settings=settings,
            now=now,
            feasible=False,
            reasons=[
                f"Cargo incompatible: onboard {vehicle.onboard_cargo_class.value} "
                f"cannot mix with {shipment.cargo_class.value}"
            ],
            rejection_code="CARGO_INCOMPATIBLE",
            assumptions=assumptions,
        )

    if shipment.weight_kg > vehicle.remaining_kg + 1e-9:
        return _base_proposal(
            match_id=match_id,
            vehicle=vehicle,
            shipment=shipment,
            settings=settings,
            now=now,
            feasible=False,
            reasons=[
                f"Weight {shipment.weight_kg} kg exceeds remaining capacity {vehicle.remaining_kg} kg"
            ],
            rejection_code="CAPACITY_EXCEEDED",
            assumptions=assumptions,
        )

    if shipment.volume_m3 > vehicle.remaining_m3 + 1e-9:
        return _base_proposal(
            match_id=match_id,
            vehicle=vehicle,
            shipment=shipment,
            settings=settings,
            now=now,
            feasible=False,
            reasons=[
                f"Volume {shipment.volume_m3} m3 exceeds remaining capacity {vehicle.remaining_m3} m3"
            ],
            rejection_code="CAPACITY_EXCEEDED",
            assumptions=assumptions,
        )

    reasons: list[str] = []
    corridor = _corridor_path(db, vehicle)
    base_dist = _path_distance(db, corridor, settings.road_factor)

    if corridor_mode:
        new_path, incremental_km = _best_insertion(
            db,
            corridor,
            shipment.origin_id,
            shipment.destination_id,
            settings.road_factor,
        )
        on_corridor = shipment.origin_id in corridor or shipment.destination_id in corridor
        max_allowed = max(max_detour_km, base_dist * max_detour_pct)
        if incremental_km > max_allowed + 1e-9:
            return _base_proposal(
                match_id=match_id,
                vehicle=vehicle,
                shipment=shipment,
                settings=settings,
                now=now,
                feasible=False,
                incremental_distance_km=incremental_km,
                reasons=[
                    f"Detour {incremental_km} km exceeds limit {round(max_allowed, 3)} km",
                    "Off-corridor" if not on_corridor else "Detour too large",
                ],
                rejection_code="DETOUR_EXCEEDED",
                assumptions=assumptions,
            )
        if on_corridor:
            reasons.append("Origin or destination on planned corridor")
        else:
            reasons.append("Insertable within detour limit")
        reasons.append(f"Incremental distance {incremental_km} km")
    else:
        la, lo = _loc_coords(db, vehicle.current_location_id)
        oa, oo = _loc_coords(db, shipment.origin_id)
        da, dn = _loc_coords(db, shipment.destination_id)
        incremental_km = round(
            road_distance_km(la, lo, oa, oo, settings.road_factor)
            + road_distance_km(oa, oo, da, dn, settings.road_factor),
            3,
        )
        new_path = [vehicle.current_location_id, shipment.origin_id, shipment.destination_id]
        reasons.append("Direct pickup-drop estimate (corridor_mode=false)")

    speed = settings.avg_speed_kmh
    travel_h = (base_dist + incremental_km) / speed if speed > 0 else 0
    eta = datetime.now(timezone.utc).timestamp() + travel_h * 3600
    deadline_ts = shipment.deadline.timestamp()
    slack_h = (deadline_ts - eta) / 3600
    if respect_deadlines and slack_h < 0:
        return _base_proposal(
            match_id=match_id,
            vehicle=vehicle,
            shipment=shipment,
            settings=settings,
            now=now,
            feasible=False,
            incremental_distance_km=incremental_km,
            reasons=["Delivery deadline not feasible under travel-time assumptions"],
            rejection_code="DEADLINE_INFEASIBLE",
            assumptions=assumptions,
        )
    if slack_h >= 0:
        reasons.append(f"Deadline slack ~{round(slack_h, 1)} h (estimate)")

    before = _utilization(vehicle)
    after = _utilization(vehicle, shipment.weight_kg, shipment.volume_m3)
    util = max(after.kg, after.m3)
    reasons.append("Fits remaining weight and volume capacity")
    reasons.append(
        f"Utilization {round(max(before.kg, before.m3)*100, 1)}% → {round(util*100, 1)}%"
    )

    incremental_cost = round(vehicle.variable_cost_per_km * incremental_km, 2)
    standalone_cost, avoided_vid = _standalone_truck_cost(
        db=db, settings=settings, shipment=shipment
    )
    avoided = round(max(0.0, standalone_cost - incremental_cost), 2)
    savings = ConsolidationSavings(
        standalone_truck_cost=standalone_cost,
        consolidated_incremental_cost=incremental_cost,
        avoided_truck_savings=avoided,
        currency=vehicle.currency,
        avoided_vehicle_id=avoided_vid,
        label="estimate",
        explanation=(
            f"Running a dedicated truck for {shipment.shipper_name or shipment.shipment_id} "
            f"would cost ~₹{standalone_cost:,.0f}. Consolidating onto "
            f"{vehicle.primary_shipper_name or vehicle.vehicle_id}'s truck adds ~₹{incremental_cost:,.0f}. "
            f"Estimated savings from avoiding the second truck: ₹{avoided:,.0f}."
        ),
    )
    if shipment.shipper_name and vehicle.primary_shipper_name:
        reasons.append(
            f"Share truck for {vehicle.primary_shipper_name} + {shipment.shipper_name}"
        )
    reasons.append(f"Avoided second-truck savings ~₹{avoided:,.0f} (estimate)")

    w = DEFAULT_WEIGHTS
    score = (
        w["incremental_km"] * (1.0 / (1.0 + incremental_km))
        + w["deadline_slack"] * min(1.0, max(0.0, slack_h / 48.0))
        + w["incremental_cost"] * (1.0 / (1.0 + incremental_cost))
        + w["utilization"] * util
        + w["avoided_savings"] * min(1.0, avoided / 30000.0)
    )
    rank_score = round(100.0 * score, 2)

    return _base_proposal(
        match_id=match_id,
        vehicle=vehicle,
        shipment=shipment,
        settings=settings,
        now=now,
        feasible=True,
        reasons=reasons,
        rejection_code=None,
        assumptions=assumptions + [f"inserted_path={new_path}"],
        rank_score=rank_score,
        incremental_distance_km=incremental_km,
        estimated_incremental_cost=incremental_cost,
        currency=vehicle.currency,
        capacity_utilization_after=after,
        consolidation_savings=savings,
    )



def match_shipments_to_vehicles(
    *,
    shipment_ids: list[str] | None = None,
    vehicle_ids: list[str] | None = None,
    max_detour_km: float | None = None,
    max_detour_pct: float | None = None,
    respect_deadlines: bool = True,
    allow_multi_shipment_per_vehicle: bool = True,
    corridor_mode: bool = True,
    db: Database | None = None,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    db = db or get_db()
    max_detour_km = max_detour_km if max_detour_km is not None else settings.max_detour_km
    max_detour_pct = max_detour_pct if max_detour_pct is not None else settings.max_detour_pct

    if shipment_ids:
        shipments = []
        for sid in shipment_ids:
            s = db.get_shipment(sid)
            if s is None:
                raise ValueError(f"SHIPMENT_NOT_FOUND:{sid}")
            shipments.append(s)
    else:
        shipments = db.list_unassigned_shipments()

    if vehicle_ids:
        vehicles = []
        for vid in vehicle_ids:
            v = db.get_vehicle(vid)
            if v is None:
                raise ValueError(f"VEHICLE_NOT_FOUND:{vid}")
            vehicles.append(v)
    else:
        vehicles = db.list_available_vehicles()

    proposals: list[MatchProposal] = []
    # Greedy multi-shipment: track remaining capacity per vehicle in this plan
    remaining: dict[str, tuple[float, float]] = {
        v.vehicle_id: (v.remaining_kg, v.remaining_m3) for v in vehicles
    }
    claimed_shipments: set[str] = set()

    for shipment in shipments:
        best: MatchProposal | None = None
        for vehicle in vehicles:
            # Temporarily adjust remaining for evaluation
            rem_kg, rem_m3 = remaining[vehicle.vehicle_id]
            patched = vehicle.model_copy(
                update={
                    "used_capacity_kg": vehicle.capacity_kg - rem_kg,
                    "used_capacity_m3": vehicle.capacity_m3 - rem_m3,
                }
            )
            prop = _evaluate_pair(
                db=db,
                settings=settings,
                vehicle=patched,
                shipment=shipment,
                max_detour_km=max_detour_km,
                max_detour_pct=max_detour_pct,
                respect_deadlines=respect_deadlines,
                corridor_mode=corridor_mode,
            )
            if not prop.feasible:
                proposals.append(prop)
                continue
            if shipment.shipment_id in claimed_shipments and allow_multi_shipment_per_vehicle:
                # still report but won't claim twice
                pass
            if best is None or (prop.rank_score or 0) > (best.rank_score or 0):
                best = prop
        if best and best.feasible:
            proposals.append(best)
            if allow_multi_shipment_per_vehicle and shipment.shipment_id not in claimed_shipments:
                rem_kg, rem_m3 = remaining[best.vehicle_id]
                remaining[best.vehicle_id] = (
                    rem_kg - shipment.weight_kg,
                    rem_m3 - shipment.volume_m3,
                )
                claimed_shipments.add(shipment.shipment_id)

    feasible = [p for p in proposals if p.feasible]
    infeasible = [p for p in proposals if not p.feasible]
    feasible.sort(key=lambda p: p.rank_score or 0, reverse=True)

    # Deduplicate infeasible noise: keep one rejection per shipment-vehicle from last eval
    # Prefer unique shipment-vehicle keys
    seen_keys: set[str] = set()
    unique_infeasible: list[MatchProposal] = []
    for p in infeasible:
        key = f"{p.vehicle_id}:{','.join(p.shipment_ids)}:{p.rejection_code}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_infeasible.append(p)

    total_savings = sum(
        (p.consolidation_savings.avoided_truck_savings if p.consolidation_savings else 0.0)
        for p in feasible
    )
    shipper_pairs = []
    for p in feasible:
        if p.shipper_names:
            shipper_pairs.append(" + ".join(dict.fromkeys(p.shipper_names)))
    payload = {
        "feasible_matches": [p.model_dump(mode="json") for p in feasible],
        "rejected": [p.model_dump(mode="json") for p in unique_infeasible],
        "algorithm_version": settings.loadlink_algorithm_version,
        "ranking_weights": DEFAULT_WEIGHTS,
        "data_class": settings.data_class,
        "opportunities_summary": {
            "count": len(feasible),
            "total_avoided_truck_savings": round(total_savings, 2),
            "currency": settings.currency,
            "shipper_combinations": shipper_pairs,
            "label": "estimate",
        },
    }
    input_hash = hashlib.sha256(
        json.dumps(
            {
                "shipment_ids": [s.shipment_id for s in shipments],
                "vehicle_ids": [v.vehicle_id for v in vehicles],
                "max_detour_km": max_detour_km,
                "max_detour_pct": max_detour_pct,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]
    run_id = db.save_match_run(
        input_hash=input_hash,
        algorithm_version=settings.loadlink_algorithm_version,
        payload=payload,
    )
    payload["run_id"] = run_id
    payload["input_hash"] = input_hash
    return payload


def estimate_match_cost(
    *,
    vehicle_id: str,
    shipment_id: str,
    db: Database | None = None,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    db = db or get_db()
    vehicle = db.get_vehicle(vehicle_id)
    shipment = db.get_shipment(shipment_id)
    if vehicle is None:
        raise ValueError("VEHICLE_NOT_FOUND")
    if shipment is None:
        raise ValueError("SHIPMENT_NOT_FOUND")
    prop = _evaluate_pair(
        db=db,
        settings=settings,
        vehicle=vehicle,
        shipment=shipment,
        max_detour_km=settings.max_detour_km,
        max_detour_pct=settings.max_detour_pct,
        respect_deadlines=True,
        corridor_mode=True,
    )
    return prop.model_dump(mode="json")
