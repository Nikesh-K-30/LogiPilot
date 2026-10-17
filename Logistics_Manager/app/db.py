from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import Settings, get_settings
from app.schemas import (
    Availability,
    Route,
    RouteStop,
    Shipment,
    ShipmentStatus,
    Vehicle,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.path = Path(path or self.settings.database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self, schema_path: Path | None = None) -> None:
        schema = schema_path or Path(__file__).resolve().parents[1] / "database" / "schema.sql"
        with self.transaction() as conn:
            conn.executescript(schema.read_text(encoding="utf-8"))

    def audit(
        self,
        conn: sqlite3.Connection,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        result: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO audit_events (event_id, actor, action, entity_type, entity_id, result, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (f"AUD-{uuid.uuid4().hex[:10]}", actor, action, entity_type, entity_id, result, _utc_now()),
        )

    def get_location(self, location_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM locations WHERE location_id = ?", (location_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_locations(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM locations ORDER BY location_id")]

    def get_vehicle(self, vehicle_id: str) -> Vehicle | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM vehicles WHERE vehicle_id = ?", (vehicle_id,)
            ).fetchone()
            return Vehicle.model_validate(dict(row)) if row else None

    def list_available_vehicles(
        self,
        *,
        location_id: str | None = None,
        min_kg: float | None = None,
        min_m3: float | None = None,
    ) -> list[Vehicle]:
        sql = "SELECT * FROM vehicles WHERE availability IN ('available', 'in_transit')"
        params: list[Any] = []
        if location_id:
            sql += " AND current_location_id = ?"
            params.append(location_id)
        sql += " ORDER BY vehicle_id"
        with self.connect() as conn:
            vehicles = [Vehicle.model_validate(dict(r)) for r in conn.execute(sql, params)]
        out: list[Vehicle] = []
        for v in vehicles:
            if min_kg is not None and v.remaining_kg < min_kg:
                continue
            if min_m3 is not None and v.remaining_m3 < min_m3:
                continue
            out.append(v)
        return out

    def get_shipment(self, shipment_id: str) -> Shipment | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM shipments WHERE shipment_id = ?", (shipment_id,)
            ).fetchone()
            if not row:
                return None
            return self._shipment_from_row(row)

    def list_shipments(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        deadline_before: str | None = None,
    ) -> list[Shipment]:
        sql = "SELECT * FROM shipments WHERE 1=1"
        params: list[Any] = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if deadline_before:
            sql += " AND deadline <= ?"
            params.append(deadline_before)
        sql += " ORDER BY shipment_id LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return [self._shipment_from_row(r) for r in conn.execute(sql, params)]

    def list_unassigned_shipments(self, limit: int = 50) -> list[Shipment]:
        return self.list_shipments(status=ShipmentStatus.unassigned.value, limit=limit)

    def get_route(self, *, route_id: str | None = None, vehicle_id: str | None = None) -> Route | None:
        with self.connect() as conn:
            if route_id:
                row = conn.execute("SELECT * FROM routes WHERE route_id = ?", (route_id,)).fetchone()
            elif vehicle_id:
                row = conn.execute(
                    "SELECT * FROM routes WHERE vehicle_id = ? ORDER BY route_id LIMIT 1",
                    (vehicle_id,),
                ).fetchone()
            else:
                return None
            if not row:
                return None
            stops = conn.execute(
                """
                SELECT location_id FROM route_stops
                WHERE route_id = ? ORDER BY sequence
                """,
                (row["route_id"],),
            ).fetchall()
            data = dict(row)
            data["stop_location_ids"] = [s["location_id"] for s in stops]
            return Route.model_validate(data)

    def get_route_stops(self, route_id: str) -> list[RouteStop]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT rs.*, l.latitude, l.longitude
                FROM route_stops rs
                JOIN locations l ON l.location_id = rs.location_id
                WHERE rs.route_id = ?
                ORDER BY rs.sequence
                """,
                (route_id,),
            ).fetchall()
            return [RouteStop.model_validate(dict(r)) for r in rows]

    def get_delivery_stops_for_locations(
        self, route_id: str | None, location_ids: list[str]
    ) -> list[RouteStop]:
        if route_id:
            return self.get_route_stops(route_id)
        stops: list[RouteStop] = []
        with self.connect() as conn:
            for i, loc_id in enumerate(location_ids):
                loc = conn.execute(
                    "SELECT * FROM locations WHERE location_id = ?", (loc_id,)
                ).fetchone()
                if not loc:
                    continue
                stops.append(
                    RouteStop(
                        stop_id=f"TMP-{i+1}",
                        route_id=route_id or "TMP",
                        location_id=loc_id,
                        sequence=i + 1,
                        latitude=loc["latitude"],
                        longitude=loc["longitude"],
                    )
                )
        return stops

    def save_match_run(self, *, input_hash: str, algorithm_version: str, payload: dict) -> str:
        run_id = f"MATRUN-{uuid.uuid4().hex[:10]}"
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO match_runs (run_id, input_hash, algorithm_version, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, input_hash, algorithm_version, json.dumps(payload), _utc_now()),
            )
        return run_id

    def save_optimization_run(
        self,
        *,
        input_hash: str,
        algorithm_version: str,
        baseline: dict,
        optimized: dict,
    ) -> str:
        run_id = f"OPT-{uuid.uuid4().hex[:10]}"
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO optimization_runs
                (run_id, input_hash, algorithm_version, baseline_metrics, optimized_metrics, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    input_hash,
                    algorithm_version,
                    json.dumps(baseline),
                    json.dumps(optimized),
                    _utc_now(),
                ),
            )
        return run_id



    def list_vehicles(self) -> list[Vehicle]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM vehicles ORDER BY vehicle_id").fetchall()
            return [Vehicle.model_validate(dict(r)) for r in rows]

    def create_vehicle(
        self,
        *,
        capacity_kg: float,
        capacity_m3: float,
        current_location_id: str,
        availability: str = "available",
        fixed_cost: float = 5000.0,
        variable_cost_per_km: float = 20.0,
        currency: str = "INR",
        used_capacity_kg: float = 0.0,
        used_capacity_m3: float = 0.0,
        onboard_cargo_class: str = "general",
        primary_shipper_id: str | None = None,
        primary_shipper_name: str | None = None,
        vehicle_id: str | None = None,
        route_stop_ids: list[str] | None = None,
        speed_kmh: float = 0.0,
        actor: str = "user:admin",
    ) -> dict:
        if self.get_location(current_location_id) is None:
            raise ValueError("LOCATION_NOT_FOUND")
        if capacity_kg < 0 or capacity_m3 < 0:
            raise ValueError("INVALID_CAPACITY")
        if used_capacity_kg > capacity_kg or used_capacity_m3 > capacity_m3:
            raise ValueError("USED_EXCEEDS_CAPACITY")
        vid = vehicle_id or f"VEH-{uuid.uuid4().hex[:6].upper()}"
        if self.get_vehicle(vid) is not None:
            raise ValueError("VEHICLE_EXISTS")
        route_stop_ids = route_stop_ids or []
        for lid in route_stop_ids:
            if self.get_location(lid) is None:
                raise ValueError(f"LOCATION_NOT_FOUND:{lid}")
        route_id = None
        now = _utc_now()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO vehicles (
                    vehicle_id, capacity_kg, capacity_m3, current_location_id, availability,
                    fixed_cost, variable_cost_per_km, currency, planned_route_id,
                    used_capacity_kg, used_capacity_m3,
                    onboard_cargo_class, primary_shipper_id, primary_shipper_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    vid, capacity_kg, capacity_m3, current_location_id, availability,
                    fixed_cost, variable_cost_per_km, currency,
                    used_capacity_kg, used_capacity_m3,
                    onboard_cargo_class, primary_shipper_id, primary_shipper_name,
                ),
            )
            if route_stop_ids:
                route_id = f"RTE-{uuid.uuid4().hex[:6].upper()}"
                conn.execute(
                    """
                    INSERT INTO routes (route_id, vehicle_id, depot_id, mode, status)
                    VALUES (?, ?, ?, 'open', 'planned')
                    """,
                    (route_id, vid, current_location_id),
                )
                for i, lid in enumerate(route_stop_ids, start=1):
                    conn.execute(
                        """
                        INSERT INTO route_stops (
                            stop_id, route_id, location_id, sequence,
                            service_duration_minutes, demand_kg, demand_m3
                        ) VALUES (?, ?, ?, ?, 30, 0, 0)
                        """,
                        (f"STP-{route_id}-{i}", route_id, lid, i),
                    )
                conn.execute(
                    "UPDATE vehicles SET planned_route_id = ? WHERE vehicle_id = ?",
                    (route_id, vid),
                )
            loc = conn.execute(
                "SELECT latitude, longitude FROM locations WHERE location_id = ?",
                (current_location_id,),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO vehicle_positions (
                    vehicle_id, latitude, longitude, heading_deg, speed_kmh,
                    progress_pct, route_id, updated_at
                ) VALUES (?, ?, ?, 0, ?, 0, ?, ?)
                """,
                (
                    vid,
                    float(loc["latitude"]),
                    float(loc["longitude"]),
                    float(speed_kmh),
                    route_id,
                    now,
                ),
            )
            self.audit(
                conn,
                actor=actor,
                action="create_vehicle",
                entity_type="vehicle",
                entity_id=vid,
                result=json.dumps({"route_id": route_id, "ok": True}),
            )
        vehicle = self.get_vehicle(vid)
        return {
            "vehicle": vehicle.model_dump(mode="json") if vehicle else None,
            "route_id": route_id,
            "vehicle_id": vid,
        }

    def create_shipment(
        self,
        *,
        origin_id: str,
        destination_id: str,
        weight_kg: float,
        volume_m3: float,
        deadline: datetime,
        shipper_name: str,
        shipper_id: str | None = None,
        cargo_class: str = "general",
        shipment_id: str | None = None,
        actor: str = "user:dispatcher-01",
    ) -> Shipment:
        if self.get_location(origin_id) is None:
            raise ValueError("ORIGIN_NOT_FOUND")
        if self.get_location(destination_id) is None:
            raise ValueError("DESTINATION_NOT_FOUND")
        if weight_kg < 0 or volume_m3 < 0:
            raise ValueError("INVALID_QUANTITY")
        sid = shipment_id or f"SHP-{uuid.uuid4().hex[:8].upper()}"
        if self.get_shipment(sid) is not None:
            raise ValueError("SHIPMENT_EXISTS")
        now = _utc_now()
        shipper_id = shipper_id or f"SHIPPER-{shipper_name.upper().replace(' ', '-')[:16]}"
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO shipments (
                    shipment_id, origin_id, destination_id, weight_kg, volume_m3,
                    deadline, status, assigned_vehicle_id,
                    shipper_id, shipper_name, cargo_class,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    origin_id,
                    destination_id,
                    weight_kg,
                    volume_m3,
                    deadline.isoformat(),
                    ShipmentStatus.unassigned.value,
                    shipper_id,
                    shipper_name,
                    cargo_class,
                    now,
                    now,
                ),
            )
            self.audit(
                conn,
                actor=actor,
                action="create_shipment",
                entity_type="shipment",
                entity_id=sid,
                result="ok",
            )
        created = self.get_shipment(sid)
        if created is None:
            raise ValueError("CREATE_FAILED")
        return created

    def assign_shipments(
        self,
        *,
        vehicle_id: str,
        shipment_ids: list[str],
        actor: str,
        rationale: str,
    ) -> dict[str, Any]:
        with self.transaction() as conn:
            vehicle = conn.execute(
                "SELECT * FROM vehicles WHERE vehicle_id = ?", (vehicle_id,)
            ).fetchone()
            if not vehicle:
                raise ValueError("VEHICLE_NOT_FOUND")
            used_kg = float(vehicle["used_capacity_kg"])
            used_m3 = float(vehicle["used_capacity_m3"])
            assigned: list[str] = []
            for sid in shipment_ids:
                ship = conn.execute(
                    "SELECT * FROM shipments WHERE shipment_id = ?", (sid,)
                ).fetchone()
                if not ship:
                    raise ValueError(f"SHIPMENT_NOT_FOUND:{sid}")
                if ship["status"] != ShipmentStatus.unassigned.value:
                    raise ValueError(f"SHIPMENT_NOT_UNASSIGNED:{sid}")
                if ship["assigned_vehicle_id"]:
                    raise ValueError(f"SHIPMENT_ALREADY_ASSIGNED:{sid}")
                used_kg += float(ship["weight_kg"])
                used_m3 += float(ship["volume_m3"])
                if used_kg > float(vehicle["capacity_kg"]) + 1e-9:
                    raise ValueError("CAPACITY_EXCEEDED_KG")
                if used_m3 > float(vehicle["capacity_m3"]) + 1e-9:
                    raise ValueError("CAPACITY_EXCEEDED_M3")
                conn.execute(
                    """
                    UPDATE shipments
                    SET status = ?, assigned_vehicle_id = ?, updated_at = ?
                    WHERE shipment_id = ?
                    """,
                    (ShipmentStatus.assigned.value, vehicle_id, _utc_now(), sid),
                )
                conn.execute(
                    """
                    INSERT INTO assignments
                    (assignment_id, vehicle_id, shipment_id, actor, rationale, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (f"ASN-{uuid.uuid4().hex[:10]}", vehicle_id, sid, actor, rationale, _utc_now()),
                )
                assigned.append(sid)
            conn.execute(
                """
                UPDATE vehicles SET used_capacity_kg = ?, used_capacity_m3 = ?
                WHERE vehicle_id = ?
                """,
                (used_kg, used_m3, vehicle_id),
            )
            self.audit(
                conn,
                actor=actor,
                action="assign_shipment_to_vehicle",
                entity_type="vehicle",
                entity_id=vehicle_id,
                result=json.dumps({"shipment_ids": assigned, "ok": True}),
            )
            return {
                "vehicle_id": vehicle_id,
                "shipment_ids": assigned,
                "used_capacity_kg": used_kg,
                "used_capacity_m3": used_m3,
            }

    @staticmethod
    def _shipment_from_row(row: sqlite3.Row) -> Shipment:
        data = dict(row)
        data.pop("created_at", None)
        data.pop("updated_at", None)
        return Shipment.model_validate(data)


_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


def reset_db_singleton() -> None:
    global _db
    _db = None
