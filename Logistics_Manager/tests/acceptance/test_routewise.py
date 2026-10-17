from app.services import routing


def test_rw01_five_stops_no_omit_duplicate(db):
    stops = ["LOC-PUN", "LOC-NGP", "LOC-HYD", "LOC-BLR", "LOC-MAA"]
    result = routing.optimize_route(
        depot_id="LOC-MUM",
        vehicle_id="VEH-001",
        stop_location_ids=stops,
        mode="open",
        db=db,
    )
    assert set(result.optimized.stop_sequence) == set(stops)
    assert len(result.optimized.stop_sequence) == len(stops)
    assert len(set(result.optimized.stop_sequence)) == len(stops)
    assert result.baseline.distance_km > 0
    assert result.optimized.distance_km > 0


def test_rw02_capacity_infeasible(db):
    # Inflate demands via temporary route stops already set; use vehicle with tiny capacity
    result = routing.optimize_route(
        depot_id="LOC-HYD",
        vehicle_id="VEH-003",
        stop_location_ids=["LOC-BLR", "LOC-MAA"],
        mode="open",
        db=db,
    )
    # VEH-003 has capacity; demands default 0 so feasible — force via route RTE-100 demands
    # Use RTE-100 on small vehicle conceptually: call with route that has demand
    # Instead mark by comparing vehicle capacity to artificial check:
    from app.schemas import RouteViolation

    # Simulate infeasible by optimizing RTE-100 stops claiming high cumulative demand on VEH-003
    result2 = routing.optimize_route(
        depot_id="LOC-MUM",
        vehicle_id="VEH-003",
        route_id="RTE-100",
        mode="open",
        db=db,
    )
    assert result2.feasible is False
    assert any(v.code.startswith("CAPACITY") for v in result2.violations)


def test_rw03_fuel_same_assumptions(db):
    result = routing.optimize_route(
        depot_id="LOC-MUM",
        vehicle_id="VEH-001",
        route_id="RTE-100",
        mode="open",
        db=db,
    )
    fa = result.fuel_assumptions
    # Recompute expected fuel from distance using same model
    expected_base = round(
        result.baseline.distance_km
        * fa.fuel_consumption_l_per_100km
        / 100
        * fa.fuel_price_per_litre,
        2,
    )
    expected_opt = round(
        result.optimized.distance_km
        * fa.fuel_consumption_l_per_100km
        / 100
        * fa.fuel_price_per_litre,
        2,
    )
    assert result.baseline.estimated_fuel_cost == expected_base
    assert result.optimized.estimated_fuel_cost == expected_opt


def test_rw04_repeatability(db):
    a = routing.optimize_route(
        depot_id="LOC-MUM",
        vehicle_id="VEH-001",
        route_id="RTE-100",
        db=db,
    )
    b = routing.optimize_route(
        depot_id="LOC-MUM",
        vehicle_id="VEH-001",
        route_id="RTE-100",
        db=db,
    )
    assert a.input_hash == b.input_hash
    assert a.baseline.distance_km == b.baseline.distance_km
    assert a.optimized.distance_km == b.optimized.distance_km
