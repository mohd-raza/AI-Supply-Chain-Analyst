"""
Digital Twin Simulation Engine for ChainMind.

Uses SimPy discrete-event simulation to model the Tesla inbound supply chain
over a configurable window (default 90 days). Runs a baseline simulation and
a modified "what-if" simulation, then reports the impact delta.

Scenario types
──────────────
  port_closure   target=supplier_id  value=disruption_days  (e.g. SUP-SH, 14)
  cost_increase  target=mode|sup_id  value=pct              (e.g. ocean, 20)
  demand_shock   target=dc_id        value=multiplier        (e.g. DC-FR, 2.0)
  dc_closure     target=dc_id        value=unused            (e.g. DC-ME, 1)
  mode_shift     target=src_mode     value=unused            (e.g. ocean, 1)
                 forces all shipments using src_mode → cheapest non-src alternative
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime
from pathlib import Path
import sys

import simpy

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import get_connection
from config import DB_PATH


# ── Metrics collector ─────────────────────────────────────────────────────────

class _Metrics:
    def __init__(self):
        self._rows: list[dict] = []
        self.unmet_units = 0.0

    def record(self, dc_id: str, route_id: str, mode: str, units: int,
               cost: float, transit: float, on_time: bool) -> None:
        self._rows.append(dict(
            dc_id=dc_id, route_id=route_id, mode=mode, units=units,
            cost=cost, transit=transit, on_time=int(on_time),
        ))

    def miss(self, units: float) -> None:
        self.unmet_units += units

    def summarize(self) -> dict:
        if not self._rows:
            return dict(
                total_cost=0.0, total_units=0, avg_transit_days=0.0,
                service_level_pct=0.0, shipment_count=0,
                unmet_demand=round(self.unmet_units),
                cost_by_mode={},
                units_by_mode={},
            )
        tc   = sum(r["cost"]    for r in self._rows)
        tu   = sum(r["units"]   for r in self._rows)
        at   = sum(r["transit"] for r in self._rows) / len(self._rows)
        sl   = sum(r["on_time"] for r in self._rows) / len(self._rows) * 100

        cost_by_mode:  dict[str, float] = {}
        units_by_mode: dict[str, int]   = {}
        for r in self._rows:
            m = r["mode"]
            cost_by_mode[m]  = round(cost_by_mode.get(m, 0.0)  + r["cost"],  2)
            units_by_mode[m] = units_by_mode.get(m, 0) + r["units"]

        return dict(
            total_cost        = round(tc, 2),
            total_units       = int(tu),
            avg_transit_days  = round(at, 2),
            service_level_pct = round(sl, 1),
            shipment_count    = len(self._rows),
            unmet_demand      = round(self.unmet_units),
            cost_by_mode      = {k: round(v, 2) for k, v in sorted(cost_by_mode.items())},
            units_by_mode     = dict(sorted(units_by_mode.items())),
        )


# ── Core simulation ───────────────────────────────────────────────────────────

def _simulate(
    routes:            list[dict],
    demand_per_dc:     dict[str, float],    # dc_id → daily units
    duration_days:     int,
    closed_routes:     set[str],             # route ids unavailable whole sim
    disrupted_routes:  dict[str, tuple[int, int]],  # id → (start_day, end_day)
    cost_multipliers:  dict[str, float],    # route_id or mode → multiplier
    demand_multipliers:dict[str, float],    # dc_id → multiplier
    forced_mode_map:   dict[str, str] | None,  # dc_id → mode to force
    seed: int = 42,
) -> dict:
    """Run the SimPy simulation and return aggregated metrics."""

    rng     = random.Random(seed)
    env     = simpy.Environment()
    metrics = _Metrics()

    def _available_routes(dc_id: str, day: float, forced_mode: str | None) -> list[dict]:
        """Return all routes to dc_id that are not closed/disrupted on this day."""
        candidates = [
            r for r in routes
            if r["destination_id"] == dc_id
            and r["id"] not in closed_routes
            and not (r["id"] in disrupted_routes
                     and disrupted_routes[r["id"]][0] <= day < disrupted_routes[r["id"]][1])
            and (forced_mode is None or r["mode"] == forced_mode)
        ]
        if not candidates and forced_mode:
            # Fallback: relax mode constraint if forced mode entirely unavailable
            candidates = [
                r for r in routes
                if r["destination_id"] == dc_id
                and r["id"] not in closed_routes
                and not (r["id"] in disrupted_routes
                         and disrupted_routes[r["id"]][0] <= day < disrupted_routes[r["id"]][1])
            ]
        return candidates

    def _allocate_demand(dc_id: str, daily: float, day: float) -> list[tuple[dict, int]]:
        """
        Split `daily` units across all available routes to dc_id, proportional to each
        route's capacity_units_per_day.  This models the reality that each supplier/route
        serves a distinct set of SKUs — they are not substitutable by price alone.
        Returns list of (route, units) pairs.
        """
        forced = forced_mode_map.get(dc_id) if forced_mode_map else None
        avail  = _available_routes(dc_id, day, forced)
        if not avail:
            return []

        total_cap = sum(r["capacity_units_per_day"] for r in avail)
        result: list[tuple[dict, int]] = []
        for r in avail:
            share = r["capacity_units_per_day"] / total_cap
            units = max(1, int(daily * share * rng.uniform(0.85, 1.15)))
            units = min(units, r["capacity_units_per_day"])   # cap at lane capacity
            result.append((r, units))
        return result

    def dc_process(env: simpy.Environment, dc_id: str, base_daily: float):
        while True:
            yield env.timeout(1)
            dm    = demand_multipliers.get(dc_id, 1.0)
            daily = base_daily * dm

            allocs = _allocate_demand(dc_id, daily, env.now)
            if not allocs:
                metrics.miss(daily)
                continue

            served = 0
            for route, units in allocs:
                # Cost multiplier: check route_id first, then mode
                cm = cost_multipliers.get(route["id"],
                     cost_multipliers.get(route["mode"], 1.0))

                congestion  = rng.uniform(0.90, 1.15)
                actual_cost = round(route["base_cost_per_unit"] * units * cm * congestion, 2)

                mode = route["mode"]
                if mode == "ocean":
                    jitter = rng.uniform(0.85, 1.40)
                elif mode == "air":
                    jitter = rng.uniform(0.90, 1.20)
                elif mode == "truck":
                    jitter = rng.uniform(0.80, 1.35)
                else:                               # rail
                    jitter = rng.uniform(0.88, 1.25)

                actual_transit = round(route["transit_days"] * jitter, 1)
                on_time        = actual_transit <= route["transit_days"] * 1.1

                metrics.record(dc_id, route["id"], route["mode"], units, actual_cost, actual_transit, on_time)
                served += units

            # Record any unmet demand from disrupted/closed lane shares
            unmet = max(0.0, daily - served)
            if unmet > 0:
                metrics.miss(unmet)

    for dc_id, daily in demand_per_dc.items():
        env.process(dc_process(env, dc_id, daily))

    env.run(until=duration_days)
    return metrics.summarize()


# ── Public API ────────────────────────────────────────────────────────────────

class SupplyChainDigitalTwin:
    """
    Wrapper that loads network data from SQLite and exposes run_scenario().
    Instantiate once (singleton in tools.py) for efficiency.
    """

    def __init__(self):
        conn          = get_connection()
        self.routes   = [dict(r) for r in conn.execute("SELECT * FROM routes").fetchall()]
        self.suppliers= {s["id"]: dict(s) for s in conn.execute("SELECT * FROM suppliers").fetchall()}
        self.dcs      = {d["id"]: dict(d) for d in conn.execute(
            "SELECT * FROM distribution_centers WHERE is_active=1"
        ).fetchall()}
        conn.close()

        # Default daily demand (~monthly / 30)
        self._default_demand: dict[str, float] = {
            "DC-FR": 167.0,   # ≈5 000/mo
            "DC-AU": 133.0,   # ≈4 000/mo
            "DC-LA": 100.0,   # ≈3 000/mo
            "DC-ME": 150.0,   # ≈4 500/mo
        }

    # ── scenario runner ───────────────────────────────────────────────────────

    def run_scenario(
        self,
        scenario_type:   str,
        scenario_target: str,
        scenario_value:  float,
        duration_days:   int  = 90,
    ) -> dict:
        """
        Run a what-if scenario and return a structured impact report.

        Returns
        -------
        dict with keys: scenario_type, target, value, duration_days,
                        baseline, scenario_result, impact
        """
        demand       = dict(self._default_demand)

        # ── shared scenario kwargs (all default to "no change") ───────────────
        closed_routes      : set[str]            = set()
        disrupted_routes   : dict[str, tuple]    = {}
        cost_multipliers   : dict[str, float]    = {}
        demand_multipliers : dict[str, float]    = {}
        forced_mode_map    : dict[str, str] | None = None

        scenario_type = scenario_type.strip().lower()

        if scenario_type == "port_closure":
            # Disrupt all routes from the named supplier for the first N days
            n_days = max(1, int(scenario_value))
            for r in self.routes:
                if r["origin_id"] == scenario_target:
                    disrupted_routes[r["id"]] = (0, min(n_days, duration_days))

        elif scenario_type == "cost_increase":
            pct = scenario_value / 100.0
            mult = 1.0 + pct
            valid_modes = {"truck", "rail", "ocean", "air"}
            if scenario_target.lower() in valid_modes:
                cost_multipliers[scenario_target.lower()] = mult
            else:
                # treat as supplier ID
                for r in self.routes:
                    if r["origin_id"] == scenario_target:
                        cost_multipliers[r["id"]] = mult

        elif scenario_type == "demand_shock":
            if scenario_target in self.dcs:
                demand_multipliers[scenario_target] = float(scenario_value)
            else:
                # Apply shock to ALL DCs
                demand_multipliers = {dc: float(scenario_value) for dc in demand}

        elif scenario_type == "dc_closure":
            closed_routes = {r["id"] for r in self.routes
                             if r["destination_id"] == scenario_target}
            demand.pop(scenario_target, None)

        elif scenario_type == "mode_shift":
            # Force shipments away from the named mode → cheapest alternative
            src_mode = scenario_target.lower()
            # Find which DCs rely primarily on src_mode
            for dc_id in list(demand.keys()):
                alternatives = [r for r in self.routes
                                if r["destination_id"] == dc_id
                                and r["mode"] != src_mode]
                if alternatives:
                    best_alt = min(alternatives, key=lambda r: r["base_cost_per_unit"])
                    if forced_mode_map is None:
                        forced_mode_map = {}
                    forced_mode_map[dc_id] = best_alt["mode"]

        else:
            return {"error": f"Unknown scenario_type '{scenario_type}'. "
                    "Valid: port_closure, cost_increase, demand_shock, dc_closure, mode_shift"}

        # ── baseline ──────────────────────────────────────────────────────────
        _shared = dict(
            routes            = self.routes,
            duration_days     = duration_days,
            seed              = 42,
        )
        baseline = _simulate(
            **_shared,
            demand_per_dc      = dict(self._default_demand),
            closed_routes      = set(),
            disrupted_routes   = {},
            cost_multipliers   = {},
            demand_multipliers = {},
            forced_mode_map    = None,
        )

        # ── scenario ──────────────────────────────────────────────────────────
        scenario_result = _simulate(
            **_shared,
            demand_per_dc      = demand,
            closed_routes      = closed_routes,
            disrupted_routes   = disrupted_routes,
            cost_multipliers   = cost_multipliers,
            demand_multipliers = demand_multipliers,
            forced_mode_map    = forced_mode_map,
        )

        # ── impact ────────────────────────────────────────────────────────────
        cost_delta   = scenario_result["total_cost"]   - baseline["total_cost"]
        trans_delta  = scenario_result["avg_transit_days"] - baseline["avg_transit_days"]
        sl_delta     = scenario_result["service_level_pct"] - baseline["service_level_pct"]
        cost_pct     = (cost_delta / baseline["total_cost"] * 100) if baseline["total_cost"] else 0

        return {
            "scenario_type"  : scenario_type,
            "target"         : scenario_target,
            "value"          : scenario_value,
            "duration_days"  : duration_days,
            "baseline"       : baseline,
            "scenario_result": scenario_result,
            "impact"         : {
                "cost_delta"         : round(cost_delta, 2),
                "cost_delta_pct"     : round(cost_pct, 1),
                "transit_delta_days" : round(trans_delta, 2),
                "service_level_delta": round(sl_delta, 1),
                "unmet_demand_units" : scenario_result.get("unmet_demand", 0),
            },
        }


    def save_to_db(self, result: dict) -> str:
        """Persist a scenario result to simulation_results table. Returns the new ID."""
        import json
        sim_id = str(uuid.uuid4())
        conn = get_connection()
        conn.execute(
            """INSERT INTO simulation_results
               (id, scenario_name, created_at, total_cost, avg_transit_days,
                service_level_pct, config_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                sim_id,
                f"{result['scenario_type']}:{result['target']}",
                datetime.utcnow().isoformat(),
                result["scenario_result"]["total_cost"],
                result["scenario_result"]["avg_transit_days"],
                result["scenario_result"]["service_level_pct"],
                json.dumps(result),
            ),
        )
        conn.commit()
        conn.close()
        return sim_id


# ── Module-level singleton ────────────────────────────────────────────────────

_twin: SupplyChainDigitalTwin | None = None

def get_twin() -> SupplyChainDigitalTwin:
    global _twin
    if _twin is None:
        _twin = SupplyChainDigitalTwin()
    return _twin
