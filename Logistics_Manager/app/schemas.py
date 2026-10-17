from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


class ToolError(BaseModel):
    code: str
    message: str


class ToolResponse(BaseModel, Generic[T]):
    ok: bool
    data: T | None = None
    error: ToolError | None = None
    source: str = "logistics_database"
    trace_id: str | None = None
    data_class: str = "calculated"


class Availability(str, Enum):
    available = "available"
    in_transit = "in_transit"
    maintenance = "maintenance"
    unavailable = "unavailable"


class ShipmentStatus(str, Enum):
    unassigned = "unassigned"
    assigned = "assigned"
    in_transit = "in_transit"
    delivered = "delivered"
    cancelled = "cancelled"


class CargoClass(str, Enum):
    general = "general"
    food = "food"
    hazardous = "hazardous"


class Location(BaseModel):
    location_id: str
    name: str
    latitude: float
    longitude: float
    timezone: str = "Asia/Kolkata"


class Vehicle(BaseModel):
    vehicle_id: str
    capacity_kg: float
    capacity_m3: float
    current_location_id: str
    availability: Availability
    fixed_cost: float = 0.0
    variable_cost_per_km: float = 0.0
    currency: str = "INR"
    planned_route_id: str | None = None
    used_capacity_kg: float = 0.0
    used_capacity_m3: float = 0.0
    onboard_cargo_class: CargoClass = CargoClass.general
    primary_shipper_id: str | None = None
    primary_shipper_name: str | None = None

    @property
    def remaining_kg(self) -> float:
        return max(0.0, self.capacity_kg - self.used_capacity_kg)

    @property
    def remaining_m3(self) -> float:
        return max(0.0, self.capacity_m3 - self.used_capacity_m3)


class Shipment(BaseModel):
    shipment_id: str
    origin_id: str
    destination_id: str
    weight_kg: float
    volume_m3: float
    deadline: datetime
    status: ShipmentStatus
    assigned_vehicle_id: str | None = None
    shipper_id: str | None = None
    shipper_name: str | None = None
    cargo_class: CargoClass = CargoClass.general

    @field_validator("weight_kg", "volume_m3")
    @classmethod
    def non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("quantities cannot be negative")
        return v


class RouteStop(BaseModel):
    stop_id: str
    route_id: str
    location_id: str
    sequence: int
    service_duration_minutes: int = 30
    time_window_start: datetime | None = None
    time_window_end: datetime | None = None
    demand_kg: float = 0.0
    demand_m3: float = 0.0
    latitude: float | None = None
    longitude: float | None = None


class Route(BaseModel):
    route_id: str
    vehicle_id: str
    depot_id: str
    mode: str = "open"
    status: str = "planned"
    stop_location_ids: list[str] = Field(default_factory=list)


class CapacityUtilization(BaseModel):
    kg: float
    m3: float


class ConsolidationSavings(BaseModel):
    """Counterfactual: cost of a dedicated second truck vs consolidating."""

    standalone_truck_cost: float
    consolidated_incremental_cost: float
    avoided_truck_savings: float
    currency: str = "INR"
    avoided_vehicle_id: str | None = None
    label: str = "estimate"
    explanation: str = ""


class MatchProposal(BaseModel):
    match_id: str
    vehicle_id: str
    shipment_ids: list[str]
    feasible: bool
    rank_score: float | None = None
    incremental_distance_km: float | None = None
    estimated_incremental_cost: float | None = None
    currency: str = "INR"
    capacity_utilization_before: CapacityUtilization | None = None
    capacity_utilization_after: CapacityUtilization | None = None
    shipper_names: list[str] = Field(default_factory=list)
    primary_shipper_name: str | None = None
    cargo_classes: list[str] = Field(default_factory=list)
    consolidation_savings: ConsolidationSavings | None = None
    reasons: list[str] = Field(default_factory=list)
    rejection_code: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    algorithm_version: str
    computed_at: datetime
    ranking_weights: dict[str, float] | None = None
    data_class: str = "calculated"


class RouteMetrics(BaseModel):
    stop_sequence: list[str]
    distance_km: float
    duration_hours: float
    estimated_fuel_cost: float


class RouteViolation(BaseModel):
    code: str
    message: str
    stop_id: str | None = None


class FuelAssumptions(BaseModel):
    fuel_consumption_l_per_100km: float
    fuel_price_per_litre: float
    currency: str = "INR"


class RouteOptimizationResult(BaseModel):
    run_id: str
    vehicle_id: str
    depot_id: str
    feasible: bool
    baseline: RouteMetrics
    optimized: RouteMetrics
    savings: dict[str, float]
    violations: list[RouteViolation] = Field(default_factory=list)
    fuel_assumptions: FuelAssumptions
    algorithm_version: str
    computed_at: datetime
    data_class: str = "calculated"
    input_hash: str


class MatchRequest(BaseModel):
    shipment_ids: list[str] | None = None
    vehicle_ids: list[str] | None = None
    max_detour_km: float | None = None
    max_detour_pct: float | None = None
    respect_deadlines: bool = True
    allow_multi_shipment_per_vehicle: bool = True
    corridor_mode: bool = True


class OptimizeRouteRequest(BaseModel):
    depot_id: str
    stop_location_ids: list[str] | None = None
    route_id: str | None = None
    vehicle_id: str
    mode: str = "open"
    fuel_consumption_l_per_100km: float | None = None
    fuel_price_per_litre: float | None = None
    avg_speed_kmh: float | None = None


class AssignRequest(BaseModel):
    vehicle_id: str
    shipment_ids: list[str]
    actor: str
    approval_token: str
    rationale: str = ""


class CreateVehicleRequest(BaseModel):
    vehicle_id: str | None = None
    capacity_kg: float
    capacity_m3: float = 20.0
    current_location_id: str
    availability: Availability = Availability.available
    fixed_cost: float = 5000.0
    variable_cost_per_km: float = 20.0
    currency: str = "INR"
    used_capacity_kg: float = 0.0
    used_capacity_m3: float = 0.0
    onboard_cargo_class: CargoClass = CargoClass.general
    primary_shipper_id: str | None = None
    primary_shipper_name: str | None = None
    # Optional corridor stops after current location (location IDs)
    route_stop_ids: list[str] = Field(default_factory=list)
    speed_kmh: float = 0.0


class CreateShipmentRequest(BaseModel):
    origin_id: str
    destination_id: str
    weight_kg: float
    volume_m3: float = 1.0
    deadline: datetime
    shipper_id: str | None = None
    shipper_name: str
    cargo_class: CargoClass = CargoClass.general
    shipment_id: str | None = None


class WhatIfRequest(BaseModel):
    allow_delay_hours: float = 0.0
    prioritize: str = "cost"  # cost | carbon | utilization
    shipment_ids: list[str] | None = None
    vehicle_ids: list[str] | None = None


class ChatRequest(BaseModel):
    session_id: str = "demo-session-001"
    message: str
    # Optional UI what-if knobs (Ask uses these; message text can still override)
    prioritize: str | None = None  # cost | carbon | utilization
    allow_delay_hours: float | None = None


class ChatResponse(BaseModel):
    answer: str
    findings: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "demo_data"
    requires_approval: bool = False
    data_class: str = "calculated"
