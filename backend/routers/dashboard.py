"""
Dashboard KPI and analytics endpoints.
"""
from fastapi import APIRouter
from database import get_connection
from models import KPIDashboard, KPICard, CostBreakdown, CostBreakdownItem, TopRoute, BottleneckAlert

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard/kpis", response_model=KPIDashboard)
def get_kpis():
    with get_connection() as conn:
        # Anchor date: latest shipment date in the database
        anchor = conn.execute(
            "SELECT MAX(shipment_date) as max_date, "
            "date(MAX(shipment_date), '-90 days') as cutoff FROM shipments"
        ).fetchone()

        # Total cost last quarter (90 days back from latest data)
        q_cost = conn.execute("""
            SELECT COALESCE(SUM(actual_cost), 0) as total,
                   COALESCE(AVG(actual_transit_days), 0) as avg_transit,
                   COALESCE(AVG(on_time) * 100, 0) as svc_level,
                   COUNT(*) as shipment_count
            FROM shipments
            WHERE shipment_date >= (SELECT date(MAX(shipment_date), '-90 days') FROM shipments)
        """).fetchone()

        # Network utilization: avg actual flow vs capacity across routes
        util = conn.execute("""
            SELECT
                AVG(CAST(daily_units AS REAL) / r.capacity_units_per_day) * 100 as util_pct
            FROM (
                SELECT route_id, AVG(units) as daily_units
                FROM shipments
                WHERE shipment_date >= (SELECT date(MAX(shipment_date), '-90 days') FROM shipments)
                GROUP BY route_id
            ) s
            JOIN routes r ON r.id = s.route_id
        """).fetchone()

    total_cost = round(q_cost["total"], 2)
    avg_transit = round(q_cost["avg_transit"], 1)
    svc_level = round(q_cost["svc_level"], 1)
    utilization = round(util["util_pct"] or 0.0, 1)

    period = f"{anchor['cutoff']} → {anchor['max_date']}" if anchor["max_date"] else "last 90 days"

    cards = [
        KPICard(label=f"Total Inbound Cost", value=f"${total_cost:,.0f}", unit=period, trend="flat"),
        KPICard(label="Avg Transit Time", value=str(avg_transit), unit="days", trend="down"),
        KPICard(label="Service Level", value=f"{svc_level}%", unit="on-time", trend="up"),
        KPICard(label="Network Utilization", value=f"{utilization}%", unit="capacity", trend="flat"),
    ]

    return KPIDashboard(
        total_cost_quarter=total_cost,
        avg_transit_days=avg_transit,
        service_level_pct=svc_level,
        network_utilization_pct=utilization,
        cards=cards,
    )


@router.get("/dashboard/cost-breakdown", response_model=CostBreakdown)
def get_cost_breakdown():
    with get_connection() as conn:
        by_mode = conn.execute("""
            SELECT r.mode as category,
                   SUM(s.actual_cost) as cost,
                   COUNT(*) as shipment_count,
                   AVG(s.actual_cost / s.units) as avg_cost_per_unit
            FROM shipments s JOIN routes r ON r.id = s.route_id
            WHERE s.shipment_date >= (SELECT date(MAX(shipment_date), '-90 days') FROM shipments)
            GROUP BY r.mode
            ORDER BY cost DESC
        """).fetchall()

        by_supplier = conn.execute("""
            SELECT sup.name as category,
                   SUM(s.actual_cost) as cost,
                   COUNT(*) as shipment_count,
                   AVG(s.actual_cost / s.units) as avg_cost_per_unit
            FROM shipments s
            JOIN routes r ON r.id = s.route_id
            JOIN suppliers sup ON sup.id = r.origin_id
            WHERE s.shipment_date >= (SELECT date(MAX(shipment_date), '-90 days') FROM shipments)
            GROUP BY sup.name
            ORDER BY cost DESC
        """).fetchall()

        by_dc = conn.execute("""
            SELECT dc.name as category,
                   SUM(s.actual_cost) as cost,
                   COUNT(*) as shipment_count,
                   AVG(s.actual_cost / s.units) as avg_cost_per_unit
            FROM shipments s
            JOIN routes r ON r.id = s.route_id
            JOIN distribution_centers dc ON dc.id = r.destination_id
            WHERE s.shipment_date >= (SELECT date(MAX(shipment_date), '-90 days') FROM shipments)
            GROUP BY dc.name
            ORDER BY cost DESC
        """).fetchall()

    def to_items(rows) -> list[CostBreakdownItem]:
        return [
            CostBreakdownItem(
                category=r["category"],
                cost=round(r["cost"], 2),
                shipment_count=r["shipment_count"],
                avg_cost_per_unit=round(r["avg_cost_per_unit"], 2),
            )
            for r in rows
        ]

    return CostBreakdown(
        by_mode=to_items(by_mode),
        by_supplier=to_items(by_supplier),
        by_dc=to_items(by_dc),
    )


@router.get("/dashboard/top-routes", response_model=list[TopRoute])
def get_top_routes(limit: int = 10):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                r.id as route_id,
                sup.name as origin,
                dc.name as destination,
                r.mode,
                SUM(s.actual_cost) as total_cost,
                COUNT(*) as shipment_count,
                AVG(s.actual_transit_days) as avg_transit_days,
                AVG(s.on_time) * 100 as on_time_pct
            FROM shipments s
            JOIN routes r ON r.id = s.route_id
            JOIN suppliers sup ON sup.id = r.origin_id
            JOIN distribution_centers dc ON dc.id = r.destination_id
            WHERE s.shipment_date >= (SELECT date(MAX(shipment_date), '-90 days') FROM shipments)
            GROUP BY r.id
            ORDER BY total_cost DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [
        TopRoute(
            route_id=r["route_id"],
            origin=r["origin"],
            destination=r["destination"],
            mode=r["mode"],
            total_cost=round(r["total_cost"], 2),
            shipment_count=r["shipment_count"],
            avg_transit_days=round(r["avg_transit_days"], 1),
            on_time_pct=round(r["on_time_pct"], 1),
        )
        for r in rows
    ]


@router.get("/dashboard/bottlenecks", response_model=list[BottleneckAlert])
def get_bottlenecks():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                r.id as entity_id,
                sup.name || ' → ' || dc.name || ' (' || r.mode || ')' as entity_name,
                AVG(s.units) as daily_avg,
                r.capacity_units_per_day as capacity,
                CAST(AVG(s.units) AS REAL) / r.capacity_units_per_day * 100 as util_pct
            FROM shipments s
            JOIN routes r ON r.id = s.route_id
            JOIN suppliers sup ON sup.id = r.origin_id
            JOIN distribution_centers dc ON dc.id = r.destination_id
            WHERE s.shipment_date >= (SELECT date(MAX(shipment_date), '-90 days') FROM shipments)
            GROUP BY r.id
            HAVING util_pct > 60
            ORDER BY util_pct DESC
        """).fetchall()

    alerts: list[BottleneckAlert] = []
    for r in rows:
        pct = round(r["util_pct"], 1)
        if pct >= 90:
            severity = "critical"
        elif pct >= 80:
            severity = "high"
        elif pct >= 70:
            severity = "medium"
        else:
            severity = "low"

        alerts.append(BottleneckAlert(
            entity_id=r["entity_id"],
            entity_name=r["entity_name"],
            entity_type="route",
            utilization_pct=pct,
            severity=severity,
            message=f"{r['entity_name']} is at {pct}% utilization — risk of delays.",
        ))

    return alerts
