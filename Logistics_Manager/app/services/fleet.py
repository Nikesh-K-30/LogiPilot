from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.config import Settings, get_settings
from app.db import Database, get_db
from app.services.geo import haversine_km


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def route_waypoints(db: Database, route_id: str) -> list[tuple[float, float, str]]:
    route = db.get_route(route_id=route_id)
    if route is None:
        return []
    points: list[tuple[float, float, str]] = []
    depot = db.get_location(route.depot_id)
    if depot:
        points.append((depot["latitude"], depot["longitude"], route.depot_id))
    for loc_id in route.stop_location_ids:
        loc = db.get_location(loc_id)
        if loc:
            points.append((loc["latitude"], loc["longitude"], loc_id))
    return points


def _interpolate_along_path(
    points: list[tuple[float, float, str]], progress_pct: float
) -> tuple[float, float, float, str | None]:
    """Return lat, lon, heading, nearest upcoming location_id."""
    if not points:
        return 0.0, 0.0, 0.0, None
    if len(points) == 1:
        return points[0][0], points[0][1], 0.0, points[0][2]

    segs: list[float] = []
    total = 0.0
    for a, b in zip(points, points[1:]):
        d = haversine_km(a[0], a[1], b[0], b[1])
        segs.append(d)
        total += d
    if total <= 0:
        return points[0][0], points[0][1], 0.0, points[0][2]

    target = max(0.0, min(100.0, progress_pct)) / 100.0 * total
    travelled = 0.0
    for i, seg in enumerate(segs):
        if travelled + seg >= target - 1e-9:
            t = 0.0 if seg == 0 else (target - travelled) / seg
            lat = _lerp(points[i][0], points[i + 1][0], t)
            lon = _lerp(points[i][1], points[i + 1][1], t)
            heading = _bearing(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
            return lat, lon, heading, points[i + 1][2]
        travelled += seg
    last = points[-1]
    prev = points[-2]
    return last[0], last[1], _bearing(prev[0], prev[1], last[0], last[1]), last[2]


def tick_fleet(*, step_pct: float = 1.5, db: Database | None = None) -> list[dict[str, Any]]:
    """Advance in-transit vehicles along planned routes (simulated live GPS)."""
    db = db or get_db()
    now = datetime.now(timezone.utc).isoformat()
    updated: list[dict[str, Any]] = []
    with db.transaction() as conn:
        rows = conn.execute("SELECT * FROM vehicle_positions").fetchall()
        for row in rows:
            vid = row["vehicle_id"]
            vehicle = conn.execute(
                "SELECT * FROM vehicles WHERE vehicle_id = ?", (vid,)
            ).fetchone()
            if vehicle is None:
                continue
            progress = float(row["progress_pct"] or 0)
            route_id = row["route_id"] or vehicle["planned_route_id"]
            speed = float(row["speed_kmh"] or 0)
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            heading = float(row["heading_deg"] or 0)

            if vehicle["availability"] == "in_transit" and route_id:
                points = []
                # load waypoints inside transaction via SQL
                depot = conn.execute(
                    "SELECT r.depot_id, l.latitude, l.longitude FROM routes r "
                    "JOIN locations l ON l.location_id = r.depot_id WHERE r.route_id = ?",
                    (route_id,),
                ).fetchone()
                stops = conn.execute(
                    """
                    SELECT l.latitude, l.longitude, l.location_id
                    FROM route_stops rs
                    JOIN locations l ON l.location_id = rs.location_id
                    WHERE rs.route_id = ?
                    ORDER BY rs.sequence
                    """,
                    (route_id,),
                ).fetchall()
                if depot:
                    points.append((depot["latitude"], depot["longitude"], depot["depot_id"]))
                for s in stops:
                    points.append((s["latitude"], s["longitude"], s["location_id"]))

                progress = min(100.0, progress + step_pct)
                lat, lon, heading, _ = _interpolate_along_path(points, progress)
                speed = 38.0 + (vid[-1].isdigit() and int(vid[-1]) or 0)  # slight variance
                if progress >= 100.0:
                    speed = 0.0
                    conn.execute(
                        "UPDATE vehicles SET availability = 'available' WHERE vehicle_id = ?",
                        (vid,),
                    )

            conn.execute(
                """
                UPDATE vehicle_positions
                SET latitude=?, longitude=?, heading_deg=?, speed_kmh=?,
                    progress_pct=?, route_id=?, updated_at=?
                WHERE vehicle_id=?
                """,
                (lat, lon, heading, speed, progress, route_id, now, vid),
            )
            updated.append(
                {
                    "vehicle_id": vid,
                    "latitude": lat,
                    "longitude": lon,
                    "heading_deg": heading,
                    "speed_kmh": speed,
                    "progress_pct": round(progress, 2),
                    "route_id": route_id,
                    "updated_at": now,
                }
            )
    return updated


def list_fleet_live(
    *,
    advance: bool = True,
    db: Database | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    db = db or get_db()
    if advance:
        tick_fleet(db=db)

    vehicles = []
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT v.*, p.latitude, p.longitude, p.heading_deg, p.speed_kmh,
                   p.progress_pct, p.updated_at AS position_updated_at, p.route_id AS pos_route_id
            FROM vehicles v
            LEFT JOIN vehicle_positions p ON p.vehicle_id = v.vehicle_id
            ORDER BY v.vehicle_id
            """
        ).fetchall()
        for r in rows:
            d = dict(r)
            cap = float(d["capacity_kg"]) or 1.0
            used = float(d["used_capacity_kg"])
            util = used / cap
            route = db.get_route(route_id=d.get("planned_route_id"))
            stops = route.stop_location_ids if route else []
            stop_names = []
            for sid in ([route.depot_id] if route else []) + stops:
                loc = db.get_location(sid)
                if loc:
                    stop_names.append(loc["name"])
            vehicles.append(
                {
                    "vehicle_id": d["vehicle_id"],
                    "availability": d["availability"],
                    "primary_shipper_name": d.get("primary_shipper_name"),
                    "capacity_kg": d["capacity_kg"],
                    "used_capacity_kg": d["used_capacity_kg"],
                    "utilization_pct": round(util * 100, 1),
                    "remaining_kg": max(0.0, d["capacity_kg"] - d["used_capacity_kg"]),
                    "onboard_cargo_class": d.get("onboard_cargo_class"),
                    "latitude": d.get("latitude"),
                    "longitude": d.get("longitude"),
                    "heading_deg": d.get("heading_deg"),
                    "speed_kmh": d.get("speed_kmh"),
                    "progress_pct": d.get("progress_pct"),
                    "route_label": " → ".join(stop_names) if stop_names else None,
                    "planned_route_id": d.get("planned_route_id"),
                    "position_updated_at": d.get("position_updated_at"),
                    "live_mode": "simulated",
                }
            )

    return {
        "vehicles": vehicles,
        "live_mode": "simulated",
        "data_class": settings.data_class,
        "polled_at": datetime.now(timezone.utc).isoformat(),
        "note": "Positions advance along planned routes for demo (simulated live GPS).",
    }


def route_polylines(db: Database | None = None) -> list[dict[str, Any]]:
    db = db or get_db()
    out = []
    with db.connect() as conn:
        routes = conn.execute("SELECT * FROM routes").fetchall()
        for r in routes:
            pts = route_waypoints(db, r["route_id"])
            out.append(
                {
                    "route_id": r["route_id"],
                    "vehicle_id": r["vehicle_id"],
                    "coordinates": [[p[0], p[1]] for p in pts],
                    "location_ids": [p[2] for p in pts],
                }
            )
    return out
