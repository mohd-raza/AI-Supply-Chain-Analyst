"""
Network data endpoints — suppliers, DCs, routes, graph.
"""
from fastapi import APIRouter, HTTPException
from database import get_connection
from models import Supplier, DistributionCenter, Route, NetworkGraph, NetworkNode, NetworkEdge

router = APIRouter(tags=["Network"])


@router.get("/network/suppliers", response_model=list[Supplier])
def list_suppliers():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM suppliers").fetchall()
    return [dict(r) for r in rows]


@router.get("/network/dcs", response_model=list[DistributionCenter])
def list_dcs():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM distribution_centers").fetchall()
    return [dict(r) for r in rows]


@router.get("/network/routes", response_model=list[Route])
def list_routes():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM routes").fetchall()
    return [dict(r) for r in rows]


@router.get("/network", response_model=NetworkGraph)
def get_network_graph():
    with get_connection() as conn:
        suppliers = conn.execute("SELECT * FROM suppliers").fetchall()
        dcs = conn.execute("SELECT * FROM distribution_centers").fetchall()
        routes = conn.execute("SELECT * FROM routes").fetchall()
        # Average flow per route from last 90 days of shipments
        flows = conn.execute("""
            SELECT route_id, AVG(units) as avg_units
            FROM shipments
            WHERE shipment_date >= date('now', '-90 days')
            GROUP BY route_id
        """).fetchall()

    flow_map = {r["route_id"]: r["avg_units"] for r in flows}

    nodes: list[NetworkNode] = []
    for s in suppliers:
        nodes.append(NetworkNode(
            id=s["id"], name=s["name"], type="supplier",
            city=s["city"], country=s["country"],
            lat=s["lat"], lon=s["lon"], capacity=s["capacity_units_per_day"],
        ))
    for dc in dcs:
        nodes.append(NetworkNode(
            id=dc["id"], name=dc["name"], type="dc",
            city=dc["city"], country=dc["country"],
            lat=dc["lat"], lon=dc["lon"], capacity=dc["capacity_units"],
        ))

    edges: list[NetworkEdge] = [
        NetworkEdge(
            id=r["id"], source=r["origin_id"], target=r["destination_id"],
            mode=r["mode"], distance_miles=r["distance_miles"],
            base_cost_per_unit=r["base_cost_per_unit"],
            transit_days=r["transit_days"],
            capacity_units_per_day=r["capacity_units_per_day"],
            flow_volume=flow_map.get(r["id"]),
        )
        for r in routes
    ]

    return NetworkGraph(nodes=nodes, edges=edges)
