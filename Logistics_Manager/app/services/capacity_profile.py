"""Per-stop onboard / remaining capacity along a vehicle's planned corridor."""

from __future__ import annotations

from typing import Any

from app.db import Database, get_db
from app.schemas import ShipmentStatus


def build_capacity_profile(vehicle_id: str, *, db: Database | None = None) -> dict[str, Any]:
    """
    Simulate load along the route using assigned shipments:
    - pickup at origin adds weight/volume
    - drop at destination frees weight/volume

    Returns a stop-by-stop timeline so operators see spare space after each stop.
    """
    db = db or get_db()
    vehicle = db.get_vehicle(vehicle_id)
    if vehicle is None:
        raise ValueError("VEHICLE_NOT_FOUND")

    route = db.get_route(vehicle_id=vehicle_id)
    depot_id = route.depot_id if route else vehicle.current_location_id
    stop_ids = ([depot_id] + list(route.stop_location_ids)) if route else [vehicle.current_location_id]

    # Assigned shipments on this truck
    assigned = [
        s
        for s in db.list_shipments(limit=200)
        if s.assigned_vehicle_id == vehicle_id
        and s.status in (ShipmentStatus.assigned, ShipmentStatus.in_transit)
    ]

    # Also treat used_capacity as baseline if no shipment breakdown matches
    # Build events per location
    pickups: dict[str, list] = {lid: [] for lid in stop_ids}
    dropoffs: dict[str, list] = {lid: [] for lid in stop_ids}
    accounted_kg = 0.0
    accounted_m3 = 0.0
    for s in assigned:
        if s.origin_id not in pickups:
            pickups[s.origin_id] = []
        if s.destination_id not in dropoffs:
            dropoffs[s.destination_id] = []
        pickups.setdefault(s.origin_id, []).append(s)
        dropoffs.setdefault(s.destination_id, []).append(s)
        accounted_kg += s.weight_kg
        accounted_m3 += s.volume_m3

    # Unexplained used capacity (seed may set used_capacity without matching legs)
    unexplained_kg = max(0.0, vehicle.used_capacity_kg - accounted_kg)
    unexplained_m3 = max(0.0, vehicle.used_capacity_m3 - accounted_m3)

    # Ensure all event locations appear in sequence if missing from route
    extra = []
    for lid in list(pickups.keys()) + list(dropoffs.keys()):
        if lid not in stop_ids and lid not in extra:
            extra.append(lid)
    sequence = stop_ids + extra

    onboard_kg = unexplained_kg
    onboard_m3 = unexplained_m3
    timeline: list[dict[str, Any]] = []

    for i, lid in enumerate(sequence):
        loc = db.get_location(lid)
        name = loc["name"] if loc else lid
        events: list[dict[str, Any]] = []

        # Drops first at stop, then pickups (typical dock order)
        for s in dropoffs.get(lid, []):
            onboard_kg = max(0.0, onboard_kg - s.weight_kg)
            onboard_m3 = max(0.0, onboard_m3 - s.volume_m3)
            events.append(
                {
                    "type": "drop",
                    "shipment_id": s.shipment_id,
                    "shipper_name": s.shipper_name,
                    "weight_kg": s.weight_kg,
                    "volume_m3": s.volume_m3,
                }
            )
        for s in pickups.get(lid, []):
            onboard_kg += s.weight_kg
            onboard_m3 += s.volume_m3
            events.append(
                {
                    "type": "pickup",
                    "shipment_id": s.shipment_id,
                    "shipper_name": s.shipper_name,
                    "weight_kg": s.weight_kg,
                    "volume_m3": s.volume_m3,
                }
            )

        remaining_kg = max(0.0, vehicle.capacity_kg - onboard_kg)
        remaining_m3 = max(0.0, vehicle.capacity_m3 - onboard_m3)
        fill_pct = round(onboard_kg / vehicle.capacity_kg * 100, 1) if vehicle.capacity_kg else 0.0

        timeline.append(
            {
                "sequence": i,
                "location_id": lid,
                "location_name": name,
                "is_depot": i == 0,
                "events": events,
                "onboard_kg": round(onboard_kg, 1),
                "onboard_m3": round(onboard_m3, 2),
                "remaining_kg": round(remaining_kg, 1),
                "remaining_m3": round(remaining_m3, 2),
                "fill_pct": fill_pct,
            }
        )

    return {
        "vehicle_id": vehicle_id,
        "capacity_kg": vehicle.capacity_kg,
        "capacity_m3": vehicle.capacity_m3,
        "used_capacity_kg": vehicle.used_capacity_kg,
        "used_capacity_m3": vehicle.used_capacity_m3,
        "remaining_kg": vehicle.remaining_kg,
        "remaining_m3": vehicle.remaining_m3,
        "fill_pct_now": round(
            vehicle.used_capacity_kg / vehicle.capacity_kg * 100, 1
        )
        if vehicle.capacity_kg
        else 0.0,
        "primary_shipper_name": vehicle.primary_shipper_name,
        "route_id": route.route_id if route else None,
        "assigned_shipments": [
            {
                "shipment_id": s.shipment_id,
                "shipper_name": s.shipper_name,
                "origin_id": s.origin_id,
                "destination_id": s.destination_id,
                "weight_kg": s.weight_kg,
                "volume_m3": s.volume_m3,
            }
            for s in assigned
        ],
        "unexplained_baseline_kg": round(unexplained_kg, 1),
        "timeline": timeline,
        "note": (
            "Fill after each stop assumes pickups at origin and drops at destination "
            "for assigned shipments. Unexplained baseline is used capacity not tied to shipment legs."
        ),
    }
