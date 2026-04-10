"""
PuLP-based network flow optimizer.
"""
from __future__ import annotations
import time
from models import OptimizeRequest, OptimizeResponse, RouteFlow

try:
    from pulp import (
        LpProblem, LpMinimize, LpVariable, lpSum, value,
        PULP_CBC_CMD, LpStatusInfeasible,
    )
    PULP_AVAILABLE = True
except ImportError:
    PULP_AVAILABLE = False

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from database import get_connection


async def run_optimization(request: OptimizeRequest) -> OptimizeResponse:
    if not PULP_AVAILABLE:
        raise RuntimeError("PuLP not installed — run: pip install pulp")

    t0 = time.time()

    with get_connection() as conn:
        routes = conn.execute("SELECT * FROM routes").fetchall()
        dcs = conn.execute("SELECT * FROM distribution_centers WHERE is_active=1").fetchall()

    dc_ids = [dc["id"] for dc in dcs]
    dc_capacity = {dc["id"]: dc["capacity_units"] * 30 for dc in dcs}  # daily → monthly
    dc_fixed_cost = {dc["id"]: dc["fixed_cost_monthly"] for dc in dcs}

    demand = request.demand
    budget = request.budget

    prob = LpProblem("ChainMindNetworkOpt", LpMinimize)

    # Decision variables
    flow = {
        r["id"]: LpVariable(f"flow_{r['id']}", lowBound=0, upBound=r["capacity_units_per_day"] * 30)
        for r in routes
    }
    open_dc = {
        dc_id: LpVariable(f"open_{dc_id}", cat="Binary")
        for dc_id in dc_ids
    }

    # Objective: variable shipping cost + fixed DC cost
    prob += (
        lpSum(r["base_cost_per_unit"] * flow[r["id"]] for r in routes)
        + lpSum(dc_fixed_cost[j] * open_dc[j] for j in dc_ids)
    )

    # Demand satisfaction per DC
    for dc_id, dem in demand.items():
        relevant = [r for r in routes if r["destination_id"] == dc_id]
        if relevant:
            prob += lpSum(flow[r["id"]] for r in relevant) >= dem

    # DC capacity
    for dc in dcs:
        dc_id = dc["id"]
        relevant = [r for r in routes if r["destination_id"] == dc_id]
        if relevant:
            prob += lpSum(flow[r["id"]] for r in relevant) <= dc_capacity[dc_id] * open_dc[dc_id]

    # Budget constraint
    prob += (
        lpSum(r["base_cost_per_unit"] * flow[r["id"]] for r in routes)
        + lpSum(dc_fixed_cost[j] * open_dc[j] for j in dc_ids)
        <= budget
    )

    # Force-open specific DCs
    if request.open_dcs:
        for dc_id in request.open_dcs:
            if dc_id in open_dc:
                prob += open_dc[dc_id] == 1

    solver = PULP_CBC_CMD(msg=0, timeLimit=30)
    prob.solve(solver)

    elapsed = round(time.time() - t0, 3)

    if prob.status == LpStatusInfeasible:
        return OptimizeResponse(
            status="infeasible",
            total_cost=0,
            open_dcs=[],
            closed_dcs=dc_ids,
            route_flows=[],
            dc_utilization={},
            solver_gap_pct=0,
            solve_time_seconds=elapsed,
        )

    opened = [j for j in dc_ids if value(open_dc[j]) and value(open_dc[j]) > 0.5]
    closed = [j for j in dc_ids if j not in opened]

    route_flows: list[RouteFlow] = []
    for r in routes:
        fv = value(flow[r["id"]]) or 0.0
        if fv > 0.01:
            route_flows.append(RouteFlow(
                route_id=r["id"],
                origin=r["origin_id"],
                destination=r["destination_id"],
                mode=r["mode"],
                flow_units=round(fv, 1),
                cost=round(r["base_cost_per_unit"] * fv, 2),
            ))

    total_cost = round(value(prob.objective) or 0.0, 2)

    # DC utilization
    dc_util: dict[str, float] = {}
    for dc in dcs:
        dc_id = dc["id"]
        inflow = sum(
            value(flow[r["id"]]) or 0.0
            for r in routes if r["destination_id"] == dc_id
        )
        dc_util[dc_id] = round(inflow / dc_capacity[dc_id] * 100, 1) if dc_id in opened else 0.0

    return OptimizeResponse(
        status="optimal",
        total_cost=total_cost,
        open_dcs=opened,
        closed_dcs=closed,
        route_flows=route_flows,
        dc_utilization=dc_util,
        solver_gap_pct=0.0,
        solve_time_seconds=elapsed,
    )
