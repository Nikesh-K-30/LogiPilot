from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import get_db, reset_db_singleton
from app.schemas import (
    AssignRequest,
    ChatRequest,
    ChatResponse,
    CreateShipmentRequest,
    CreateVehicleRequest,
    MatchRequest,
    OptimizeRouteRequest,
    WhatIfRequest,
)
from app.services.approval import issue_approval_token, verify_approval_token
from app.services import matching, routing
from app.services.fleet import list_fleet_live, tick_fleet
from app.services.overview import build_overview
from app.services.chat_service import handle_chat
from app.services.negotiation import run_negotiation
from app.services.capacity_profile import build_capacity_profile
from database.seed import seed


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.use_sample_data and not settings.database_path.exists():
        seed(reset=True)
    yield


app = FastAPI(
    title="LogiPilot AI",
    description="LoadLink pooling + RouteWise optimization API",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATIC = Path(__file__).resolve().parent / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/admin")
def admin_page() -> FileResponse:
    return FileResponse(_STATIC / "admin.html")


@app.get("/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    db_ok = settings.database_path.exists()
    return {
        "ok": db_ok,
        "env": settings.env,
        "database": str(settings.database_path),
        "data_class": settings.data_class,
        "modules": ["loadlink", "routewise"],
    }


@app.get("/api/overview")
def api_overview(advance: bool = True) -> dict[str, Any]:
    """Full ops dashboard payload: KPIs, live fleet, opportunities."""
    return build_overview(advance_fleet=advance)


@app.get("/api/fleet/live")
def api_fleet_live(advance: bool = True) -> dict[str, Any]:
    """Simulated live GPS for all vehicles."""
    return list_fleet_live(advance=advance)


@app.post("/api/fleet/tick")
def api_fleet_tick(step_pct: float = 1.5) -> dict[str, Any]:
    """Manually advance simulated positions (for demos)."""
    updated = tick_fleet(step_pct=step_pct)
    return {"ok": True, "updated": updated, "live_mode": "simulated"}


@app.get("/api/opportunities")
def api_opportunities() -> dict[str, Any]:
    data = build_overview(advance_fleet=False)
    return {
        "opportunities": data["opportunities"],
        "rejected_preview": data["rejected_preview"],
        "kpis": data["kpis"],
        "data_class": data["data_class"],
    }


@app.post("/admin/seed")

def admin_seed(reset: bool = True) -> dict[str, Any]:
    path = seed(reset=reset)
    reset_db_singleton()
    return {"ok": True, "database": str(path), "live_mode": "simulated"}


@app.post("/loads/match")
def loads_match(body: MatchRequest) -> dict[str, Any]:
    try:
        return matching.match_shipments_to_vehicles(
            shipment_ids=body.shipment_ids,
            vehicle_ids=body.vehicle_ids,
            max_detour_km=body.max_detour_km,
            max_detour_pct=body.max_detour_pct,
            respect_deadlines=body.respect_deadlines,
            allow_multi_shipment_per_vehicle=body.allow_multi_shipment_per_vehicle,
            corridor_mode=body.corridor_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/loads/assign")
def loads_assign(body: AssignRequest) -> dict[str, Any]:
    if not verify_approval_token(
        body.approval_token,
        actor=body.actor,
        action="assign_shipment_to_vehicle",
        entity_id=body.vehicle_id,
    ):
        raise HTTPException(status_code=403, detail="APPROVAL_REQUIRED")
    try:
        return get_db().assign_shipments(
            vehicle_id=body.vehicle_id,
            shipment_ids=body.shipment_ids,
            actor=body.actor,
            rationale=body.rationale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/loads/approval-token")
def loads_approval_token(actor: str, vehicle_id: str) -> dict[str, str]:
    """Dev helper to issue an approval token. Lock down in production."""
    settings = get_settings()
    if settings.env == "production":
        raise HTTPException(status_code=404, detail="Not available in production")
    token = issue_approval_token(
        actor=actor,
        action="assign_shipment_to_vehicle",
        entity_id=vehicle_id,
    )
    return {"approval_token": token}


@app.post("/routes/optimize")
def routes_optimize(body: OptimizeRouteRequest) -> dict[str, Any]:
    try:
        result = routing.optimize_route(
            depot_id=body.depot_id,
            vehicle_id=body.vehicle_id,
            stop_location_ids=body.stop_location_ids,
            route_id=body.route_id,
            mode=body.mode,
            fuel_consumption_l_per_100km=body.fuel_consumption_l_per_100km,
            fuel_price_per_litre=body.fuel_price_per_litre,
            avg_speed_kmh=body.avg_speed_kmh,
        )
        return result.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.get("/vehicles")
def list_vehicles() -> list[dict[str, Any]]:
    out = []
    for v in get_db().list_vehicles():
        d = v.model_dump(mode="json")
        d["remaining_kg"] = v.remaining_kg
        d["remaining_m3"] = v.remaining_m3
        out.append(d)
    return out


@app.post("/vehicles")
def create_vehicle(body: CreateVehicleRequest) -> dict[str, Any]:
    """Register a new truck in the fleet (admin)."""
    try:
        result = get_db().create_vehicle(
            vehicle_id=body.vehicle_id,
            capacity_kg=body.capacity_kg,
            capacity_m3=body.capacity_m3,
            current_location_id=body.current_location_id,
            availability=body.availability.value if hasattr(body.availability, "value") else str(body.availability),
            fixed_cost=body.fixed_cost,
            variable_cost_per_km=body.variable_cost_per_km,
            currency=body.currency,
            used_capacity_kg=body.used_capacity_kg,
            used_capacity_m3=body.used_capacity_m3,
            onboard_cargo_class=body.onboard_cargo_class.value if hasattr(body.onboard_cargo_class, "value") else str(body.onboard_cargo_class),
            primary_shipper_id=body.primary_shipper_id,
            primary_shipper_name=body.primary_shipper_name,
            route_stop_ids=body.route_stop_ids,
            speed_kmh=body.speed_kmh,
            actor="user:admin",
        )
        return {"ok": True, "event": "NEW_VEHICLE", **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/vehicles/{vehicle_id}")
def get_vehicle(vehicle_id: str) -> dict[str, Any]:
    v = get_db().get_vehicle(vehicle_id)
    if v is None:
        raise HTTPException(status_code=404, detail="VEHICLE_NOT_FOUND")
    data = v.model_dump(mode="json")
    data["remaining_kg"] = v.remaining_kg
    data["remaining_m3"] = v.remaining_m3
    return data


@app.get("/vehicles/{vehicle_id}/capacity-profile")
def vehicle_capacity_profile(vehicle_id: str) -> dict[str, Any]:
    """Stop-by-stop filled / remaining capacity along the planned corridor."""
    try:
        return build_capacity_profile(vehicle_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc



@app.get("/shipments")
def list_shipments(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return [s.model_dump(mode="json") for s in get_db().list_shipments(status=status, limit=limit)]


@app.get("/routes/{route_id}")
def get_route(route_id: str) -> dict[str, Any]:
    route = get_db().get_route(route_id=route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="ROUTE_NOT_FOUND")
    return route.model_dump(mode="json")


@app.post("/chat")
def chat(body: ChatRequest) -> ChatResponse:
    """Logistics Manager copilot — Gemini when configured, else deterministic tools."""
    return handle_chat(
        body.message,
        prioritize=body.prioritize,
        allow_delay_hours=body.allow_delay_hours,
    )


@app.post("/api/negotiate")
def api_negotiate(body: WhatIfRequest = Body(default_factory=WhatIfRequest)) -> dict[str, Any]:
    return run_negotiation(
        allow_delay_hours=body.allow_delay_hours,
        prioritize=body.prioritize,
        shipment_ids=body.shipment_ids,
    )


@app.post("/api/what-if")
def api_what_if(body: WhatIfRequest) -> dict[str, Any]:
    return run_negotiation(
        allow_delay_hours=body.allow_delay_hours,
        prioritize=body.prioritize,
        shipment_ids=body.shipment_ids,
    )


@app.get("/api/locations")
def api_locations() -> list[dict[str, Any]]:
    return get_db().list_locations()


@app.post("/shipments")
def create_shipment(body: CreateShipmentRequest) -> dict[str, Any]:
    """Create an unassigned load (NEW_SHIPMENT). Triggers fresh matching on next overview."""
    try:
        ship = get_db().create_shipment(
            origin_id=body.origin_id,
            destination_id=body.destination_id,
            weight_kg=body.weight_kg,
            volume_m3=body.volume_m3,
            deadline=body.deadline,
            shipper_name=body.shipper_name,
            shipper_id=body.shipper_id,
            cargo_class=body.cargo_class.value if hasattr(body.cargo_class, "value") else str(body.cargo_class),
            shipment_id=body.shipment_id,
        )
        # Emit negotiation wake-up note
        neg = run_negotiation(shipment_ids=[ship.shipment_id])
        return {
            "ok": True,
            "shipment": ship.model_dump(mode="json"),
            "event": "NEW_SHIPMENT",
            "negotiation_preview": {
                "recommendation": neg.get("recommendation"),
                "activity_tail": (neg.get("activity") or [])[-6:],
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc




def main() -> None:
    settings = get_settings()
    uvicorn.run("app.api:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
