"""
SQLite database setup and synthetic data seeding.
Called once on application startup.
"""
import sqlite3
import random
import uuid
import math
from datetime import date, timedelta
from pathlib import Path

from config import DB_PATH

# ── Seed for reproducible demos ───────────────────────────────────────────────
SEED = 42
random.seed(SEED)


# ── Master data ───────────────────────────────────────────────────────────────

SUPPLIERS = [
    {
        "id": "SUP-SH",
        "name": "Shanghai Electronics",
        "city": "Shanghai",
        "country": "China",
        "lat": 31.23,
        "lon": 121.47,
        "capacity_units_per_day": 500,
    },
    {
        "id": "SUP-SZ",
        "name": "Shenzhen Components",
        "city": "Shenzhen",
        "country": "China",
        "lat": 22.54,
        "lon": 114.06,
        "capacity_units_per_day": 400,
    },
    {
        "id": "SUP-MU",
        "name": "Munich Auto Parts",
        "city": "Munich",
        "country": "Germany",
        "lat": 48.14,
        "lon": 11.58,
        "capacity_units_per_day": 300,
    },
    {
        "id": "SUP-MO",
        "name": "Monterrey Industrial",
        "city": "Monterrey",
        "country": "Mexico",
        "lat": 25.67,
        "lon": -100.31,
        "capacity_units_per_day": 450,
    },
    {
        "id": "SUP-DE",
        "name": "Detroit Motors Supply",
        "city": "Detroit",
        "country": "USA",
        "lat": 42.33,
        "lon": -83.05,
        "capacity_units_per_day": 350,
    },
]

DISTRIBUTION_CENTERS = [
    {
        "id": "DC-FR",
        "name": "Fremont DC",
        "city": "Fremont",
        "state": "CA",
        "country": "USA",
        "lat": 37.55,
        "lon": -121.98,
        "capacity_units": 2000,
        "fixed_cost_monthly": 150_000,
        "is_active": 1,
    },
    {
        "id": "DC-AU",
        "name": "Austin DC",
        "city": "Austin",
        "state": "TX",
        "country": "USA",
        "lat": 30.27,
        "lon": -97.74,
        "capacity_units": 1800,
        "fixed_cost_monthly": 120_000,
        "is_active": 1,
    },
    {
        "id": "DC-LA",
        "name": "Lathrop DC",
        "city": "Lathrop",
        "state": "CA",
        "country": "USA",
        "lat": 37.82,
        "lon": -121.28,
        "capacity_units": 1500,
        "fixed_cost_monthly": 100_000,
        "is_active": 1,
    },
    {
        "id": "DC-ME",
        "name": "Memphis Hub",
        "city": "Memphis",
        "state": "TN",
        "country": "USA",
        "lat": 35.15,
        "lon": -90.05,
        "capacity_units": 2200,
        "fixed_cost_monthly": 130_000,
        "is_active": 1,
    },
]

# 20 routes: (origin_id, dest_id, mode, distance_miles, base_cost_per_unit, transit_days, capacity_per_day)
# Cost logic:
#   ocean:  cheapest per unit long-distance (~$4-6/unit/1000 miles)
#   truck:  cheapest short-distance (<2000 mi), $6-12/unit/1000 miles
#   rail:   middle ground, $4-8/unit/1000 miles
#   air:    most expensive, ~$8-15/unit/1000 miles
# Transit logic:
#   ocean: 500-600 miles/day (20-25 days transoceanic)
#   truck: 600-700 miles/day
#   rail:  450-550 miles/day
#   air:   <1 day (2-3 days door-to-door including customs)

ROUTES = [
    # ── Shanghai → US DCs (transoceanic — ocean dominant, air premium) ──
    {
        "id": "RT-001",
        "origin_id": "SUP-SH",
        "destination_id": "DC-FR",
        "mode": "ocean",
        "distance_miles": 7450,
        "base_cost_per_unit": 44.0,
        "transit_days": 22,
        "capacity_units_per_day": 200,
    },
    {
        "id": "RT-002",
        "origin_id": "SUP-SH",
        "destination_id": "DC-FR",
        "mode": "air",
        "distance_miles": 7450,
        "base_cost_per_unit": 78.0,
        "transit_days": 3,
        "capacity_units_per_day": 80,
    },
    {
        "id": "RT-003",
        "origin_id": "SUP-SH",
        "destination_id": "DC-LA",
        "mode": "ocean",
        "distance_miles": 7200,
        "base_cost_per_unit": 42.0,
        "transit_days": 21,
        "capacity_units_per_day": 180,
    },
    {
        "id": "RT-004",
        "origin_id": "SUP-SH",
        "destination_id": "DC-ME",
        "mode": "ocean",
        "distance_miles": 9100,
        "base_cost_per_unit": 52.0,
        "transit_days": 25,
        "capacity_units_per_day": 150,
    },
    # ── Shenzhen → US DCs ──
    {
        "id": "RT-005",
        "origin_id": "SUP-SZ",
        "destination_id": "DC-FR",
        "mode": "ocean",
        "distance_miles": 7350,
        "base_cost_per_unit": 43.0,
        "transit_days": 21,
        "capacity_units_per_day": 200,
    },
    {
        "id": "RT-006",
        "origin_id": "SUP-SZ",
        "destination_id": "DC-FR",
        "mode": "air",
        "distance_miles": 7350,
        "base_cost_per_unit": 75.0,
        "transit_days": 3,
        "capacity_units_per_day": 75,
    },
    {
        "id": "RT-007",
        "origin_id": "SUP-SZ",
        "destination_id": "DC-AU",
        "mode": "ocean",
        "distance_miles": 8300,
        "base_cost_per_unit": 48.0,
        "transit_days": 23,
        "capacity_units_per_day": 160,
    },
    {
        "id": "RT-008",
        "origin_id": "SUP-SZ",
        "destination_id": "DC-LA",
        "mode": "ocean",
        "distance_miles": 7050,
        "base_cost_per_unit": 41.0,
        "transit_days": 20,
        "capacity_units_per_day": 170,
    },
    # ── Munich → US DCs (transatlantic — ocean + air) ──
    {
        "id": "RT-009",
        "origin_id": "SUP-MU",
        "destination_id": "DC-FR",
        "mode": "ocean",
        "distance_miles": 6350,
        "base_cost_per_unit": 39.0,
        "transit_days": 18,
        "capacity_units_per_day": 150,
    },
    {
        "id": "RT-010",
        "origin_id": "SUP-MU",
        "destination_id": "DC-FR",
        "mode": "air",
        "distance_miles": 6350,
        "base_cost_per_unit": 67.0,
        "transit_days": 2,
        "capacity_units_per_day": 80,
    },
    {
        "id": "RT-011",
        "origin_id": "SUP-MU",
        "destination_id": "DC-ME",
        "mode": "ocean",
        "distance_miles": 5500,
        "base_cost_per_unit": 35.0,
        "transit_days": 16,
        "capacity_units_per_day": 130,
    },
    {
        "id": "RT-012",
        "origin_id": "SUP-MU",
        "destination_id": "DC-AU",
        "mode": "ocean",
        "distance_miles": 5900,
        "base_cost_per_unit": 37.0,
        "transit_days": 17,
        "capacity_units_per_day": 120,
    },
    # ── Monterrey → US DCs (truck + rail — nearshore advantage) ──
    {
        "id": "RT-013",
        "origin_id": "SUP-MO",
        "destination_id": "DC-AU",
        "mode": "truck",
        "distance_miles": 890,
        "base_cost_per_unit": 11.0,
        "transit_days": 2,
        "capacity_units_per_day": 320,
    },
    {
        "id": "RT-014",
        "origin_id": "SUP-MO",
        "destination_id": "DC-AU",
        "mode": "rail",
        "distance_miles": 890,
        "base_cost_per_unit": 7.5,
        "transit_days": 4,
        "capacity_units_per_day": 420,
    },
    {
        "id": "RT-015",
        "origin_id": "SUP-MO",
        "destination_id": "DC-FR",
        "mode": "truck",
        "distance_miles": 2250,
        "base_cost_per_unit": 23.0,
        "transit_days": 5,
        "capacity_units_per_day": 180,
    },
    {
        "id": "RT-016",
        "origin_id": "SUP-MO",
        "destination_id": "DC-ME",
        "mode": "truck",
        "distance_miles": 1120,
        "base_cost_per_unit": 13.5,
        "transit_days": 3,
        "capacity_units_per_day": 260,
    },
    {
        "id": "RT-017",
        "origin_id": "SUP-MO",
        "destination_id": "DC-ME",
        "mode": "rail",
        "distance_miles": 1120,
        "base_cost_per_unit": 9.0,
        "transit_days": 5,
        "capacity_units_per_day": 360,
    },
    # ── Detroit → US DCs (domestic — truck + rail) ──
    {
        "id": "RT-018",
        "origin_id": "SUP-DE",
        "destination_id": "DC-ME",
        "mode": "truck",
        "distance_miles": 830,
        "base_cost_per_unit": 10.0,
        "transit_days": 2,
        "capacity_units_per_day": 300,
    },
    {
        "id": "RT-019",
        "origin_id": "SUP-DE",
        "destination_id": "DC-ME",
        "mode": "rail",
        "distance_miles": 830,
        "base_cost_per_unit": 6.5,
        "transit_days": 4,
        "capacity_units_per_day": 420,
    },
    {
        "id": "RT-020",
        "origin_id": "SUP-DE",
        "destination_id": "DC-AU",
        "mode": "truck",
        "distance_miles": 1320,
        "base_cost_per_unit": 15.5,
        "transit_days": 3,
        "capacity_units_per_day": 250,
    },

    # ── Extra routes added for richer coverage ────────────────────────────────
    # Shenzhen→Austin: adds truck mode so truck-vs-ocean comparison is possible
    {
        "id": "RT-021",
        "origin_id": "SUP-SZ",
        "destination_id": "DC-AU",
        "mode": "truck",           # intermodal (ocean + final-mile), labelled truck
        "distance_miles": 8300,
        "base_cost_per_unit": 62.0,
        "transit_days": 16,
        "capacity_units_per_day": 120,
    },
    # Shanghai→Austin: ocean lane to reach the US mid-continent DC
    {
        "id": "RT-022",
        "origin_id": "SUP-SH",
        "destination_id": "DC-AU",
        "mode": "ocean",
        "distance_miles": 8400,
        "base_cost_per_unit": 50.0,
        "transit_days": 24,
        "capacity_units_per_day": 140,
    },
    # Monterrey→Lathrop: nearshore truck + rail to West-Coast DC
    {
        "id": "RT-023",
        "origin_id": "SUP-MO",
        "destination_id": "DC-LA",
        "mode": "truck",
        "distance_miles": 1350,
        "base_cost_per_unit": 15.0,
        "transit_days": 3,
        "capacity_units_per_day": 240,
    },
    {
        "id": "RT-024",
        "origin_id": "SUP-MO",
        "destination_id": "DC-LA",
        "mode": "rail",
        "distance_miles": 1350,
        "base_cost_per_unit": 10.5,
        "transit_days": 6,
        "capacity_units_per_day": 360,
    },
    # Detroit→Fremont: cross-country truck + rail
    {
        "id": "RT-025",
        "origin_id": "SUP-DE",
        "destination_id": "DC-FR",
        "mode": "truck",
        "distance_miles": 2380,
        "base_cost_per_unit": 26.0,
        "transit_days": 5,
        "capacity_units_per_day": 200,
    },
    {
        "id": "RT-026",
        "origin_id": "SUP-DE",
        "destination_id": "DC-LA",
        "mode": "rail",
        "distance_miles": 2380,
        "base_cost_per_unit": 18.0,
        "transit_days": 8,
        "capacity_units_per_day": 300,
    },
    # Munich→Lathrop: transatlantic ocean (East-Coast → Panama Canal → LA)
    {
        "id": "RT-027",
        "origin_id": "SUP-MU",
        "destination_id": "DC-LA",
        "mode": "ocean",
        "distance_miles": 6100,
        "base_cost_per_unit": 38.0,
        "transit_days": 18,
        "capacity_units_per_day": 140,
    },
    # Shenzhen→Memphis: Asia-to-mid-South lane
    {
        "id": "RT-028",
        "origin_id": "SUP-SZ",
        "destination_id": "DC-ME",
        "mode": "ocean",
        "distance_miles": 9800,
        "base_cost_per_unit": 57.0,
        "transit_days": 27,
        "capacity_units_per_day": 130,
    },
    # Shanghai→Memphis: air express for time-critical parts
    {
        "id": "RT-029",
        "origin_id": "SUP-SH",
        "destination_id": "DC-ME",
        "mode": "air",
        "distance_miles": 9100,
        "base_cost_per_unit": 88.0,
        "transit_days": 3,
        "capacity_units_per_day": 60,
    },
    # Detroit→Lathrop: domestic rail option to West Coast
    {
        "id": "RT-030",
        "origin_id": "SUP-DE",
        "destination_id": "DC-FR",
        "mode": "rail",
        "distance_miles": 2380,
        "base_cost_per_unit": 19.5,
        "transit_days": 7,
        "capacity_units_per_day": 280,
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles."""
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _seasonal_multiplier(month: int) -> float:
    """Q4 holiday surge; Q1 post-holiday dip."""
    if month in (11, 12):
        return random.uniform(1.10, 1.25)
    if month in (1, 2):
        return random.uniform(0.88, 0.96)
    if month in (7, 8, 9):
        return random.uniform(1.02, 1.12)
    return random.uniform(0.95, 1.08)


def _congestion_factor(mode: str) -> float:
    """Trucking is most susceptible to congestion."""
    if mode == "truck":
        return random.uniform(0.85, 1.35)
    if mode == "ocean":
        return random.uniform(0.90, 1.20)
    if mode == "rail":
        return random.uniform(0.90, 1.15)
    return random.uniform(0.95, 1.10)  # air


# ── DDL ───────────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS suppliers (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    city                  TEXT,
    country               TEXT,
    lat                   REAL,
    lon                   REAL,
    capacity_units_per_day INTEGER
);

CREATE TABLE IF NOT EXISTS distribution_centers (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    city                 TEXT,
    state                TEXT,
    country              TEXT,
    lat                  REAL,
    lon                  REAL,
    capacity_units       INTEGER,
    fixed_cost_monthly   REAL,
    is_active            INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS routes (
    id                    TEXT PRIMARY KEY,
    origin_id             TEXT NOT NULL,
    destination_id        TEXT NOT NULL,
    mode                  TEXT CHECK(mode IN ('truck','rail','ocean','air')),
    distance_miles        REAL,
    base_cost_per_unit    REAL,
    transit_days          REAL,
    capacity_units_per_day INTEGER,
    FOREIGN KEY (origin_id)      REFERENCES suppliers(id),
    FOREIGN KEY (destination_id) REFERENCES distribution_centers(id)
);

CREATE TABLE IF NOT EXISTS shipments (
    id                   TEXT PRIMARY KEY,
    route_id             TEXT NOT NULL,
    shipment_date        TEXT NOT NULL,
    units                INTEGER,
    actual_cost          REAL,
    actual_transit_days  REAL,
    on_time              INTEGER,
    congestion_factor    REAL,
    season               INTEGER,
    FOREIGN KEY (route_id) REFERENCES routes(id)
);

CREATE TABLE IF NOT EXISTS simulation_results (
    id                 TEXT PRIMARY KEY,
    scenario_name      TEXT,
    created_at         TEXT,
    total_cost         REAL,
    avg_transit_days   REAL,
    service_level_pct  REAL,
    config_json        TEXT
);
"""


# ── Seed helpers ──────────────────────────────────────────────────────────────

def _already_seeded(conn: sqlite3.Connection) -> bool:
    cursor = conn.execute("SELECT COUNT(*) FROM suppliers")
    return cursor.fetchone()[0] > 0


def _seed_suppliers(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """INSERT OR IGNORE INTO suppliers
           (id, name, city, country, lat, lon, capacity_units_per_day)
           VALUES (:id, :name, :city, :country, :lat, :lon, :capacity_units_per_day)""",
        SUPPLIERS,
    )


def _seed_dcs(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """INSERT OR IGNORE INTO distribution_centers
           (id, name, city, state, country, lat, lon, capacity_units, fixed_cost_monthly, is_active)
           VALUES (:id, :name, :city, :state, :country, :lat, :lon, :capacity_units, :fixed_cost_monthly, :is_active)""",
        DISTRIBUTION_CENTERS,
    )


def _seed_routes(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """INSERT OR IGNORE INTO routes
           (id, origin_id, destination_id, mode, distance_miles, base_cost_per_unit, transit_days, capacity_units_per_day)
           VALUES (:id, :origin_id, :destination_id, :mode, :distance_miles, :base_cost_per_unit, :transit_days, :capacity_units_per_day)""",
        ROUTES,
    )


def _seed_shipments(conn: sqlite3.Connection, n: int = 20_000) -> None:
    """
    Generate n historical shipment records over 2 years.

    Realistic distributions:
    - Units:  10–200 (heavier tail for bulk routes)
    - Cost:   base_cost * units * seasonal_mult * congestion * jitter
    - Transit: base_transit * congestion * jitter; capped at +40%
    - On-time: actual_transit <= base_transit * 1.1
    """
    start_date = date(2023, 1, 1)
    end_date = date(2024, 12, 31)
    date_range_days = (end_date - start_date).days

    # Route weights: higher-capacity routes get proportionally more shipments
    route_weights = [r["capacity_units_per_day"] for r in ROUTES]
    total_weight = sum(route_weights)
    route_probs = [w / total_weight for w in route_weights]

    rows = []
    for _ in range(n):
        # Pick route
        route = random.choices(ROUTES, weights=route_probs, k=1)[0]

        # Pick date
        offset = random.randint(0, date_range_days)
        shipment_date = start_date + timedelta(days=offset)
        month = shipment_date.month
        season = (month - 1) // 3 + 1  # 1=Q1 … 4=Q4

        # Units — larger variance for bulk ocean/rail; smaller for expensive air
        if route["mode"] == "air":
            units = random.randint(10, 80)
        elif route["mode"] in ("ocean",):
            units = random.randint(40, 200)
        else:
            units = random.randint(20, 150)

        # Cost factors
        season_mult = _seasonal_multiplier(month)
        congestion = _congestion_factor(route["mode"])
        cost_jitter = random.uniform(0.90, 1.15)

        actual_cost = round(
            route["base_cost_per_unit"] * units * season_mult * congestion * cost_jitter, 2
        )

        # Transit factors (ocean most variable; air least)
        if route["mode"] == "ocean":
            transit_jitter = random.uniform(0.85, 1.40)
        elif route["mode"] == "truck":
            transit_jitter = random.uniform(0.80, 1.35)
        elif route["mode"] == "rail":
            transit_jitter = random.uniform(0.88, 1.25)
        else:  # air
            transit_jitter = random.uniform(0.90, 1.20)

        actual_transit = round(route["transit_days"] * transit_jitter, 1)
        on_time = 1 if actual_transit <= route["transit_days"] * 1.1 else 0

        rows.append(
            (
                str(uuid.uuid4()),
                route["id"],
                shipment_date.isoformat(),
                units,
                actual_cost,
                actual_transit,
                on_time,
                round(congestion, 3),
                season,
            )
        )

    conn.executemany(
        """INSERT INTO shipments
           (id, route_id, shipment_date, units, actual_cost, actual_transit_days,
            on_time, congestion_factor, season)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        rows,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def init_db() -> None:
    """
    Create tables and seed synthetic data if the database is empty.
    Safe to call on every startup (idempotent).
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(DDL)

    if not _already_seeded(conn):
        print("🌱  Seeding synthetic supply chain data …")
        random.seed(SEED)
        _seed_suppliers(conn)
        _seed_dcs(conn)
        _seed_routes(conn)
        _seed_shipments(conn)
        conn.commit()
        print(f"✅  Seeded {len(SUPPLIERS)} suppliers, {len(DISTRIBUTION_CENTERS)} DCs, "
              f"{len(ROUTES)} routes, 20 000 shipments.")
    else:
        print("✅  Database already seeded — skipping.")

    conn.close()


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with FK enforcement and row-factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


if __name__ == "__main__":
    init_db()
    print(f"DB at: {DB_PATH}")
