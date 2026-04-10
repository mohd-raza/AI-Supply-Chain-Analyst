"""
Pydantic schemas for request/response validation across all routers.
"""
from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ── Network entities ──────────────────────────────────────────────────────────

class Supplier(BaseModel):
    id: str
    name: str
    city: str
    country: str
    lat: float
    lon: float
    capacity_units_per_day: int


class DistributionCenter(BaseModel):
    id: str
    name: str
    city: str
    state: str
    country: str
    lat: float
    lon: float
    capacity_units: int
    fixed_cost_monthly: float
    is_active: bool


class Route(BaseModel):
    id: str
    origin_id: str
    destination_id: str
    mode: Literal["truck", "rail", "ocean", "air"]
    distance_miles: float
    base_cost_per_unit: float
    transit_days: float
    capacity_units_per_day: int


class Shipment(BaseModel):
    id: str
    route_id: str
    shipment_date: str
    units: int
    actual_cost: float
    actual_transit_days: float
    on_time: bool
    congestion_factor: float
    season: int


class SimulationResult(BaseModel):
    id: str
    scenario_name: str
    created_at: str
    total_cost: float
    avg_transit_days: float
    service_level_pct: float
    config_json: str


# ── Network graph (for map rendering) ─────────────────────────────────────────

class NetworkNode(BaseModel):
    id: str
    name: str
    type: Literal["supplier", "dc"]
    city: str
    country: str
    lat: float
    lon: float
    capacity: int


class NetworkEdge(BaseModel):
    id: str
    source: str
    target: str
    mode: Literal["truck", "rail", "ocean", "air"]
    distance_miles: float
    base_cost_per_unit: float
    transit_days: float
    capacity_units_per_day: int
    flow_volume: Optional[float] = None


class NetworkGraph(BaseModel):
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]


# ── Dashboard ─────────────────────────────────────────────────────────────────

class KPICard(BaseModel):
    label: str
    value: str
    unit: str = ""
    delta: Optional[str] = None
    trend: Optional[Literal["up", "down", "flat"]] = None


class KPIDashboard(BaseModel):
    total_cost_quarter: float
    avg_transit_days: float
    service_level_pct: float
    network_utilization_pct: float
    cards: list[KPICard]


class CostBreakdownItem(BaseModel):
    category: str
    cost: float
    shipment_count: int
    avg_cost_per_unit: float


class CostBreakdown(BaseModel):
    by_mode: list[CostBreakdownItem]
    by_supplier: list[CostBreakdownItem]
    by_dc: list[CostBreakdownItem]


class TopRoute(BaseModel):
    route_id: str
    origin: str
    destination: str
    mode: str
    total_cost: float
    shipment_count: int
    avg_transit_days: float
    on_time_pct: float


class BottleneckAlert(BaseModel):
    entity_id: str
    entity_name: str
    entity_type: Literal["route", "dc", "supplier"]
    utilization_pct: float
    severity: Literal["low", "medium", "high", "critical"]
    message: str


# ── Chat / Agent ──────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)
    session_id: Optional[str] = None


class AgentEvent(BaseModel):
    type: Literal["thinking", "tool_call", "tool_result", "answer", "error"]
    agent: Optional[str] = None
    content: Optional[str] = None
    tool: Optional[str] = None
    input: Optional[dict[str, Any]] = None
    output: Optional[Any] = None


# ── Predictions ───────────────────────────────────────────────────────────────

class CostPredictRequest(BaseModel):
    origin_id: str
    destination_id: str
    mode: Literal["truck", "rail", "ocean", "air"]
    units: int = Field(..., ge=1, le=10_000)
    season: int = Field(..., ge=1, le=4)


class CostPredictResponse(BaseModel):
    predicted_cost: float
    predicted_cost_per_unit: float
    confidence_low: float
    confidence_high: float
    model_version: str = "xgboost-v1"


class TransitPredictRequest(BaseModel):
    origin_id: str
    destination_id: str
    mode: Literal["truck", "rail", "ocean", "air"]
    congestion_factor: float = Field(default=1.0, ge=0.5, le=2.0)


class TransitPredictResponse(BaseModel):
    predicted_transit_days: float
    confidence_low: float
    confidence_high: float


# ── Optimization ──────────────────────────────────────────────────────────────

class OptimizeRequest(BaseModel):
    demand: dict[str, float] = Field(
        description="DC id → monthly demand in units",
        example={"DC-FR": 5000, "DC-AU": 4000, "DC-LA": 3000, "DC-ME": 4500},
    )
    budget: float = Field(
        description="Maximum monthly budget in USD",
        example=500_000,
    )
    open_dcs: Optional[list[str]] = Field(
        default=None,
        description="Force-open these DCs (null = optimizer decides)",
    )


class RouteFlow(BaseModel):
    route_id: str
    origin: str
    destination: str
    mode: str
    flow_units: float
    cost: float


class OptimizeResponse(BaseModel):
    status: Literal["optimal", "infeasible", "timeout"]
    total_cost: float
    open_dcs: list[str]
    closed_dcs: list[str]
    route_flows: list[RouteFlow]
    dc_utilization: dict[str, float]
    solver_gap_pct: float
    solve_time_seconds: float


# ── Simulation ────────────────────────────────────────────────────────────────

class ScenarioModification(BaseModel):
    type: Literal[
        "close_dc", "open_dc", "increase_transit", "increase_cost",
        "demand_shock", "capacity_change", "route_disable"
    ]
    target_id: str
    value: Optional[float] = None
    description: str = ""


class SimulateRequest(BaseModel):
    scenario_name: str
    modifications: list[ScenarioModification]
    duration_days: int = Field(default=90, ge=7, le=365)
    baseline: bool = Field(default=True, description="Include baseline run for comparison")


class SimulateResponse(BaseModel):
    scenario_name: str
    baseline_cost: Optional[float]
    scenario_cost: float
    cost_delta_pct: Optional[float]
    baseline_transit: Optional[float]
    scenario_transit: float
    transit_delta_pct: Optional[float]
    service_level_pct: float
    bottlenecks: list[str]
    summary: str


# ── Health ─────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    version: str
    db_connected: bool
    models_loaded: bool
    config_warnings: list[str] = Field(default_factory=list)
