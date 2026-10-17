from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.db import Database, reset_db_singleton

IST = ZoneInfo("Asia/Kolkata")

LOCATIONS = [
    ("LOC-DEL", "Delhi Hub", 28.6139, 77.2090),
    ("LOC-JPR", "Jaipur", 26.9124, 75.7873),
    ("LOC-AGR", "Agra", 27.1767, 78.0081),
    ("LOC-LKO", "Lucknow", 26.8467, 80.9462),
    ("LOC-BHO", "Bhopal", 23.2599, 77.4126),
    ("LOC-NGP", "Nagpur", 21.1458, 79.0882),
    ("LOC-HYD", "Hyderabad", 17.3850, 78.4867),
    ("LOC-BLR", "Bengaluru", 12.9716, 77.5946),
    ("LOC-MAA", "Chennai", 13.0827, 80.2707),
    ("LOC-COK", "Kochi", 9.9312, 76.2673),
    ("LOC-MUM", "Mumbai", 19.0760, 72.8777),
    ("LOC-PUN", "Pune", 18.5204, 73.8567),
]


def seed(db: Database | None = None, reset: bool = True) -> Path:
    """Seed a generic multi-shipper consolidation demo (no consumer-brand names)."""
    settings = get_settings()
    path = settings.database_path
    if reset and path.exists():
        path.unlink()
    reset_db_singleton()
    database = db or Database(path=path, settings=settings)
    database.initialize()

    now = datetime.now(timezone.utc)
    deadline_base = datetime(2026, 10, 20, 18, 0, tzinfo=IST)

    with database.transaction() as conn:
        for loc_id, name, lat, lon in LOCATIONS:
            conn.execute(
                """
                INSERT INTO locations (location_id, name, latitude, longitude, timezone)
                VALUES (?, ?, ?, ?, 'Asia/Kolkata')
                """,
                (loc_id, name, lat, lon),
            )

        # Primary corridor truck: Northern Retail, ~61% full Mumbai→Chennai via Hyd
        conn.execute(
            """
            INSERT INTO vehicles (
                vehicle_id, capacity_kg, capacity_m3, current_location_id, availability,
                fixed_cost, variable_cost_per_km, currency, planned_route_id,
                used_capacity_kg, used_capacity_m3,
                onboard_cargo_class, primary_shipper_id, primary_shipper_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "VEH-001", 13000, 40.0, "LOC-MUM", "in_transit",
                5000.0, 22.0, "INR", "RTE-100",
                8000.0, 24.0, "food", "SHIPPER-NORTH", "Northern Retail",
            ),
        )
        # Counterfactual dedicated truck for Deccan Goods (avoided if we consolidate)
        conn.execute(
            """
            INSERT INTO vehicles (
                vehicle_id, capacity_kg, capacity_m3, current_location_id, availability,
                fixed_cost, variable_cost_per_km, currency, planned_route_id,
                used_capacity_kg, used_capacity_m3,
                onboard_cargo_class, primary_shipper_id, primary_shipper_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "VEH-002", 5000, 18.0, "LOC-HYD", "available",
                8000.0, 25.0, "INR", "RTE-200",
                0.0, 0.0, "general", None, None,
            ),
        )
        conn.execute(
            """
            INSERT INTO vehicles (
                vehicle_id, capacity_kg, capacity_m3, current_location_id, availability,
                fixed_cost, variable_cost_per_km, currency, planned_route_id,
                used_capacity_kg, used_capacity_m3,
                onboard_cargo_class, primary_shipper_id, primary_shipper_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "VEH-003", 500, 3.0, "LOC-BLR", "available",
                200.0, 14.0, "INR", None,
                0.0, 0.0, "general", None, None,
            ),
        )

        conn.execute(
            """
            INSERT INTO routes (route_id, vehicle_id, depot_id, mode, status)
            VALUES ('RTE-100', 'VEH-001', 'LOC-MUM', 'open', 'planned')
            """
        )
        for stop_id, loc_id, seq, dkg, dm3 in [
            ("STP-100-1", "LOC-PUN", 1, 2000, 6.0),   # drop SHP-1002
            ("STP-100-2", "LOC-HYD", 2, 1000, 3.0),   # drop SHP-1003
            ("STP-100-3", "LOC-MAA", 3, 5000, 15.0),  # drop SHP-1001
        ]:
            conn.execute(
                """
                INSERT INTO route_stops (
                    stop_id, route_id, location_id, sequence,
                    service_duration_minutes, demand_kg, demand_m3
                ) VALUES (?, 'RTE-100', ?, ?, 45, ?, ?)
                """,
                (stop_id, loc_id, seq, dkg, dm3),
            )

        conn.execute(
            """
            INSERT INTO routes (route_id, vehicle_id, depot_id, mode, status)
            VALUES ('RTE-200', 'VEH-002', 'LOC-HYD', 'open', 'planned')
            """
        )
        conn.execute(
            """
            INSERT INTO route_stops (
                stop_id, route_id, location_id, sequence,
                service_duration_minutes, demand_kg, demand_m3
            ) VALUES ('STP-200-1', 'RTE-200', 'LOC-MAA', 1, 30, 0, 0)
            """
        )

        # Realistic multi-stop load on VEH-001 (capacity 13000 kg):
        # Mumbai loads: through-to-Chennai + drop at Pune + drop at Hyderabad.
        # After Pune drop, spare capacity grows — ideal for mid-corridor pooling at Hyd.
        shipments = [
            ("SHP-1001", "LOC-MUM", "LOC-MAA", 5000, 15.0, deadline_base + timedelta(days=3),
             "assigned", "VEH-001", "SHIPPER-NORTH", "Northern Retail", "food"),
            ("SHP-1002", "LOC-MUM", "LOC-PUN", 2000, 6.0, deadline_base + timedelta(days=1),
             "assigned", "VEH-001", "SHIPPER-NORTH", "Northern Retail", "food"),
            ("SHP-1003", "LOC-MUM", "LOC-HYD", 1000, 3.0, deadline_base + timedelta(days=2),
             "assigned", "VEH-001", "SHIPPER-NORTH", "Northern Retail", "food"),
            # Open pooling candidates (Hyd → Chennai corridor)
            ("SHP-2001", "LOC-HYD", "LOC-MAA", 3000, 9.0, deadline_base + timedelta(days=3),
             "unassigned", None, "SHIPPER-DECCAN", "Deccan Goods", "food"),
            ("SHP-2007", "LOC-HYD", "LOC-MAA", 2000, 6.0, deadline_base + timedelta(days=3),
             "unassigned", None, "SHIPPER-COASTAL", "CoastalMart", "general"),
            ("SHP-2002", "LOC-PUN", "LOC-HYD", 400, 1.2, deadline_base + timedelta(days=2),
             "unassigned", None, "SHIPPER-LOCAL", "LocalMart", "food"),
            ("SHP-2003", "LOC-HYD", "LOC-MAA", 1800, 5.0, deadline_base + timedelta(days=4),
             "unassigned", None, "SHIPPER-BULK", "BulkCo", "general"),
            ("SHP-2004", "LOC-COK", "LOC-MUM", 100, 0.5, deadline_base + timedelta(days=5),
             "unassigned", None, "SHIPPER-SOUTH", "SouthShip", "general"),
            ("SHP-2005", "LOC-HYD", "LOC-MAA", 500, 1.5, deadline_base + timedelta(days=3),
             "unassigned", None, "SHIPPER-CHEM", "ChemHaul", "hazardous"),
            ("SHP-2006", "LOC-BLR", "LOC-MAA", 250, 1.2, deadline_base + timedelta(days=2),
             "unassigned", None, "SHIPPER-BLR", "BlrGoods", "general"),
        ]
        for sid, origin, dest, w, v, deadline, status, veh, shipper_id, shipper_name, cargo in shipments:
            conn.execute(
                """
                INSERT INTO shipments (
                    shipment_id, origin_id, destination_id, weight_kg, volume_m3,
                    deadline, status, assigned_vehicle_id,
                    shipper_id, shipper_name, cargo_class,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid, origin, dest, w, v, deadline.isoformat(), status, veh,
                    shipper_id, shipper_name, cargo, now.isoformat(), now.isoformat(),
                ),
            )

        # Live positions: VEH-001 mid-corridor (between Pune and Hyderabad)
        # VEH-002 idle at Hyderabad, VEH-003 idle at Bengaluru
        positions = [
            ("VEH-001", 18.0, 75.8, 120.0, 42.0, 28.0, "RTE-100"),
            ("VEH-002", 17.3850, 78.4867, 140.0, 0.0, 0.0, "RTE-200"),
            ("VEH-003", 12.9716, 77.5946, 90.0, 0.0, 0.0, None),
        ]
        for vid, lat, lon, heading, speed, progress, rid in positions:
            conn.execute(
                """
                INSERT INTO vehicle_positions (
                    vehicle_id, latitude, longitude, heading_deg, speed_kmh,
                    progress_pct, route_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (vid, lat, lon, heading, speed, progress, rid, now.isoformat()),
            )

        database.audit(
            conn,
            actor="system:seed",
            action="seed_database",
            entity_type="database",
            entity_id=str(path),
            result="ok",
        )

    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed LogiPilot demo database")
    parser.add_argument("--reset", action="store_true", default=True)
    parser.add_argument("--no-reset", action="store_true")
    args = parser.parse_args()
    path = seed(reset=not args.no_reset)
    print(f"Seeded database at {path}")


if __name__ == "__main__":
    main()
