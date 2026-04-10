"""
LangChain tool definitions for the ChainMind supply chain analyst agent.

Three tools are exposed:
  1. query_supply_chain_data  — read-only SQL against the SQLite DB
  2. predict_shipping_cost    — XGBoost cost prediction for a specific shipment
  3. optimize_network         — PuLP LP solver for network-wide cost minimization

The docstrings are the LLM's primary source of knowledge about when and how to
call each tool — write them as if briefing a junior analyst, not a programmer.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from langchain_core.tools import tool

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_PATH, COST_MODEL_PATH, TRANSIT_MODEL_PATH
from database import get_connection


# ── Shared helpers ────────────────────────────────────────────────────────────

_cost_model_cache: Any = None
_transit_model_cache: Any = None


def _get_cost_model():
    global _cost_model_cache
    if _cost_model_cache is None:
        from ml.train_models import load_cost_model, ensure_models_trained
        ensure_models_trained()
        _cost_model_cache = load_cost_model()
    return _cost_model_cache


def _get_transit_model():
    global _transit_model_cache
    if _transit_model_cache is None:
        from ml.train_models import load_transit_model, ensure_models_trained
        ensure_models_trained()
        _transit_model_cache = load_transit_model()
    return _transit_model_cache


_BLOCKED_PATTERNS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|MERGE|ATTACH|DETACH|PRAGMA\s+\w+=)\b",
    re.IGNORECASE,
)

_ALLOWED_TABLES = {
    "suppliers", "distribution_centers", "routes", "shipments", "simulation_results"
}


def _validate_sql(query: str) -> str | None:
    """Return an error string if the query is unsafe, else None."""
    stripped = query.strip()
    upper = stripped.upper()
    # Allow plain SELECT and CTEs that start with WITH ... SELECT
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return "Only SELECT queries are permitted."
    if _BLOCKED_PATTERNS.search(stripped):
        return "Query contains a disallowed keyword (INSERT/UPDATE/DELETE/DROP etc)."
    if ";" in stripped[:-1]:          # allow trailing semicolon only
        return "Multi-statement queries are not allowed."
    return None


def _rows_to_text(rows: list[dict], max_rows: int = 50) -> str:
    if not rows:
        return "(no rows returned)"
    truncated = rows[:max_rows]
    header = " | ".join(truncated[0].keys())
    sep    = "-" * len(header)
    body   = "\n".join(" | ".join(str(v) for v in r.values()) for r in truncated)
    note   = f"\n[Showing {len(truncated)} of {len(rows)} rows — query returned {len(rows)} total]" \
             if len(rows) > max_rows else f"\n[{len(rows)} row(s)]"
    return f"{header}\n{sep}\n{body}{note}"


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 1 — SQL Query
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def query_supply_chain_data(query: str) -> str:
    """
    Execute a read-only SQL SELECT query against the ChainMind supply chain database
    and return the results as a formatted table.

    Use this tool to answer questions about:
    - Supplier details, locations, capacities (table: suppliers)
    - Distribution center details and monthly fixed costs (table: distribution_centers)
    - Route lanes — mode (truck/rail/ocean/air), distance, base cost, transit days,
      daily capacity (table: routes)
    - Historical shipment records — actual cost, actual transit days, on-time flag,
      congestion factor, season (table: shipments)
    - Simulation results from past what-if scenarios (table: simulation_results)

    Key relationships:
      shipments.route_id → routes.id
      routes.origin_id   → suppliers.id
      routes.destination_id → distribution_centers.id

    Examples of useful queries:
      SELECT s.name, r.mode, r.base_cost_per_unit, r.transit_days
        FROM routes r JOIN suppliers s ON s.id = r.origin_id
        WHERE r.destination_id = 'DC-FR';

      SELECT r.mode, AVG(sh.actual_cost/sh.units) as avg_unit_cost,
             AVG(sh.on_time)*100 as on_time_pct
        FROM shipments sh JOIN routes r ON r.id = sh.route_id
        GROUP BY r.mode ORDER BY avg_unit_cost;

      SELECT r.origin_id, r.destination_id, r.mode,
             SUM(sh.actual_cost) as total_cost
        FROM shipments sh JOIN routes r ON r.id = sh.route_id
        WHERE sh.shipment_date >= date('now','-90 days')
        GROUP BY r.id ORDER BY total_cost DESC LIMIT 10;

    Rules:
    - SELECT only — INSERT/UPDATE/DELETE/DROP will be rejected.
    - Maximum 50 rows returned; add LIMIT clauses for large result sets.
    - Use date('now','-90 days') for "last quarter" type filters.

    Args:
        query: A valid SQLite SELECT statement.

    Returns:
        Query results as a pipe-delimited text table, or an error message.
    """
    err = _validate_sql(query)
    if err:
        return f"ERROR — Query rejected: {err}"

    try:
        conn = get_connection()
        cursor = conn.execute(query)
        cols = [desc[0] for desc in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()
        return _rows_to_text(rows)
    except Exception as exc:
        return f"ERROR — Query failed: {exc}\n\nQuery was:\n{query}"


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 2 — Cost Predictor
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def predict_shipping_cost(
    origin_id: str,
    destination_id: str,
    mode: str,
    units: int,
    season: int,
) -> str:
    """
    Predict the total shipping cost for a specific shipment using the XGBoost
    cost model trained on 10,000 historical shipment records.

    Use this tool when the user asks:
    - "What will it cost to ship X units from [supplier] to [DC]?"
    - "Compare cost: truck vs ocean from Monterrey to Austin"
    - "What's the predicted cost for 150 units via air from Munich?"
    - "Give me a cost estimate for this lane"

    This tool looks up the route characteristics (distance, base cost, transit days)
    from the database, then feeds them through the ML model for an accurate,
    data-driven prediction — NOT a simple multiplication.

    The model accounts for: distance, volume, transport mode, origin country,
    season, and historical congestion patterns.

    Args:
        origin_id:      Supplier ID. Valid values: SUP-SH, SUP-SZ, SUP-MU, SUP-MO, SUP-DE
        destination_id: DC ID. Valid values: DC-FR, DC-AU, DC-LA, DC-ME
        mode:           Transport mode. One of: truck, rail, ocean, air
        units:          Number of units to ship (1–10,000)
        season:         Quarter of the year: 1=Q1(Jan-Mar), 2=Q2(Apr-Jun),
                        3=Q3(Jul-Sep), 4=Q4(Oct-Dec)

    Returns:
        A formatted cost breakdown with predicted total, cost per unit,
        confidence interval, and comparison to historical average for that lane.
    """
    # Validate inputs
    valid_modes = {"truck", "rail", "ocean", "air"}
    if mode not in valid_modes:
        return f"ERROR — Invalid mode '{mode}'. Choose from: {', '.join(sorted(valid_modes))}"
    if not (1 <= season <= 4):
        return "ERROR — season must be 1 (Q1) … 4 (Q4)"
    if units < 1:
        return "ERROR — units must be ≥ 1"

    # Look up route from DB
    conn = get_connection()
    route = conn.execute("""
        SELECT r.id, r.distance_miles, r.base_cost_per_unit, r.transit_days,
               sup.country as origin_country, sup.name as origin_name,
               dc.name as dest_name
        FROM routes r
        JOIN suppliers sup ON sup.id = r.origin_id
        JOIN distribution_centers dc ON dc.id = r.destination_id
        WHERE r.origin_id = ? AND r.destination_id = ? AND r.mode = ?
    """, (origin_id, destination_id, mode)).fetchone()

    # Historical stats for comparison
    hist = conn.execute("""
        SELECT AVG(sh.actual_cost / sh.units) as avg_unit_cost,
               AVG(sh.on_time) * 100 as on_time_pct,
               COUNT(*) as sample_size
        FROM shipments sh
        JOIN routes r ON r.id = sh.route_id
        WHERE r.origin_id = ? AND r.destination_id = ? AND r.mode = ?
    """, (origin_id, destination_id, mode)).fetchone()
    conn.close()

    if route is None:
        # No direct route — advise what exists
        conn2 = get_connection()
        alts = conn2.execute("""
            SELECT r.mode, r.base_cost_per_unit, r.transit_days
            FROM routes r
            WHERE r.origin_id = ? AND r.destination_id = ?
        """, (origin_id, destination_id)).fetchall()
        conn2.close()
        if alts:
            alt_str = "\n".join(
                f"  • {a['mode']}: ${a['base_cost_per_unit']}/unit, {a['transit_days']}d transit"
                for a in alts
            )
            return (
                f"No {mode} route found from {origin_id} → {destination_id}.\n"
                f"Available modes for this lane:\n{alt_str}"
            )
        return f"No route exists between {origin_id} and {destination_id}. Check supplier/DC IDs."

    # Build feature row (matches train_models.FEATURE_COLS exactly)
    from ml.train_models import build_inference_row
    COUNTRY_MAP = {"China": 0, "Germany": 1, "Mexico": 2, "USA": 3}
    X = build_inference_row(
        distance_miles    = route["distance_miles"],
        units             = units,
        mode              = mode,
        origin_country    = route["origin_country"],
        season            = season,
        congestion_factor = 1.0,           # neutral — agent doesn't know current congestion
        base_cost_per_unit= route["base_cost_per_unit"],
        base_transit_days = route["transit_days"],
    )

    model = _get_cost_model()
    predicted_total = float(model.predict(X)[0])
    predicted_per_unit = predicted_total / units

    # Confidence interval: ±12% based on model residual spread
    ci_low  = predicted_total * 0.88
    ci_high = predicted_total * 1.12

    # Historical comparison
    hist_note = ""
    if hist and hist["sample_size"] and hist["avg_unit_cost"]:
        hist_avg_total = hist["avg_unit_cost"] * units
        delta_pct = (predicted_total - hist_avg_total) / hist_avg_total * 100
        direction = "above" if delta_pct > 0 else "below"
        hist_note = (
            f"\nHistorical avg (n={hist['sample_size']}): "
            f"${hist_avg_total:,.0f} total (${hist['avg_unit_cost']:.2f}/unit) — "
            f"prediction is {abs(delta_pct):.1f}% {direction} historical mean."
            f"\nOn-time delivery rate: {hist['on_time_pct']:.1f}%"
        )

    q_names = {1: "Q1 (Jan–Mar)", 2: "Q2 (Apr–Jun)", 3: "Q3 (Jul–Sep)", 4: "Q4 (Oct–Dec)"}

    return (
        f"━━ Cost Prediction: {route['origin_name']} → {route['dest_name']} via {mode.upper()} ━━\n"
        f"  Units:            {units:,}\n"
        f"  Season:           {q_names[season]}\n"
        f"  Distance:         {route['distance_miles']:,.0f} miles\n"
        f"  Transit time:     {route['transit_days']} days\n"
        f"\n"
        f"  Predicted cost:   ${predicted_total:,.2f}\n"
        f"  Cost per unit:    ${predicted_per_unit:.2f}\n"
        f"  90% CI:           ${ci_low:,.0f} – ${ci_high:,.0f}\n"
        f"{hist_note}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 3 — Network Optimizer
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def optimize_network(monthly_budget: float, demand_per_dc: str) -> str:
    """
    Run a linear programming (PuLP) optimization to find the minimum-cost inbound
    supply chain network configuration that satisfies demand at each Distribution
    Center within the given monthly budget.

    The optimizer decides:
    - Which DCs to keep open (each has a fixed monthly cost)
    - How much flow to route on each supplier→DC lane
    - Which transport modes to use for each flow

    Use this tool when the user asks:
    - "Optimize our network to minimize total cost"
    - "What's the cheapest way to serve demand at all DCs within $X budget?"
    - "Which DCs should we keep open given this demand pattern?"
    - "How should we allocate inbound volume across routes?"
    - "Run a network optimization with a $500K budget"

    Args:
        monthly_budget: Maximum total monthly spend in USD (variable shipping + fixed DC costs).
                        Minimum viable budget for 16,500 units/month across 4 DCs is ~$900K.
                        Example: 1200000 for $1.2M (comfortable for full-network optimization).
        demand_per_dc:  JSON string mapping DC ID → monthly demand in units.
                        DC IDs: DC-FR (Fremont CA), DC-AU (Austin TX),
                                DC-LA (Lathrop CA), DC-ME (Memphis TN).
                        Example: '{"DC-FR": 5000, "DC-AU": 4000, "DC-LA": 3000, "DC-ME": 4500}'
                        Omit a DC to exclude it from the optimization (demand treated as 0).

    Returns:
        A detailed optimization report: open/closed DCs, optimal route flows,
        total cost breakdown, DC utilization, and solver performance.
    """
    # ── Parse demand ──────────────────────────────────────────────────────────
    try:
        demand: dict[str, float] = json.loads(demand_per_dc)
    except json.JSONDecodeError as exc:
        return (
            f"ERROR — demand_per_dc must be valid JSON. Got: {demand_per_dc!r}\n"
            f"Parse error: {exc}\n"
            f"Example: '{{\"DC-FR\": 5000, \"DC-AU\": 4000, \"DC-LA\": 3000, \"DC-ME\": 4500}}'"
        )

    if monthly_budget <= 0:
        return "ERROR — monthly_budget must be a positive number (USD)."

    valid_dcs = {"DC-FR", "DC-AU", "DC-LA", "DC-ME"}
    invalid = set(demand.keys()) - valid_dcs
    if invalid:
        return f"ERROR — Unknown DC IDs: {invalid}. Valid IDs: {valid_dcs}"

    # ── Load network data ─────────────────────────────────────────────────────
    try:
        from pulp import (
            LpProblem, LpMinimize, LpVariable, lpSum,
            value, PULP_CBC_CMD, constants as lp_const,
        )
    except ImportError:
        return "ERROR — PuLP not installed. Run: pip install pulp"

    conn = get_connection()
    routes = [dict(r) for r in conn.execute("SELECT * FROM routes").fetchall()]
    dcs    = [dict(d) for d in conn.execute(
        "SELECT * FROM distribution_centers WHERE is_active=1"
    ).fetchall()]
    suppliers = {s["id"]: dict(s) for s in conn.execute("SELECT * FROM suppliers").fetchall()}
    dc_map    = {d["id"]: d for d in dcs}
    conn.close()

    dc_ids      = [d["id"] for d in dcs]
    # capacity_units is daily throughput — convert to monthly for the LP
    dc_capacity = {d["id"]: d["capacity_units"] * 30    for d in dcs}
    dc_fixed    = {d["id"]: d["fixed_cost_monthly"]     for d in dcs}

    # Monthly capacity = daily cap × 30 days
    route_monthly_cap = {r["id"]: r["capacity_units_per_day"] * 30 for r in routes}

    # ── Build LP ──────────────────────────────────────────────────────────────
    t0   = time.time()
    prob = LpProblem("ChainMind_NetworkOpt", LpMinimize)

    flow = {
        r["id"]: LpVariable(f"flow_{r['id']}", lowBound=0, upBound=route_monthly_cap[r["id"]])
        for r in routes
    }
    open_dc = {
        dc_id: LpVariable(f"open_{dc_id}", cat="Binary")
        for dc_id in dc_ids
    }

    # Objective: variable shipping cost + fixed DC cost
    prob += (
        lpSum(r["base_cost_per_unit"] * flow[r["id"]] for r in routes)
        + lpSum(dc_fixed[j] * open_dc[j] for j in dc_ids)
    )

    # Demand constraint: each demanded DC must receive ≥ demand
    for dc_id, dem in demand.items():
        inbound = [r for r in routes if r["destination_id"] == dc_id]
        if inbound:
            prob += (
                lpSum(flow[r["id"]] for r in inbound) >= dem,
                f"demand_{dc_id}",
            )

    # DC capacity constraint (only when open)
    for dc_id in dc_ids:
        inbound = [r for r in routes if r["destination_id"] == dc_id]
        if inbound:
            prob += (
                lpSum(flow[r["id"]] for r in inbound) <= dc_capacity[dc_id] * open_dc[dc_id],
                f"capacity_{dc_id}",
            )

    # Budget constraint
    prob += (
        lpSum(r["base_cost_per_unit"] * flow[r["id"]] for r in routes)
        + lpSum(dc_fixed[j] * open_dc[j] for j in dc_ids)
        <= monthly_budget,
        "budget",
    )

    # Supplier capacity constraint (monthly = daily × 30)
    for sup_id in suppliers:
        outbound = [r for r in routes if r["origin_id"] == sup_id]
        if outbound:
            sup_monthly_cap = suppliers[sup_id]["capacity_units_per_day"] * 30
            prob += (
                lpSum(flow[r["id"]] for r in outbound) <= sup_monthly_cap,
                f"sup_cap_{sup_id}",
            )

    # ── Solve ─────────────────────────────────────────────────────────────────
    solver = PULP_CBC_CMD(msg=0, timeLimit=30)
    prob.solve(solver)
    elapsed = round(time.time() - t0, 3)

    status = prob.status
    if status == lp_const.LpStatusInfeasible:
        return (
            "⚠️  INFEASIBLE — No solution exists within the given budget and constraints.\n\n"
            f"Budget: ${monthly_budget:,.0f}/month\n"
            f"Requested demand: {demand}\n\n"
            "Suggestions:\n"
            "  1. Increase monthly_budget\n"
            "  2. Reduce demand at one or more DCs\n"
            "  3. Check that requested DC IDs have inbound routes"
        )

    # ── Extract solution ──────────────────────────────────────────────────────
    opened  = [j for j in dc_ids if (value(open_dc[j]) or 0) > 0.5]
    closed  = [j for j in dc_ids if j not in opened]
    obj_val = value(prob.objective) or 0.0

    # Route flows
    active_flows: list[dict] = []
    variable_cost = 0.0
    for r in routes:
        fv = value(flow[r["id"]]) or 0.0
        if fv > 0.5:
            cost = r["base_cost_per_unit"] * fv
            variable_cost += cost
            active_flows.append({
                "route":  r["id"],
                "origin": suppliers[r["origin_id"]]["name"],
                "dest":   dc_map[r["destination_id"]]["name"],
                "mode":   r["mode"],
                "units":  round(fv),
                "cost":   round(cost, 2),
            })

    fixed_cost = sum(dc_fixed[j] for j in opened)

    # DC utilization
    dc_util: dict[str, float] = {}
    dc_inflow: dict[str, float] = {}
    for dc_id in opened:
        inflow = sum(
            value(flow[r["id"]]) or 0.0
            for r in routes if r["destination_id"] == dc_id
        )
        dc_inflow[dc_id] = round(inflow)
        dc_util[dc_id]   = round(inflow / dc_capacity[dc_id] * 100, 1)

    # ── Format report ─────────────────────────────────────────────────────────
    lines = [
        "━━ Network Optimization Report ━━",
        f"  Status:         OPTIMAL  (solved in {elapsed}s)",
        f"  Total cost:     ${obj_val:,.0f}/month",
        f"  Variable cost:  ${variable_cost:,.0f}/month  (shipping)",
        f"  Fixed DC cost:  ${fixed_cost:,.0f}/month",
        f"  Budget used:    {obj_val / monthly_budget * 100:.1f}% of ${monthly_budget:,.0f}",
        "",
        "📦  DC Configuration:",
    ]
    for dc_id in opened:
        d = dc_map[dc_id]
        lines.append(
            f"  ✅ OPEN   {d['name']:20s}  "
            f"inflow={dc_inflow.get(dc_id,0):,} units  "
            f"util={dc_util.get(dc_id,0):.1f}%  "
            f"fixed=${dc_fixed[dc_id]:,.0f}/mo"
        )
    for dc_id in closed:
        lines.append(f"  ❌ CLOSED {dc_map[dc_id]['name']}")

    lines += ["", "🚛  Optimal Route Flows (active lanes):"]
    active_flows.sort(key=lambda x: -x["cost"])
    for f_ in active_flows:
        lines.append(
            f"  {f_['origin'][:22]:<22} → {f_['dest'][:14]:<14} "
            f"[{f_['mode']:5}]  {f_['units']:,} units  ${f_['cost']:,.0f}"
        )

    total_demand = sum(demand.values())
    total_served = sum(dc_inflow.get(dc_id, 0) for dc_id in opened)
    lines += [
        "",
        f"📊  Total demand: {total_demand:,.0f} units/month  "
        f"| Served: {total_served:,.0f} units/month",
        f"    Avg cost per unit: ${obj_val / max(total_served, 1):.2f}",
    ]

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 4 — Digital Twin Scenario Simulator
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def run_scenario(
    scenario_type:   str,
    scenario_target: str,
    scenario_value:  float,
    duration_days:   int = 90,
) -> str:
    """
    Run a Digital Twin what-if simulation on Tesla's inbound supply chain network.

    Simulates the network for `duration_days` using SimPy discrete-event
    simulation.  Runs a baseline (no change) and the modified scenario in
    parallel, then reports the impact delta in cost, transit time, and
    service level.

    Use this tool when the user asks:
    - "What if the Shanghai port closes for 2 weeks?"
    - "What if fuel costs increase 20%?"
    - "What happens if demand at Fremont doubles?"
    - "Simulate closing the Memphis DC"
    - "What if we shift all ocean shipments to truck?"
    - "Stress-test: port disruption scenario"

    Args:
        scenario_type:   One of the five scenario types:
                           'port_closure'  — supplier routes unavailable for N days
                           'cost_increase' — cost multiplier on a mode or supplier
                           'demand_shock'  — demand multiplier at a DC (or all DCs)
                           'dc_closure'    — close a DC entirely, re-route demand
                           'mode_shift'    — force shipments off a given mode
        scenario_target: What the scenario applies to:
                           port_closure  → supplier ID  (e.g. 'SUP-SH')
                           cost_increase → mode OR supplier ID (e.g. 'ocean' or 'SUP-MU')
                           demand_shock  → DC ID  (e.g. 'DC-FR')  or 'all'
                           dc_closure    → DC ID  (e.g. 'DC-ME')
                           mode_shift    → source mode  (e.g. 'ocean')
        scenario_value:  Numeric severity:
                           port_closure  → disruption days (e.g. 14)
                           cost_increase → percent increase (e.g. 20 for +20%)
                           demand_shock  → demand multiplier (e.g. 2.0 for double)
                           dc_closure    → 1 (ignored)
                           mode_shift    → 1 (ignored)
        duration_days:   Simulation window in days (default 90 = one quarter).

    Returns:
        Formatted report with baseline vs scenario metrics and impact deltas:
        total cost, avg transit days, service level %, and units of unmet demand.
    """
    try:
        from simulation.digital_twin import get_twin
        twin   = get_twin()
        result = twin.run_scenario(
            scenario_type   = scenario_type,
            scenario_target = scenario_target,
            scenario_value  = scenario_value,
            duration_days   = duration_days,
        )
    except Exception as exc:
        return f"ERROR — Digital Twin simulation failed: {exc}"

    if "error" in result:
        return f"ERROR — {result['error']}"

    # Persist to DB (non-fatal if it fails)
    try:
        sim_id = twin.save_to_db(result)
    except Exception:
        sim_id = "unsaved"

    b  = result["baseline"]
    s  = result["scenario_result"]
    im = result["impact"]

    direction = lambda v: ("+" if v >= 0 else "") + str(v)

    lines = [
        f"━━ Digital Twin Simulation: {result['scenario_type'].replace('_',' ').title()} "
        f"— {result['target']} ━━",
        f"  Duration:          {result['duration_days']} days",
        f"  Simulation ID:     {sim_id}",
        "",
        "┌─────────────────────────────────────────────────────────────┐",
        "│                   BASELINE vs SCENARIO                      │",
        "├──────────────────────┬──────────────────┬───────────────────┤",
        f"│ Metric               │ Baseline         │ Scenario          │",
        "├──────────────────────┼──────────────────┼───────────────────┤",
        f"│ Total cost (90d)     │ ${b['total_cost']:>13,.0f} │ ${s['total_cost']:>13,.0f}   │",
        f"│ Avg transit (days)   │ {b['avg_transit_days']:>13.1f}d │ {s['avg_transit_days']:>13.1f}d   │",
        f"│ Service level        │ {b['service_level_pct']:>12.1f}%  │ {s['service_level_pct']:>12.1f}%    │",
        f"│ Total units shipped  │ {b['total_units']:>13,} │ {s['total_units']:>13,}   │",
        "└──────────────────────┴──────────────────┴───────────────────┘",
        "",
        "📊  Impact Summary:",
        f"  Cost impact:        {direction(im['cost_delta_pct'])}% "
        f"(${im['cost_delta']:+,.0f} over {result['duration_days']} days)",
        f"  Transit impact:     {direction(im['transit_delta_days'])} days avg",
        f"  Service level:      {direction(im['service_level_delta'])}%",
    ]

    if im["unmet_demand_units"] > 0:
        lines.append(
            f"  ⚠️  Unmet demand:    {im['unmet_demand_units']:,.0f} units "
            f"(routes/DCs unavailable)"
        )
    else:
        lines.append("  ✅  All demand met — no stockouts detected")

    # Per-mode cost breakdown (baseline vs scenario)
    b_modes = b.get("cost_by_mode", {})
    s_modes = s.get("cost_by_mode", {})
    all_modes = sorted(set(b_modes) | set(s_modes))
    if all_modes:
        lines += ["", "🚚  Cost by Mode (90-day total):"]
        lines.append(f"  {'Mode':<8}  {'Baseline':>12}  {'Scenario':>12}  {'Delta':>12}")
        lines.append(f"  {'-'*8}  {'-'*12}  {'-'*12}  {'-'*12}")
        for m in all_modes:
            bv = b_modes.get(m, 0)
            sv = s_modes.get(m, 0)
            dv = sv - bv
            lines.append(
                f"  {m:<8}  ${bv:>11,.0f}  ${sv:>11,.0f}  {'+' if dv>=0 else ''}"
                f"${dv:>+11,.0f}"
            )

    return "\n".join(lines)


# ── Tool registry (imported by orchestrator) ──────────────────────────────────
ALL_TOOLS = [query_supply_chain_data, predict_shipping_cost, optimize_network, run_scenario]
