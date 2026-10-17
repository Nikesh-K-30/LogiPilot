from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Sequence

from app.config import Settings, get_settings
from app.db import Database, get_db
from app.schemas import (
    FuelAssumptions,
    RouteMetrics,
    RouteOptimizationResult,
    RouteViolation,
)
from app.services.geo import distance_matrix, path_length


def _fuel_cost(distance_km: float, l_per_100: float, price: float) -> float:
    return round(distance_km * l_per_100 / 100.0 * price, 2)


def _nearest_neighbor(matrix: list[list[float]], start: int = 0) -> list[int]:
    n = len(matrix)
    unvisited = set(range(n))
    unvisited.remove(start)
    order = [start]
    cur = start
    while unvisited:
        nxt = min(unvisited, key=lambda j: matrix[cur][j])
        order.append(nxt)
        unvisited.remove(nxt)
        cur = nxt
    return order


def _two_opt(matrix: list[list[float]], order: list[int], max_iter: int = 200) -> list[int]:
    """2-opt local search. Keeps index 0 (depot) fixed when present as start."""
    best = order[:]
    best_len = path_length(matrix, best)
    improved = True
    iterations = 0
    while improved and iterations < max_iter:
        improved = False
        iterations += 1
        for i in range(1, len(best) - 2):
            for k in range(i + 1, len(best) - 1):
                candidate = best[:i] + best[i : k + 1][::-1] + best[k + 1 :]
                cand_len = path_length(matrix, candidate)
                if cand_len + 1e-9 < best_len:
                    best = candidate
                    best_len = cand_len
                    improved = True
                    break
            if improved:
                break
    return best


def optimize_route(
    *,
    depot_id: str,
    vehicle_id: str,
    stop_location_ids: Sequence[str] | None = None,
    route_id: str | None = None,
    mode: str = "open",
    fuel_consumption_l_per_100km: float | None = None,
    fuel_price_per_litre: float | None = None,
    avg_speed_kmh: float | None = None,
    db: Database | None = None,
    settings: Settings | None = None,
) -> RouteOptimizationResult:
    settings = settings or get_settings()
    db = db or get_db()

    vehicle = db.get_vehicle(vehicle_id)
    if vehicle is None:
        raise ValueError("VEHICLE_NOT_FOUND")

    if route_id and not stop_location_ids:
        route = db.get_route(route_id=route_id)
        if route is None:
            raise ValueError("ROUTE_NOT_FOUND")
        stop_location_ids = route.stop_location_ids
        depot_id = route.depot_id or depot_id
        mode = route.mode or mode

    if not stop_location_ids:
        raise ValueError("NO_STOPS")

    # Preserve input order; reject duplicates / missing
    seen: set[str] = set()
    ordered_stops: list[str] = []
    for loc in stop_location_ids:
        if loc in seen:
            raise ValueError(f"DUPLICATE_STOP:{loc}")
        seen.add(loc)
        ordered_stops.append(loc)

    depot = db.get_location(depot_id)
    if depot is None:
        raise ValueError("DEPOT_NOT_FOUND")

    coords: list[tuple[float, float]] = [(depot["latitude"], depot["longitude"])]
    loc_ids = [depot_id]
    demands_kg: list[float] = [0.0]
    demands_m3: list[float] = [0.0]
    window_ends: list[datetime | None] = [None]

    for loc_id in ordered_stops:
        loc = db.get_location(loc_id)
        if loc is None:
            raise ValueError(f"LOCATION_NOT_FOUND:{loc_id}")
        coords.append((loc["latitude"], loc["longitude"]))
        loc_ids.append(loc_id)
        demands_kg.append(0.0)
        demands_m3.append(0.0)
        window_ends.append(None)

    # Overlay route stop demands/windows if available
    if route_id:
        for stop in db.get_route_stops(route_id):
            if stop.location_id in loc_ids:
                idx = loc_ids.index(stop.location_id)
                demands_kg[idx] = stop.demand_kg
                demands_m3[idx] = stop.demand_m3
                window_ends[idx] = stop.time_window_end

    matrix = distance_matrix(coords, settings.road_factor)
    n = len(coords)

    # Baseline: depot + input order (+ optional return)
    baseline_idx = list(range(n))
    if mode == "round_trip":
        baseline_idx = baseline_idx + [0]

    nn = _nearest_neighbor(matrix, start=0)
    # nn visits all nodes including depot first; drop nothing
    opt_core = _two_opt(matrix, nn)
    if mode == "round_trip":
        # ensure ends at depot
        if opt_core[-1] != 0:
            opt_core = opt_core + [0]
        else:
            # already ends at 0 only if we added it; nn doesn't include return
            pass
        if opt_core[-1] != 0:
            opt_core.append(0)

    # For open routes, sequence is depot + stops without forcing return in metrics path
    if mode == "open":
        # Remove trailing depot if 2-opt somehow had it (shouldn't)
        opt_idx = [i for i in opt_core if not (i == 0 and opt_core.index(i) != 0)]
        # Rebuild: keep depot first, then remaining in opt order excluding depot
        rest = [i for i in opt_core if i != 0]
        opt_idx = [0] + rest
        base_idx = baseline_idx if baseline_idx[-1] != 0 or len(baseline_idx) == 1 else baseline_idx
    else:
        rest = [i for i in opt_core if i != 0]
        opt_idx = [0] + rest + [0]
        base_idx = [0] + list(range(1, n)) + [0]

    fuel_l = fuel_consumption_l_per_100km if fuel_consumption_l_per_100km is not None else settings.fuel_l_per_100km
    fuel_p = fuel_price_per_litre if fuel_price_per_litre is not None else settings.fuel_price_per_litre
    speed = avg_speed_kmh if avg_speed_kmh is not None else settings.avg_speed_kmh

    def metrics_for(order: list[int]) -> RouteMetrics:
        dist = path_length(matrix, order)
        # stop sequence excludes depot endpoints for output clarity
        seq = [loc_ids[i] for i in order if i != 0 or order.count(0) > 1]
        # Prefer listing intermediate stops only once
        stop_seq: list[str] = []
        for i in order:
            if i == 0:
                continue
            stop_seq.append(loc_ids[i])
        return RouteMetrics(
            stop_sequence=stop_seq,
            distance_km=dist,
            duration_hours=round(dist / speed, 3) if speed > 0 else 0.0,
            estimated_fuel_cost=_fuel_cost(dist, fuel_l, fuel_p),
        )

    baseline = metrics_for(base_idx if mode == "round_trip" else list(range(n)))
    optimized = metrics_for(opt_idx)

    violations: list[RouteViolation] = []
    cum_kg = 0.0
    cum_m3 = 0.0
    for i in opt_idx:
        if i == 0:
            continue
        cum_kg += demands_kg[i]
        cum_m3 += demands_m3[i]
    if cum_kg > vehicle.capacity_kg + 1e-9:
        violations.append(
            RouteViolation(
                code="CAPACITY_EXCEEDED_KG",
                message=f"Route demand {cum_kg} kg exceeds vehicle capacity {vehicle.capacity_kg} kg",
            )
        )
    if cum_m3 > vehicle.capacity_m3 + 1e-9:
        violations.append(
            RouteViolation(
                code="CAPACITY_EXCEEDED_M3",
                message=f"Route demand {cum_m3} m3 exceeds vehicle capacity {vehicle.capacity_m3} m3",
            )
        )

    # Simple time-window check using cumulative travel from depot
    elapsed_h = 0.0
    prev = 0
    for i in opt_idx[1:]:
        if i == 0:
            continue
        elapsed_h += matrix[prev][i] / speed if speed > 0 else 0
        end = window_ends[i]
        if end is not None:
            # Compare elapsed hours from "now" — demo uses absolute window only as soft check
            # If window end is in the past relative to computed_at + elapsed, flag
            arrival = datetime.now(timezone.utc).timestamp() + elapsed_h * 3600
            if arrival > end.timestamp():
                violations.append(
                    RouteViolation(
                        code="TIME_WINDOW_VIOLATION",
                        message=f"Estimated arrival exceeds window for {loc_ids[i]}",
                        stop_id=loc_ids[i],
                    )
                )
        prev = i

    input_payload = {
        "depot_id": depot_id,
        "vehicle_id": vehicle_id,
        "stops": ordered_stops,
        "mode": mode,
        "fuel_l": fuel_l,
        "fuel_p": fuel_p,
        "speed": speed,
        "algo": settings.routewise_algorithm_version,
    }
    input_hash = hashlib.sha256(
        json.dumps(input_payload, sort_keys=True).encode()
    ).hexdigest()[:16]

    run_id = db.save_optimization_run(
        input_hash=input_hash,
        algorithm_version=settings.routewise_algorithm_version,
        baseline=baseline.model_dump(),
        optimized=optimized.model_dump(),
    )

    savings = {
        "distance_km": round(baseline.distance_km - optimized.distance_km, 3),
        "estimated_fuel_cost": round(baseline.estimated_fuel_cost - optimized.estimated_fuel_cost, 2),
        "pct_distance": round(
            (baseline.distance_km - optimized.distance_km) / baseline.distance_km * 100, 2
        )
        if baseline.distance_km > 0
        else 0.0,
    }

    return RouteOptimizationResult(
        run_id=run_id,
        vehicle_id=vehicle_id,
        depot_id=depot_id,
        feasible=len(violations) == 0,
        baseline=baseline,
        optimized=optimized,
        savings=savings,
        violations=violations,
        fuel_assumptions=FuelAssumptions(
            fuel_consumption_l_per_100km=fuel_l,
            fuel_price_per_litre=fuel_p,
            currency=settings.currency,
        ),
        algorithm_version=settings.routewise_algorithm_version,
        computed_at=datetime.now(timezone.utc),
        data_class=settings.data_class,
        input_hash=input_hash,
    )


def compare_routes(
    *,
    depot_id: str,
    baseline_stops: Sequence[str],
    candidate_stops: Sequence[str],
    settings: Settings | None = None,
    db: Database | None = None,
) -> dict:
    settings = settings or get_settings()
    db = db or get_db()
    depot = db.get_location(depot_id)
    if depot is None:
        raise ValueError("DEPOT_NOT_FOUND")

    def build(stops: Sequence[str]) -> tuple[list[list[float]], list[int], list[str]]:
        coords = [(depot["latitude"], depot["longitude"])]
        ids = [depot_id]
        for s in stops:
            loc = db.get_location(s)
            if loc is None:
                raise ValueError(f"LOCATION_NOT_FOUND:{s}")
            coords.append((loc["latitude"], loc["longitude"]))
            ids.append(s)
        matrix = distance_matrix(coords, settings.road_factor)
        order = list(range(len(coords)))
        return matrix, order, ids

    b_mat, b_ord, _ = build(baseline_stops)
    c_mat, c_ord, _ = build(candidate_stops)
    b_dist = path_length(b_mat, b_ord)
    c_dist = path_length(c_mat, c_ord)
    return {
        "baseline_distance_km": b_dist,
        "candidate_distance_km": c_dist,
        "delta_km": round(b_dist - c_dist, 3),
        "assumptions": [f"road_factor={settings.road_factor}", "haversine_distance_v1"],
        "data_class": "estimate",
    }
