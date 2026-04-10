# ChainMind — Complete Project Brief for Presentation Generation

> **Purpose of this document:** This is an exhaustive technical brief of the ChainMind project — a full-stack AI-powered supply chain network optimizer built for a Tesla Machine Learning Engineer panel interview. Feed this entire document to an AI assistant and ask it to generate a PowerPoint presentation following the slide structure at the end.

---

## 1. THE PROBLEM BEING SOLVED

Tesla's inbound distribution network spans 5 global suppliers (China, Germany, Mexico, USA) shipping parts to 4 US distribution centers via truck, rail, ocean, and air freight. Today, supply chain managers face three critical gaps:

1. **No predictive cost visibility.** Freight cost is known only after shipment completes. There is no tool to predict cost *before* committing to a lane + mode. Decisions are reactive.

2. **Manual network design.** Choosing which DCs to keep open, how to allocate flow across 30 routes, and which modes to use is done in spreadsheets. No optimization solver backs these decisions.

3. **No disruption modeling.** When a port closes, freight rates spike, or demand doubles at a facility, there is no way to quickly quantify the impact. "What-if" analysis takes days, not seconds.

4. **Insights locked in data warehouses.** Engineers write SQL, analysts build Excel reports, managers wait. There is no natural language interface that lets a supply chain manager ask a question and get a model-backed, data-driven answer immediately.

**What ChainMind solves:** A single system where a user types a question in natural language, and a 3-agent AI system plans, executes (using ML models, LP solvers, and simulation), and synthesizes an executive-ready answer — all streamed in real-time through a modern web UI.

---

## 2. SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│                    REACT FRONTEND                           │
│   Chat Panel  ·  Dashboard  ·  Network Map                  │
│   (React 18 + Vite + Tailwind CSS + Recharts + Lucide)      │
└───────────────────────────┬─────────────────────────────────┘
                            │  REST API + SSE (Server-Sent Events)
                            │  POST /api/chat (streaming)
                            │  GET /api/dashboard/* · /api/network/*
┌───────────────────────────┴─────────────────────────────────┐
│                    FASTAPI BACKEND                           │
│   main.py  ·  config.py  ·  models.py (Pydantic)            │
│   routers: chat.py · dashboard.py · network.py · optimize.py│
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│          3-AGENT LANGGRAPH ORCHESTRATOR                      │
│                                                              │
│  Agent 1: PLANNER  ──→  Agent 2: ANALYST  ──→  Agent 3: REC │
│  (intent, entities,      (ReAct agent,          (synthesize  │
│   execution plan)         executes tools)        & recommend) │
│                                                              │
│  LLM: Azure OpenAI GPT-5.2 via langchain-openai             │
│  Agent: langgraph create_react_agent                         │
└───────────────────────────┬─────────────────────────────────┘
                            │  tool calls
┌───────────┬───────────────┼───────────────┬─────────────────┐
│  Tool 1   │    Tool 2     │    Tool 3     │     Tool 4      │
│  SQL      │    XGBoost    │    PuLP LP    │     SimPy       │
│  Query    │    Cost       │    Network    │     Digital      │
│  Engine   │    Predictor  │    Optimizer  │     Twin         │
└─────┬─────┴───────┬───────┴───────┬───────┴────────┬────────┘
      │             │               │                │
      └─────────────┴───────────────┴────────────────┘
                            │
                    SQLite Database
          5 suppliers · 4 DCs · 30 routes · 20,000 shipments
```

### Technology stack:
- **Backend:** FastAPI (Python 3.11+), uvicorn, Pydantic v2
- **LLM:** Azure OpenAI GPT-5.2 via `langchain-openai` `AzureChatOpenAI` with `reasoning_effort` parameter
- **Agent framework:** LangGraph `create_react_agent` (ReAct pattern)
- **ML:** XGBoost Regressor (cost prediction), Random Forest Regressor (transit time prediction), scikit-learn
- **Optimization:** PuLP (CBC solver) for Mixed Integer Linear Programming
- **Simulation:** SimPy discrete-event simulation
- **Database:** SQLite with WAL mode, Row factory
- **Frontend:** React 18, Vite 6, Tailwind CSS 4, Recharts, Lucide React icons
- **Streaming:** Server-Sent Events over POST endpoint (not GET/WebSocket) using `fetch()` + `ReadableStream`
- **Dev proxy:** Vite proxy rewrites `/api` → `localhost:8000` to avoid CORS in development

---

## 3. FILE STRUCTURE

```
chainmind/
├── .env                              # Azure OpenAI credentials
├── .cursorrules                      # Development instructions
├── PRD.md                            # Product requirements document
├── PRESENTATION_BRIEF.md             # This file
│
├── backend/
│   ├── main.py                       # FastAPI app, lifespan, CORS, routers, health check
│   ├── config.py                     # Load .env, Azure OpenAI settings, paths
│   ├── database.py                   # SQLite DDL, synthetic data seeding (20K shipments)
│   ├── models.py                     # 25+ Pydantic schemas for all request/response types
│   ├── requirements.txt              # 19 Python dependencies
│   │
│   ├── agent/
│   │   ├── orchestrator.py           # Original single-agent (deprecated, kept for reference)
│   │   ├── multi_orchestrator.py     # 3-Agent orchestrator (Planner→Analyst→Recommendation)
│   │   └── tools.py                  # 4 LangChain @tool functions + registry
│   │
│   ├── ml/
│   │   ├── train_models.py           # XGBoost + RandomForest training, feature engineering
│   │   ├── cost_model.pkl            # Persisted XGBoost cost model (auto-generated)
│   │   └── transit_model.pkl         # Persisted RandomForest transit model (auto-generated)
│   │
│   ├── simulation/
│   │   └── digital_twin.py           # SimPy simulation engine, 5 scenario types
│   │
│   ├── routers/
│   │   ├── chat.py                   # POST /api/chat → SSE stream
│   │   ├── dashboard.py              # GET /api/dashboard/kpis, cost-breakdown, top-routes, bottlenecks
│   │   ├── network.py                # GET /api/network, suppliers, dcs, routes
│   │   └── optimize.py               # POST /api/optimize/network (stub)
│   │
│   └── data/
│       └── chainmind.db              # SQLite database (auto-generated)
│
└── frontend/
    ├── package.json                  # React + Vite + Tailwind + Recharts + Lucide
    ├── vite.config.js                # Vite config with proxy + Tailwind plugin
    ├── index.html
    └── src/
        ├── main.jsx                  # React DOM entry
        ├── App.jsx                   # Root layout: Sidebar + Header + Views + Footer
        ├── api/
        │   └── client.js            # fetchStream() SSE client + REST helpers
        └── components/
            ├── ChatPanel.jsx         # AI chat with 3-agent reasoning panel
            ├── Dashboard.jsx         # KPI cards + cost charts + top routes table
            └── NetworkMap.jsx        # SVG schematic network diagram
```

---

## 4. THE DATA LAYER — database.py

### 4.1 Database Schema (5 tables)

```sql
CREATE TABLE suppliers (
    id                     TEXT PRIMARY KEY,   -- e.g. 'SUP-SH'
    name                   TEXT NOT NULL,
    city                   TEXT,
    country                TEXT,
    lat                    REAL,
    lon                    REAL,
    capacity_units_per_day INTEGER
);

CREATE TABLE distribution_centers (
    id                   TEXT PRIMARY KEY,   -- e.g. 'DC-FR'
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

CREATE TABLE routes (
    id                    TEXT PRIMARY KEY,   -- e.g. 'RT-001'
    origin_id             TEXT NOT NULL,      -- FK → suppliers.id
    destination_id        TEXT NOT NULL,      -- FK → distribution_centers.id
    mode                  TEXT CHECK(mode IN ('truck','rail','ocean','air')),
    distance_miles        REAL,
    base_cost_per_unit    REAL,
    transit_days          REAL,
    capacity_units_per_day INTEGER
);

CREATE TABLE shipments (
    id                   TEXT PRIMARY KEY,
    route_id             TEXT NOT NULL,       -- FK → routes.id
    shipment_date        TEXT NOT NULL,
    units                INTEGER,
    actual_cost          REAL,
    actual_transit_days  REAL,
    on_time              INTEGER,             -- boolean (0/1)
    congestion_factor    REAL,
    season               INTEGER              -- 1=Q1 … 4=Q4
);

CREATE TABLE simulation_results (
    id                 TEXT PRIMARY KEY,
    scenario_name      TEXT,
    created_at         TEXT,
    total_cost         REAL,
    avg_transit_days   REAL,
    service_level_pct  REAL,
    config_json        TEXT                   -- full JSON of scenario + results
);
```

### 4.2 Master Data — 5 Suppliers

| ID | Name | City | Country | Daily Capacity |
|----|------|------|---------|---------------|
| SUP-SH | Shanghai Electronics | Shanghai | China | 500 units/day |
| SUP-SZ | Shenzhen Components | Shenzhen | China | 400 units/day |
| SUP-MU | Munich Auto Parts | Munich | Germany | 300 units/day |
| SUP-MO | Monterrey Industrial | Monterrey | Mexico | 450 units/day |
| SUP-DE | Detroit Motors Supply | Detroit | USA | 350 units/day |

### 4.3 Master Data — 4 Distribution Centers

| ID | Name | City | State | Capacity | Fixed Cost/mo |
|----|------|------|-------|----------|--------------|
| DC-FR | Fremont DC | Fremont | CA | 2,000 units | $150,000 |
| DC-AU | Austin DC | Austin | TX | 1,800 units | $120,000 |
| DC-LA | Lathrop DC | Lathrop | CA | 1,500 units | $100,000 |
| DC-ME | Memphis Hub | Memphis | TN | 2,200 units | $130,000 |

### 4.4 Routes — 30 Lanes

30 routes connecting each supplier to 2–6 DCs across 4 transport modes. Key examples:

- **Transoceanic (China→US):** RT-001: SUP-SH → DC-FR ocean, 7,450 mi, $44/unit, 22 days, 200 cap/day
- **Transoceanic air:** RT-002: SUP-SH → DC-FR air, 7,450 mi, $78/unit, 3 days, 80 cap/day
- **Nearshore truck:** RT-013: SUP-MO → DC-AU truck, 890 mi, $11/unit, 2 days, 320 cap/day
- **Nearshore rail:** RT-014: SUP-MO → DC-AU rail, 890 mi, $7.5/unit, 4 days, 420 cap/day
- **Domestic rail:** RT-030: SUP-DE → DC-FR rail, 2,380 mi, $19.5/unit, 7 days, 280 cap/day

Cost logic: ocean cheapest long-distance ($4-6/unit/1000mi), truck cheapest short-distance ($6-12/unit/1000mi), rail middle ($4-8/unit/1000mi), air most expensive ($8-15/unit/1000mi).

### 4.5 Shipment Generation — 20,000 Records

Generated on app startup with `random.seed(42)` for reproducibility:

- **Date range:** 2023-01-01 to 2024-12-31 (2 years)
- **Route selection:** Weighted by `capacity_units_per_day` (higher-capacity routes get proportionally more shipments)
- **Units per shipment:** Air: 10–80, Ocean: 40–200, Truck/Rail: 20–150
- **Cost formula:** `actual_cost = base_cost_per_unit × units × seasonal_multiplier × congestion_factor × jitter(0.90, 1.15)`
- **Seasonal multiplier:** Nov–Dec: 1.10–1.25 (Q4 holiday surge), Jan–Feb: 0.88–0.96 (post-holiday dip), Jul–Sep: 1.02–1.12 (moderate), other: 0.95–1.08
- **Congestion factor:** Truck: 0.85–1.35 (most variable), Ocean: 0.90–1.20, Rail: 0.90–1.15, Air: 0.95–1.10
- **Transit formula:** `actual_transit = transit_days × mode_jitter` where ocean jitter is 0.85–1.40, truck 0.80–1.35, rail 0.88–1.25, air 0.90–1.20
- **On-time definition:** `actual_transit <= transit_days × 1.1` (10% grace window)

---

## 5. ML MODELS — train_models.py

### 5.1 Feature Engineering (11 features)

| # | Feature | Type | Source | Why it matters |
|---|---------|------|--------|---------------|
| 1 | `distance_miles` | continuous | routes table | Primary cost driver |
| 2 | `units` | continuous | shipments table | Volume discount effect |
| 3 | `mode_truck` | binary (one-hot) | routes.mode | Modes have completely different cost curves |
| 4 | `mode_rail` | binary (one-hot) | routes.mode | |
| 5 | `mode_ocean` | binary (one-hot) | routes.mode | |
| 6 | `mode_air` | binary (one-hot) | routes.mode | |
| 7 | `country_enc` | label encoded | suppliers.country | China=0, Germany=1, Mexico=2, USA=3 — proxy for import complexity |
| 8 | `season` | ordinal 1–4 | shipments.season | Q4 premium captured |
| 9 | `congestion_factor` | continuous | shipments.congestion_factor | Random 0.8–1.3, captures port/road congestion |
| 10 | `base_cost_per_unit` | continuous | routes table | Lane-level anchor price |
| 11 | `base_transit_days` | continuous | routes table | Transit ↔ cost tradeoff signal |

The feature order is defined once in `FEATURE_COLS` in `train_models.py` and imported by `tools.py` via `build_inference_row()` — single source of truth to prevent train/serve skew.

### 5.2 Model 1: XGBoost Cost Predictor

- **Target:** `actual_cost`
- **Algorithm:** XGBoost Regressor (falls back to RandomForest if XGBoost is unavailable — handles macOS libomp dependency)
- **Hyperparameters:** `n_estimators=400, max_depth=6, learning_rate=0.04, subsample=0.8, colsample_bytree=0.8, min_child_weight=3, gamma=0.1, reg_alpha=0.05`
- **Train/test split:** 80/20, `random_state=42`
- **Saved to:** `backend/ml/cost_model.pkl` via joblib
- **Evaluation metrics printed at startup:** MAE, MAPE (%), R²

### 5.3 Model 2: Random Forest Transit Estimator

- **Target:** `actual_transit_days`
- **Algorithm:** RandomForest Regressor
- **Hyperparameters:** `n_estimators=200, max_depth=8, min_samples_leaf=5`
- **Same feature set and split as cost model
- **Saved to:** `backend/ml/transit_model.pkl` via joblib

### 5.4 Training Trigger

`ensure_models_trained()` is called from `main.py` on startup. It checks if `.pkl` files exist; if not, loads training data from SQLite, builds features, trains both models, evaluates, and saves. Fully idempotent — safe to call on every restart.

### 5.5 Inference Pipeline

At prediction time (`predict_shipping_cost` tool):
1. Look up route from DB using `origin_id`, `destination_id`, `mode`
2. Call `build_inference_row()` — constructs a single-row DataFrame with 11 features in exact `FEATURE_COLS` order
3. `model.predict(X)` → predicted total cost
4. Calculate: cost per unit, 90% confidence interval (±12% based on residual spread)
5. Look up historical average from `shipments` table for the same lane
6. Return formatted comparison: predicted vs historical, with delta % and on-time rate

---

## 6. NETWORK OPTIMIZER — PuLP LP (Tool 3 in tools.py)

### 6.1 Mathematical Formulation

```
Minimize:
  Σ (base_cost_per_unit_ij × flow_ij)  +  Σ (fixed_cost_j × open_j)

Subject to:
  Demand satisfaction:   Σ_i flow_ij  >=  demand_j           ∀ DC j
  Route capacity:        flow_ij       <=  cap_ij × 30        per lane (monthly)
  DC capacity:           Σ_i flow_ij  <=  capacity_j × 30 × open_j  per DC
  Supplier capacity:     Σ_j flow_ij  <=  sup_cap_i × 30     per supplier
  Budget:                total_obj     <=  monthly_budget
  Non-negativity:        flow_ij       >=  0
  Binary:                open_j        ∈  {0, 1}
```

### 6.2 Decision Variables

- **flow_ij** (continuous): Units/month flowing on route i → DC j. Bounded [0, route monthly capacity].
- **open_j** (binary): Whether DC j is open (1) or closed (0). Each open DC incurs its `fixed_cost_monthly`.

### 6.3 Solver

- PuLP CBC (open-source, bundled with PuLP, no external dependency)
- `timeLimit=30` seconds, silent mode
- Same LP formulation portable to CPLEX/Gurobi by changing one solver line

### 6.4 Output Report Format

```
━━ Network Optimization Report ━━
  Status:         OPTIMAL  (solved in 0.068s)
  Total cost:     $688,250/month
  Variable cost:  $188,250/month  (shipping)
  Fixed DC cost:  $500,000/month
  Budget used:    57.4% of $1,200,000

📦  DC Configuration:
  ✅ OPEN   Fremont DC          inflow=5,000 units  util=8.3%  fixed=$150,000/mo
  ✅ OPEN   Austin DC           inflow=4,000 units  util=7.4%  fixed=$120,000/mo
  ❌ CLOSED Memphis Hub

🚛  Optimal Route Flows (active lanes):
  Detroit Motors Supply  → Fremont DC     [rail ]  5,000 units  $97,500
  Monterrey Industrial   → Austin DC      [rail ]  4,000 units  $30,000
```

---

## 7. DIGITAL TWIN — SimPy Simulation Engine (simulation/digital_twin.py)

### 7.1 Architecture

SimPy discrete-event simulation. Each DC runs an independent `dc_process` coroutine that fires once per day:

1. Calculate daily demand (base × demand_multiplier)
2. Find all available routes to this DC (not closed, not disrupted on this day)
3. **Allocate demand proportionally across routes by capacity** — each route's share = `capacity_units_per_day / total_available_capacity`. This models reality: each supplier/route serves distinct SKUs; they are not price-substitutable.
4. For each route allocation: apply cost multiplier (route-specific → mode-level fallback), apply congestion jitter, calculate actual cost and transit time
5. Record metrics; track unmet demand if no routes available

### 7.2 Five Scenario Types

| Scenario | Target | Value | What it does |
|----------|--------|-------|-------------|
| `port_closure` | supplier ID (e.g. SUP-SH) | disruption days (e.g. 14) | All routes from that supplier are unavailable for [0, N) days. Their capacity share becomes unmet demand. |
| `cost_increase` | mode name OR supplier ID | % increase (e.g. 20) | Multiplies cost by (1 + pct/100) for all routes of that mode or from that supplier |
| `demand_shock` | DC ID (e.g. DC-FR) or "all" | multiplier (e.g. 2.0) | Daily demand at that DC multiplied by the value |
| `dc_closure` | DC ID (e.g. DC-ME) | 1 (ignored) | All routes to that DC closed; DC removed from demand map entirely |
| `mode_shift` | source mode (e.g. ocean) | 1 (ignored) | Forces each DC to use its cheapest non-source-mode alternative |

### 7.3 Baseline vs Scenario

Every `run_scenario()` call runs TWO simulations with the same RNG seed (42):
1. **Baseline:** No modifications, same default demand
2. **Scenario:** With the specified disruption/change applied

Then calculates deltas: cost_delta, cost_delta_pct, transit_delta_days, service_level_delta, unmet_demand_units.

### 7.4 Metrics Tracked

- Total cost (90 days)
- Total units shipped
- Average transit days
- Service level % (on-time shipment rate)
- Unmet demand units
- **Cost breakdown by mode** (ocean/truck/rail/air totals, baseline vs scenario)
- **Units breakdown by mode**

### 7.5 Persistence

Each simulation result is saved to the `simulation_results` table with a UUID, scenario name (`type:target`), timestamp, and full JSON config. This enables historical scenario comparison queries via the SQL tool.

### 7.6 Singleton Pattern

`get_twin()` at module level caches a single `SupplyChainDigitalTwin` instance. The instance loads routes/suppliers/DCs from SQLite once at creation. The `_simulate()` function runs fresh each call with new `simpy.Environment`.

---

## 8. THE 3-AGENT LANGGRAPH ARCHITECTURE (multi_orchestrator.py)

### 8.1 Why 3 Agents, Not 1?

The original single ReAct agent had three problems:
1. **Redundant tool calls:** It would call `optimize_network` twice (constrained + unconstrained) for a single question
2. **Mixing reasoning with execution:** Planning and acting happened simultaneously, leading to unfocused reasoning
3. **No structured output:** Answers were raw tool dumps, not executive-ready summaries

The 3-agent design gives each agent a single responsibility:

### 8.2 Agent 1 — Planner (no tools)

- **LLM call:** `llm.ainvoke()` (single complete response, NOT streamed token-by-token)
- **System prompt defines:** Intent classification (cost_query | optimization | comparison | factual_lookup | trend_analysis | what_if), entity detection (suppliers, DCs, modes, time range, volume, budget), analysis tasks (max 3), tool assignments
- **Hard limits enforced in prompt:**
  - `optimize_network`: EXACTLY ONE call per response
  - `run_scenario`: EXACTLY ONE call per response
  - `predict_shipping_cost`: at most TWO calls
  - `query_supply_chain_data`: at most TWO SQL calls
  - Maximum 3 tasks total

**Output format:**
```
INTENT: what_if

ENTITIES DETECTED:
  Suppliers : SUP-SH
  DCs       : all
  Modes     : all
  Time range: last quarter

ANALYSIS TASKS:
  1. Pull baseline inbound KPIs from last quarter for SUP-SH
  2. Run digital-twin port_closure scenario: SUP-SH, 14 days

TOOL ASSIGNMENTS:
  Task 1 → query_supply_chain_data
  Task 2 → run_scenario
```

### 8.3 Agent 2 — Analyst (4 tools, ReAct agent)

- **Implementation:** `langgraph.prebuilt.create_react_agent` with all 4 tools
- **Streaming:** `agent.astream(stream_mode="updates")` with `recursion_limit=12`
- **System prompt instructs:** Execute ALL tasks in the plan, STOP when complete, fix errors and retry once, never add extra queries
- **SSE events emitted:** `tool_call` (with tool name, inputs, unique `id`) and `tool_result` (with output, paired by `tool_call_id`)
- **Schema awareness:** Full database schema with exact column names provided in the system prompt to prevent SQL errors

### 8.4 Agent 3 — Recommendation (no tools)

- **LLM call:** `llm.ainvoke()` (single complete response)
- **Input:** User's original question + Analyst's collected tool outputs
- **Output structure enforced by prompt:**
  1. Opening sentence — key answer/insight, bold the most important number
  2. Supporting data — markdown table if comparing ≥2 options, bullet points otherwise
  3. Recommendation — one specific, actionable decision
- **Style rules:** USD with commas ($1,234,567), transit time to 1 decimal (22.0 days), never repeat raw tool output verbatim

### 8.5 SSE Event Flow

```
{"type": "agent_start",  "agent": "planner",        "label": "Planner Agent — Decomposing your request"}
{"type": "thinking",     "content": "INTENT: cost_query\n..."}        ← full plan as one block
{"type": "agent_start",  "agent": "analyst",         "label": "Analyst Agent — Running analysis"}
{"type": "tool_call",    "tool": "query_supply_chain_data", "input": {...}, "id": "call_abc123"}
{"type": "tool_result",  "tool": "query_supply_chain_data", "output": "...", "tool_call_id": "call_abc123"}
{"type": "tool_call",    "tool": "predict_shipping_cost",   "input": {...}, "id": "call_def456"}
{"type": "tool_result",  "tool": "predict_shipping_cost",   "output": "...", "tool_call_id": "call_def456"}
{"type": "agent_start",  "agent": "recommendation",  "label": "Recommendation Agent — Synthesizing insights"}
{"type": "answer",       "content": "**$4,500** is the predicted cost..."}
```

### 8.6 LLM Configuration

```python
AzureChatOpenAI(
    azure_endpoint    = "https://drewh-mecx78y4-eastus2.cognitiveservices.azure.com",
    azure_deployment  = "gpt-5.2",
    api_version       = "2025-04-01-preview",
    streaming         = True,
    temperature       = 1,             # required for o-series reasoning models
    reasoning_effort  = "medium",      # configurable via .env
)
```

---

## 9. THE 4 TOOLS (agent/tools.py)

### 9.1 Tool 1: `query_supply_chain_data(query: str)`

- Executes read-only SQL SELECT (also allows WITH/CTE queries) against SQLite
- Validation: blocks INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/MERGE via regex
- Blocks multi-statement queries (`;` check)
- Max 50 rows returned, pipe-delimited text table format
- Detailed docstring teaches the LLM the full schema, join relationships, and example queries

### 9.2 Tool 2: `predict_shipping_cost(origin_id, destination_id, mode, units, season)`

- Input validation: valid supplier/DC IDs, mode ∈ {truck, rail, ocean, air}, season 1–4, units ≥ 1
- Looks up route from DB; if no route exists, suggests available modes for that lane
- Builds 11-feature inference row via `build_inference_row()` (imported from `train_models.py`)
- Loads XGBoost model (cached singleton), calls `model.predict(X)`
- Returns: predicted total cost, cost/unit, 90% CI (±12%), historical comparison with sample size and delta %, on-time rate

### 9.3 Tool 3: `optimize_network(monthly_budget, demand_per_dc)`

- `demand_per_dc`: JSON string → dict of DC ID → monthly units
- Loads all routes, DCs, suppliers from DB
- Builds PuLP LP: flow variables (continuous, bounded by route capacity × 30), open_dc variables (binary)
- Objective: minimize variable shipping cost + fixed DC cost
- Constraints: demand satisfaction, route capacity, DC capacity (linked to open_j), supplier capacity, budget
- Solver: CBC with 30s timeout
- Output: OPTIMAL/INFEASIBLE status, solve time, open/closed DCs with inflow and utilization, active route flows sorted by cost, budget utilization, avg cost/unit

### 9.4 Tool 4: `run_scenario(scenario_type, scenario_target, scenario_value, duration_days=90)`

- Calls `SupplyChainDigitalTwin.run_scenario()`
- Returns formatted report: baseline vs scenario table (cost, transit, service level, units), impact summary with % deltas, per-mode cost breakdown table
- Persists result to `simulation_results` table
- The `ALL_TOOLS` registry: `[query_supply_chain_data, predict_shipping_cost, optimize_network, run_scenario]`

---

## 10. FASTAPI BACKEND (main.py + routers/)

### 10.1 Startup Sequence (Lifespan)

1. Validate Azure OpenAI config (warns if API key missing)
2. `init_db()` — create SQLite tables + seed 20K shipments (idempotent)
3. `ensure_models_trained()` — train XGBoost + RandomForest if `.pkl` files don't exist
4. Mount routers

### 10.2 API Endpoints

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| POST | `/api/chat` | `chat.py` | SSE streaming of 3-agent orchestrator response |
| GET | `/api/dashboard/kpis` | `dashboard.py` | 4 KPI cards (cost, transit, service level, utilization) for last 90 days |
| GET | `/api/dashboard/cost-breakdown` | `dashboard.py` | Cost aggregated by mode, by supplier, by DC |
| GET | `/api/dashboard/top-routes` | `dashboard.py` | Top N routes by total cost (includes on-time %) |
| GET | `/api/dashboard/bottlenecks` | `dashboard.py` | Routes with >60% utilization, severity-ranked |
| GET | `/api/network` | `network.py` | Full network graph (nodes + edges with flow volumes) |
| GET | `/api/network/suppliers` | `network.py` | All 5 suppliers |
| GET | `/api/network/dcs` | `network.py` | All 4 DCs |
| GET | `/api/network/routes` | `network.py` | All 30 routes |
| POST | `/api/optimize/network` | `optimize.py` | Direct optimization endpoint (stub) |
| GET | `/health` | `main.py` | Health check: DB status, model status, config warnings |
| GET | `/` | `main.py` | Root: app name, version, docs link |

### 10.3 CORS Configuration

```python
allow_origins = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]
allow_credentials = True
allow_methods = ["*"]
allow_headers = ["*"]
```

### 10.4 SSE Chat Endpoint (chat.py)

```python
@router.post("/chat")
async def chat(request: ChatRequest):
    async def event_stream():
        from agent.multi_orchestrator import stream_multi_agent
        async for event in stream_multi_agent(request.message, request.history):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

Uses POST (not GET) because messages can be long. Frontend uses `fetch()` + `ReadableStream` (not `EventSource`, which only supports GET).

---

## 11. REACT FRONTEND

### 11.1 App Layout (App.jsx)

- **Root:** Full-screen dark theme (`#080808` background)
- **Backend health banner:** Red alert bar when backend is offline, with retry button. Health polled every 30s.
- **Sidebar:** 64px wide, 3 navigation icons (Chat, Dashboard, Network), backend status dot (green/amber/red)
- **Header:** "CHAINMIND" in Tesla red + view title
- **Content area:** All 3 views stay mounted via `display: none` (preserves chat history and scroll position across tab switches)
- **Footer:** "Powered by Azure OpenAI gpt-5.2 · 3-Agent LangGraph · XGBoost · PuLP LP"

### 11.2 ChatPanel.jsx — The Demo Centerpiece

**Core features:**
- Message input with auto-resize textarea
- 5 clickable suggestion queries pre-loaded
- Real-time SSE consumption via `fetchStream()` async generator
- Per-message conversation state with timestamps

**SSE Event Rendering:**
- `agent_start` → Colored horizontal divider with agent icon and label (Planner=purple 🎯, Analyst=blue 🔬, Recommendation=green 💡)
- `thinking` → Planner's structured plan rendered in `<pre>` with `white-space: pre-wrap` to preserve indentation. Lines ending with `→ n/a` are filtered out. Triple-blank-lines collapsed.
- `tool_call` → Collapsible card with tool-specific styling:
  - SQL Query: blue, Database icon
  - Cost Predictor: purple, BarChart3 icon
  - Network Optimizer: green, Network icon
  - Digital Twin: orange, FlaskConical icon
  - Shows input parameters; status indicator (running → done)
- `tool_result` → Expandable output under its matching tool_call card, paired by `tool_call_id` for exact matching
- `answer` → Inline markdown renderer that handles:
  - `### headers` → styled section headings
  - `| table |` → HTML table with dark styling
  - `**bold**` → font-weight: 700
  - `$1,234` → green highlight
  - `truck`/`rail`/`ocean`/`air` → colored mode pills (case-insensitive regex)
  - `**ocean**` → colored pill (not plain bold)
  - `` `code` `` → monospace with purple tint

**Agent Reasoning Panel:**
- Collapsible per-message panel showing all reasoning steps
- Header shows "3-Agent Reasoning" with active agent badges
- Agent dividers with icons and colors
- Tool call/result cards with expandable inputs/outputs
- Step counter

### 11.3 Dashboard.jsx

**Row 1 — 4 KPI Cards:**
- Total Inbound Cost (DollarSign icon, formatted as $X,XXX,XXX)
- Avg Transit Time (Clock icon, X.X days)
- Service Level (ShieldCheck icon, XX.X% on-time)
- Network Utilization (Activity icon, XX.X% capacity)
- Each card has trend indicator (up/down/flat arrow)

**Row 2 — Charts:**
- Cost by Mode: Recharts vertical BarChart, bars colored by mode (ocean=blue, truck=amber, rail=green, air=purple), dark theme
- Cost by Supplier: Horizontal BarChart, 5 bars

**Row 3 — Top Routes Table:**
- 7 columns: Origin, Destination, Mode, Total Cost, Shipments, Avg Transit, On-Time %
- Sorted by total cost descending
- Mode filter dropdown
- Hover row highlighting

**Data source:** `/api/dashboard/kpis`, `/api/dashboard/cost-breakdown`, `/api/dashboard/top-routes`

### 11.4 NetworkMap.jsx

- SVG schematic diagram (not a real map projection)
- **Supplier nodes:** Blue circles positioned by region (Asia left, Europe center-left, Mexico center, Detroit center-right)
- **DC nodes:** Green circles positioned roughly by US geography
- **Route lines:** Bezier curves connecting suppliers to DCs
  - Thickness proportional to flow volume
  - Color by mode: ocean=blue (dashed), truck=amber (solid), rail=green (dotted), air=purple (dash-dot)
- Hover tooltips showing route details (ID, mode, cost, transit, capacity)
- Click node → detail panel with supplier/DC info
- Region zone labels and dotted backgrounds
- Legend showing mode color/dash patterns

**Data source:** `/api/network` (nodes + edges with `flow_volume` from last 90 days of shipments)

### 11.5 API Client (client.js)

- `fetchStream(message, history)` — async generator that POSTs to `/api/chat`, reads SSE stream via `ReadableStream`, yields parsed event objects, handles `[DONE]` sentinel
- REST helpers: `getKPIs()`, `getCostBreakdown()`, `getTopRoutes(limit)`, `getBottlenecks()`, `getNetwork()`, `getSuppliers()`, `getDCs()`, `getRoutes()`, `healthCheck()`
- Error handling: catches fetch errors with friendly "Backend unreachable" messages

### 11.6 Design System

- **Theme:** Tesla-inspired dark — `#080808` (background), `#0d0d0d` (sidebar/header), `#e82127` (Tesla red accent), `#f5f5f5` (white text)
- **Borders:** `#2a2a2a`
- **Dim text:** `#6b7280`
- **Mode colors:** ocean=#3b82f6, truck=#f59e0b, rail=#10b981, air=#8b5cf6
- **Icons:** Lucide React (lightweight, consistent)
- **Charts:** Recharts with custom dark theme tooltips

---

## 12. PYDANTIC SCHEMAS (models.py)

25+ schemas covering every data entity and API contract:

- **Network entities:** Supplier, DistributionCenter, Route, Shipment, SimulationResult
- **Network graph:** NetworkNode, NetworkEdge, NetworkGraph
- **Dashboard:** KPICard, KPIDashboard, CostBreakdownItem, CostBreakdown, TopRoute, BottleneckAlert
- **Chat:** ChatMessage (role + content), ChatRequest (message + history + session_id), AgentEvent (type + agent + content + tool + input + output)
- **Predictions:** CostPredictRequest/Response, TransitPredictRequest/Response
- **Optimization:** OptimizeRequest (demand + budget + open_dcs), RouteFlow, OptimizeResponse (status + total_cost + open_dcs + route_flows + dc_utilization + solve_time)
- **Simulation:** ScenarioModification, SimulateRequest, SimulateResponse
- **Health:** HealthResponse (status + version + db_connected + models_loaded + config_warnings)

---

## 13. PYTHON DEPENDENCIES (requirements.txt)

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
python-dotenv==1.0.1
langchain>=0.3.13
langchain-openai>=0.2.14
langgraph>=0.2.62
pydantic>=2.10.0
sqlalchemy>=2.0.36
aiosqlite>=0.20.0
scikit-learn>=1.6.1
xgboost>=2.1.3
pandas>=2.2.3
numpy>=1.26.4,<2.0.0
simpy>=4.1.1
pulp>=2.9.0
joblib>=1.4.2
httpx>=0.28.1
sse-starlette>=2.2.1
python-multipart>=0.0.20
```

## 14. FRONTEND DEPENDENCIES (package.json)

```json
{
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "recharts": "^2.15.0",
    "lucide-react": "^0.474.0"
  },
  "devDependencies": {
    "vite": "^6.0.11",
    "@vitejs/plugin-react": "^4.3.4",
    "tailwindcss": "^4.0.0",
    "@tailwindcss/vite": "^4.0.0"
  }
}
```

---

## 15. HOW TO RUN

```bash
# Terminal 1 — Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

On first startup:
1. SQLite database created at `backend/data/chainmind.db`
2. 5 suppliers + 4 DCs + 30 routes + 20,000 shipments seeded
3. XGBoost cost model + RandomForest transit model trained and saved to `.pkl` files
4. All subsequent starts skip seeding and training (idempotent)

---

## 16. DEMO QUERIES THAT WORK END-TO-END

### SQL-backed queries:
1. "What is our total inbound shipping cost this quarter?"
2. "Which routes have the worst on-time delivery rates?"
3. "Rank all 5 suppliers by average cost per unit over the last 6 months"

### ML prediction queries:
4. "What's the cheapest way to ship 100 units from Shanghai to Fremont?"
5. "Compare shipping costs: truck vs ocean from Shenzhen to Austin"
6. "Compare shipping costs for 200 units from Munich to Memphis: truck vs rail vs air"

### Network optimization queries:
7. "Optimize our network to minimize total cost with a $500K monthly budget"
8. "Optimize our network with a $1.2M budget and demand DC-FR=5000, DC-AU=4000, DC-LA=3000, DC-ME=4500"

### Digital Twin what-if queries:
9. "What if the Shanghai port closes for 2 weeks?"
10. "What happens if ocean freight costs increase 20%?"
11. "Simulate closing the Memphis DC entirely"
12. "What if demand at the Fremont DC suddenly doubles?"
13. "What if a port strike forces us to shift all ocean freight to truck or air?"

---

## 17. KEY TECHNICAL DECISIONS AND RATIONALE

| Decision | Why |
|----------|-----|
| SQLite not Postgres | Zero setup for demo. Swap connection string for prod — no code changes. |
| XGBoost not neural net | Tabular data, 11 features, 20K rows. XGBoost dominates tabular at this scale. Interpretable feature importance. |
| PuLP not commercial solver | Open-source, deployable anywhere. Same LP formulation runs on CPLEX/Gurobi by changing one line. |
| 3 agents not 1 | Single agent loops, makes redundant tool calls, mixes planning with execution. Separation of concerns gives each agent one job. |
| SimPy for Digital Twin | Discrete-event abstraction is the right model. Each DC is an independent process. Deterministic seeding enables reproducible baseline vs scenario comparison. |
| Capacity-proportional allocation (not cheapest-route) in Digital Twin | Routes serve different SKUs — Shanghai provides electronics, Detroit provides motors. They are not price-substitutable. Allocating by capacity weight models reality. |
| POST for SSE (not GET/EventSource) | Messages can be long. EventSource only supports GET with query params. POST with fetch + ReadableStream handles any message length. |
| All views stay mounted (display:none) | Preserves chat history, scroll position, and loaded dashboard data across tab switches. |
| `ainvoke` for Planner and Recommendation, `astream` for Analyst | Planner and Recommendation produce complete text responses — streaming them token-by-token fragments the UI. Analyst needs real-time tool call/result events. |
| Tool call ID pairing on frontend | When multiple calls to the same tool run in parallel, results can arrive out of order. `tool_call_id` ensures each result is displayed under the correct card. |

---

## 18. MAPPING TO TESLA JD (Machine Learning Engineer, Supply Chain)

| JD Requirement | What Was Built |
|---------------|---------------|
| "Build and productionize ML models & AI agents that power inbound network design, including cost, transit-time prediction, mode/route selection" | XGBoost cost predictor + RF transit estimator with 11-feature engineering pipeline; 3-agent LangGraph system with 4 specialized tools |
| "Design and extend our Digital Twin, integrating inbound network constraints" | SimPy discrete-event Digital Twin with capacity-weighted proportional allocation across all lanes, 5 scenario types |
| "Build and run large-scale what-if simulations to evaluate new inbound strategies" | `run_scenario` tool: port_closure, cost_increase, demand_shock, dc_closure, mode_shift — each runs baseline vs scenario with per-mode cost breakdown |
| "Perform sensitivity and stress testing on existing inbound network designs" | LP optimizer tests budget sensitivity; Digital Twin stress-tests disruptions, demand shocks, mode shifts |
| "Own the ML lifecycle: data pipelines, feature engineering, model evaluation, monitoring" | `train_models.py`: data loading → feature engineering → train/test split → model training → MAE/MAPE/R² evaluation → joblib persistence → auto-retrain on startup |
| "Collaborate with Material Planning, Logistics, Finance, Warehouse Operations" | Natural language chat interface enables self-serve analysis for non-technical users |
| "Build decision-support tools, APIs, and UIs" | FastAPI REST + SSE backend, React dark-themed dashboard with KPIs/charts/tables, SVG network map, real-time chat panel |
| "Translate complex quantitative results into clear narratives and visualizations" | Recommendation Agent: executive-ready synthesis with bold key numbers, markdown tables, one actionable recommendation per query |
| "Strong programming skills in SQL, Python, scikit-learn" | Full-stack Python backend, custom SQL validation engine, scikit-learn/XGBoost ML pipeline |
| "Hands-on experience with React, RESTful API design" | React 18 + Vite + Tailwind frontend, fully documented REST API with Pydantic schemas, SSE streaming |
| "Experience leveraging LLMs, Generative AI" | Azure OpenAI GPT-5.2 with reasoning_effort, LangGraph multi-agent orchestration, structured prompt engineering |

---

## 19. SLIDE STRUCTURE FOR PRESENTATION GENERATION

Generate a PowerPoint presentation with the following slides. Total time: 25 minutes presentation + 5 minutes Q&A.

### Slide 1 — Title (30 sec)
- Title: "ChainMind: An AI-Powered Supply Chain Network Optimizer"
- Subtitle: "End-to-End ML System — Cost Prediction · Network Optimization · Digital Twin Simulation"
- Name, date

### Slide 2 — About Me (1.5 min)
- Background, education, relevant experience
- One sentence: built this to demonstrate what I'd bring to Tesla's Supply Chain Optimization team

### Slide 3 — The Problem (2 min)
- Frame: Tesla's inbound distribution network has no unified system for predictive cost visibility, automated network design, disruption modeling, or natural language analytics
- 4 specific problems listed in Section 1 above
- Why it matters: cost visibility drives mode/route decisions, disruption response needs sub-hour analysis

### Slide 4 — System Architecture (2 min)
- Full architecture diagram from Section 2
- Call out: FastAPI, LangGraph `create_react_agent`, Azure OpenAI GPT-5.2, SSE streaming, SQLite
- Show the 4-tool layer: SQL + XGBoost + PuLP + SimPy

### Slide 5 — The Data Layer (1.5 min)
- 5 tables, 5 suppliers, 4 DCs, 30 routes, 20K shipments
- Explain synthetic data generation: seasonal multipliers, congestion factors, mode-specific jitter distributions
- Key stat: 2 years of history, route-weighted sampling, seed=42 for reproducibility

### Slide 6 — ML Model: XGBoost Cost Predictor (3 min) — MOST IMPORTANT TECHNICAL SLIDE
- 11 features table with types and rationale
- Model architecture: XGBoost Regressor with hyperparameters
- Training: 80/20 split, MAE/MAPE/R² evaluation
- Inference pipeline: route lookup → feature engineering → predict → CI → historical comparison
- Key design: `build_inference_row()` as single source of truth prevents train/serve skew

### Slide 7 — Network Optimizer: PuLP LP (2.5 min)
- LP formulation: objective, 5 constraint types
- Decision variables: continuous flow + binary DC open/close
- Example output showing DC configuration + optimal route flows
- Budget sensitivity: tight $300K forces DC closures

### Slide 8 — Digital Twin: SimPy Simulation (2.5 min)
- 5 scenario types table
- Architecture: SimPy discrete-event, 1 event/day per DC
- Key design: capacity-proportional allocation (not cheapest-route)
- Baseline vs scenario with same RNG seed
- Metrics: cost, transit, service level, unmet demand, per-mode breakdown

### Slide 9 — 3-Agent LangGraph Architecture (3 min)
- Diagram: Planner → Analyst → Recommendation
- Each agent's role, LLM call type (ainvoke vs astream), and constraints
- SSE event flow diagram
- Why 3 > 1: prevents redundant calls, separates concerns, structured output

### Slide 10 — Frontend: React Real-Time UI (1.5 min)
- 3 screenshots: Chat Panel, Dashboard, Network Map
- Highlight: SSE streaming rendering, tool cards, mode pills, agent reasoning panel
- Design: Tesla dark theme

### Slide 11 — Results & Demo (2 min)
- Show 5 query/answer pairs demonstrating all 4 tools
- Screenshots or live demo of the chat panel with agent reasoning visible
- Key metrics: sub-10-second end-to-end latency from question to recommendation

### Slide 12 — Why This Maps to Tesla (1.5 min)
- JD requirement → what I built mapping table from Section 18

### Slide 13 — Close (1 min)
- One sentence: "I built a full-stack, production-pattern AI system that takes a supply chain manager from natural language question to data-driven, model-backed recommendation in under 10 seconds."
- What I'd add with more time: real distance matrix, feature store, A/B testing, Kubernetes + MLflow, Postgres + TimescaleDB

### Slide 14 — Q&A
- "Questions?"
- Backup slides with technical details ready

---

### DESIGN INSTRUCTIONS FOR THE PRESENTATION:
- Use a dark theme inspired by Tesla's brand: black/dark gray backgrounds, white text, red (#e82127) accents
- Use diagrams and architecture visuals — the team LOVES graphics
- Every slide should have at least one visual element (diagram, table, chart, or screenshot)
- Code snippets should be in dark-mode syntax highlighting
- Keep text minimal on slides — use the speaking notes for detail
- Include speaker notes on each slide with the detailed talking points
