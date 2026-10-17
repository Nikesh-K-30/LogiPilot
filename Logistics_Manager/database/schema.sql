PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS locations (
    location_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata'
);

CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id TEXT PRIMARY KEY,
    capacity_kg REAL NOT NULL CHECK (capacity_kg >= 0),
    capacity_m3 REAL NOT NULL CHECK (capacity_m3 >= 0),
    current_location_id TEXT NOT NULL REFERENCES locations(location_id),
    availability TEXT NOT NULL,
    fixed_cost REAL NOT NULL DEFAULT 0,
    variable_cost_per_km REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'INR',
    planned_route_id TEXT,
    used_capacity_kg REAL NOT NULL DEFAULT 0 CHECK (used_capacity_kg >= 0),
    used_capacity_m3 REAL NOT NULL DEFAULT 0 CHECK (used_capacity_m3 >= 0),
    onboard_cargo_class TEXT NOT NULL DEFAULT 'general',
    primary_shipper_id TEXT,
    primary_shipper_name TEXT
);

CREATE TABLE IF NOT EXISTS routes (
    route_id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL REFERENCES vehicles(vehicle_id),
    depot_id TEXT NOT NULL REFERENCES locations(location_id),
    mode TEXT NOT NULL DEFAULT 'open',
    status TEXT NOT NULL DEFAULT 'planned'
);

CREATE TABLE IF NOT EXISTS route_stops (
    stop_id TEXT PRIMARY KEY,
    route_id TEXT NOT NULL REFERENCES routes(route_id) ON DELETE CASCADE,
    location_id TEXT NOT NULL REFERENCES locations(location_id),
    sequence INTEGER NOT NULL,
    service_duration_minutes INTEGER NOT NULL DEFAULT 30,
    time_window_start TEXT,
    time_window_end TEXT,
    demand_kg REAL NOT NULL DEFAULT 0,
    demand_m3 REAL NOT NULL DEFAULT 0,
    UNIQUE (route_id, sequence)
);

CREATE TABLE IF NOT EXISTS shipments (
    shipment_id TEXT PRIMARY KEY,
    origin_id TEXT NOT NULL REFERENCES locations(location_id),
    destination_id TEXT NOT NULL REFERENCES locations(location_id),
    weight_kg REAL NOT NULL CHECK (weight_kg >= 0),
    volume_m3 REAL NOT NULL CHECK (volume_m3 >= 0),
    deadline TEXT NOT NULL,
    status TEXT NOT NULL,
    assigned_vehicle_id TEXT REFERENCES vehicles(vehicle_id),
    shipper_id TEXT,
    shipper_name TEXT,
    cargo_class TEXT NOT NULL DEFAULT 'general',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assignments (
    assignment_id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL REFERENCES vehicles(vehicle_id),
    shipment_id TEXT NOT NULL UNIQUE REFERENCES shipments(shipment_id),
    actor TEXT NOT NULL,
    rationale TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_runs (
    run_id TEXT PRIMARY KEY,
    input_hash TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS optimization_runs (
    run_id TEXT PRIMARY KEY,
    input_hash TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    baseline_metrics TEXT NOT NULL,
    optimized_metrics TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vehicle_positions (
    vehicle_id TEXT PRIMARY KEY REFERENCES vehicles(vehicle_id) ON DELETE CASCADE,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    heading_deg REAL NOT NULL DEFAULT 0,
    speed_kmh REAL NOT NULL DEFAULT 0,
    progress_pct REAL NOT NULL DEFAULT 0,
    route_id TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shipments_status ON shipments(status);
CREATE INDEX IF NOT EXISTS idx_shipments_vehicle ON shipments(assigned_vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_availability ON vehicles(availability);
CREATE INDEX IF NOT EXISTS idx_route_stops_route ON route_stops(route_id, sequence);
