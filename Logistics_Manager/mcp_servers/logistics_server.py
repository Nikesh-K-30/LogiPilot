from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import get_db
from app.services import matching, routing
from app.services.approval import verify_approval_token
from app.services.geo import distance_matrix
from app.services.tool_responses import err, ok

mcp = FastMCP("logipilot-logistics")


def _dump(model: Any) -> Any:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model


@mcp.tool()
def get_shipment(shipment_id: str) -> str:
    """Get a shipment by ID."""
    ship = get_db().get_shipment(shipment_id)
    if ship is None:
        return json.dumps(err("SHIPMENT_NOT_FOUND", "No shipment exists for the requested identifier."))
    return json.dumps(ok(_dump(ship)))


@mcp.tool()
def list_shipments(status: str | None = None, limit: int = 50) -> str:
    """List shipments with optional status filter."""
    ships = get_db().list_shipments(status=status, limit=limit)
    return json.dumps(ok([_dump(s) for s in ships]))


@mcp.tool()
def list_unassigned_shipments(limit: int = 50) -> str:
    """List shipments that are not yet assigned to a vehicle."""
    ships = get_db().list_unassigned_shipments(limit=limit)
    return json.dumps(ok([_dump(s) for s in ships]))


@mcp.tool()
def get_vehicle(vehicle_id: str) -> str:
    """Get a vehicle including remaining capacity."""
    vehicle = get_db().get_vehicle(vehicle_id)
    if vehicle is None:
        return json.dumps(err("VEHICLE_NOT_FOUND", "No vehicle exists for the requested identifier."))
    data = _dump(vehicle)
    data["remaining_kg"] = vehicle.remaining_kg
    data["remaining_m3"] = vehicle.remaining_m3
    return json.dumps(ok(data))


@mcp.tool()
def list_available_vehicles(
    location_id: str | None = None,
    min_kg: float | None = None,
    min_m3: float | None = None,
) -> str:
    """List available vehicles optionally filtered by location and minimum remaining capacity."""
    vehicles = get_db().list_available_vehicles(
        location_id=location_id, min_kg=min_kg, min_m3=min_m3
    )
    out = []
    for v in vehicles:
        d = _dump(v)
        d["remaining_kg"] = v.remaining_kg
        d["remaining_m3"] = v.remaining_m3
        out.append(d)
    return json.dumps(ok(out))


@mcp.tool()
def get_route(route_id: str | None = None, vehicle_id: str | None = None) -> str:
    """Get a planned route by route_id or vehicle_id."""
    route = get_db().get_route(route_id=route_id, vehicle_id=vehicle_id)
    if route is None:
        return json.dumps(err("ROUTE_NOT_FOUND", "No route found for the requested identifier."))
    return json.dumps(ok(_dump(route)))


@mcp.tool()
def get_delivery_stops(route_id: str | None = None, stop_location_ids: list[str] | None = None) -> str:
    """Get delivery stops for a route or explicit location list."""
    db = get_db()
    if route_id:
        stops = db.get_route_stops(route_id)
    elif stop_location_ids:
        stops = db.get_delivery_stops_for_locations(None, stop_location_ids)
    else:
        return json.dumps(err("INVALID_INPUT", "Provide route_id or stop_location_ids."))
    return json.dumps(ok([_dump(s) for s in stops]))


@mcp.tool()
def get_distance_matrix(location_ids: list[str]) -> str:
    """Build a road-adjusted haversine distance matrix for location IDs."""
    from app.config import get_settings

    db = get_db()
    settings = get_settings()
    points = []
    for lid in location_ids:
        loc = db.get_location(lid)
        if loc is None:
            return json.dumps(err("LOCATION_NOT_FOUND", f"Unknown location {lid}"))
        points.append((loc["latitude"], loc["longitude"]))
    matrix = distance_matrix(points, settings.road_factor)
    return json.dumps(
        ok(
            {
                "location_ids": location_ids,
                "matrix_km": matrix,
                "method": "haversine_road_factor_v1",
                "road_factor": settings.road_factor,
                "data_class": "estimate",
            }
        )
    )


@mcp.tool()
def match_shipments_to_vehicles(
    shipment_ids: list[str] | None = None,
    vehicle_ids: list[str] | None = None,
    max_detour_km: float | None = None,
    max_detour_pct: float | None = None,
    respect_deadlines: bool = True,
    allow_multi_shipment_per_vehicle: bool = True,
    corridor_mode: bool = True,
) -> str:
    """Rank feasible vehicle-shipment matches for logistics pooling / spare capacity."""
    try:
        result = matching.match_shipments_to_vehicles(
            shipment_ids=shipment_ids,
            vehicle_ids=vehicle_ids,
            max_detour_km=max_detour_km,
            max_detour_pct=max_detour_pct,
            respect_deadlines=respect_deadlines,
            allow_multi_shipment_per_vehicle=allow_multi_shipment_per_vehicle,
            corridor_mode=corridor_mode,
        )
        return json.dumps(ok(result, source="loadlink_matching"))
    except ValueError as exc:
        code = str(exc).split(":")[0]
        return json.dumps(err(code, str(exc), source="loadlink_matching"))


@mcp.tool()
def estimate_match_cost(vehicle_id: str, shipment_id: str) -> str:
    """Estimate incremental distance and cost for one vehicle-shipment pair."""
    try:
        result = matching.estimate_match_cost(vehicle_id=vehicle_id, shipment_id=shipment_id)
        return json.dumps(ok(result, source="loadlink_matching"))
    except ValueError as exc:
        return json.dumps(err(str(exc).split(":")[0], str(exc), source="loadlink_matching"))


@mcp.tool()
def optimize_route(
    depot_id: str,
    vehicle_id: str,
    stop_location_ids: list[str] | None = None,
    route_id: str | None = None,
    mode: str = "open",
    fuel_consumption_l_per_100km: float | None = None,
    fuel_price_per_litre: float | None = None,
    avg_speed_kmh: float | None = None,
) -> str:
    """Optimize stop sequence and compare baseline vs optimized metrics."""
    try:
        result = routing.optimize_route(
            depot_id=depot_id,
            vehicle_id=vehicle_id,
            stop_location_ids=stop_location_ids,
            route_id=route_id,
            mode=mode,
            fuel_consumption_l_per_100km=fuel_consumption_l_per_100km,
            fuel_price_per_litre=fuel_price_per_litre,
            avg_speed_kmh=avg_speed_kmh,
        )
        return json.dumps(ok(_dump(result), source="routewise_routing"))
    except ValueError as exc:
        return json.dumps(err(str(exc).split(":")[0], str(exc), source="routewise_routing"))


@mcp.tool()
def compare_routes(
    depot_id: str,
    baseline_stops: list[str],
    candidate_stops: list[str],
) -> str:
    """Compare two stop sequences on the same distance assumptions."""
    try:
        result = routing.compare_routes(
            depot_id=depot_id,
            baseline_stops=baseline_stops,
            candidate_stops=candidate_stops,
        )
        return json.dumps(ok(result, source="routewise_routing"))
    except ValueError as exc:
        return json.dumps(err(str(exc).split(":")[0], str(exc), source="routewise_routing"))


@mcp.tool()
def create_match_run(
    shipment_ids: list[str] | None = None,
    vehicle_ids: list[str] | None = None,
) -> str:
    """Persist a LoadLink match proposal run (not a dispatch commit)."""
    try:
        result = matching.match_shipments_to_vehicles(
            shipment_ids=shipment_ids, vehicle_ids=vehicle_ids
        )
        return json.dumps(ok(result, source="loadlink_matching"))
    except ValueError as exc:
        return json.dumps(err(str(exc).split(":")[0], str(exc)))


@mcp.tool()
def assign_shipment_to_vehicle(
    vehicle_id: str,
    shipment_ids: list[str],
    actor: str,
    approval_token: str,
    rationale: str = "",
) -> str:
    """Commit shipment assignments. Requires a valid approval_token."""
    if not verify_approval_token(
        approval_token,
        actor=actor,
        action="assign_shipment_to_vehicle",
        entity_id=vehicle_id,
    ):
        return json.dumps(
            err(
                "APPROVAL_REQUIRED",
                "Valid approval_token required before committing assignments.",
            )
        )
    try:
        result = get_db().assign_shipments(
            vehicle_id=vehicle_id,
            shipment_ids=shipment_ids,
            actor=actor,
            rationale=rationale,
        )
        return json.dumps(ok(result, source="logistics_database"))
    except ValueError as exc:
        return json.dumps(err(str(exc).split(":")[0], str(exc)))


def main() -> None:
    # Ensure DB exists for MCP process
    from database.seed import seed
    from app.config import get_settings

    settings = get_settings()
    if not settings.database_path.exists():
        seed(reset=True)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
