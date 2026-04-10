"""
ChainMind 3-Agent Orchestrator
================================
Three specialized AI agents run in sequence for every user message:

  1. Planner Agent       — reads the question, classifies intent, writes a
                           precise execution plan (no tools, no SQL)
  2. Analyst Agent       — executes the plan using all 3 tools (SQL / ML / LP)
                           and collects raw findings
  3. Recommendation Agent— synthesizes the findings into a clear, executive-ready
                           response with a concrete recommendation

SSE events emitted (superset of single-agent events):
  {"type": "agent_start",  "agent": "planner"|"analyst"|"recommendation",
                            "label": "human-readable phase label"}
  {"type": "thinking",     "content": "..."}
  {"type": "tool_call",    "tool": "...", "input": {...}, "id": "..."}
  {"type": "tool_result",  "tool": "...", "output": "...", "tool_call_id": "..."}
  {"type": "answer",       "content": "..."}
  {"type": "error",        "content": "..."}
"""
from __future__ import annotations

from typing import AsyncIterator

from langchain_core.messages import (
    HumanMessage, AIMessage, SystemMessage, ToolMessage,
)
from langchain_openai import AzureChatOpenAI
from langgraph.prebuilt import create_react_agent

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from agent.tools import ALL_TOOLS


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 1 — PLANNER SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

PLANNER_PROMPT = """\
You are the Planner Agent in ChainMind's 3-agent AI supply chain analysis \
system for Tesla's inbound distribution network.

Your ONLY job: read the user's question and produce a structured execution plan \
for the Analyst Agent.

Rules:
- Do NOT answer the question yourself.
- Do NOT call any tools.
- Do NOT write SQL.
- Just analyse and plan — the Analyst will execute.

Output EXACTLY this format (fill in every section):

INTENT: [one of: cost_query | optimization | comparison | factual_lookup | \
trend_analysis | what_if]

ENTITIES DETECTED:
  Suppliers : [comma-separated IDs, e.g. SUP-SH, SUP-SZ  — or "all"]
  DCs       : [comma-separated IDs, e.g. DC-FR  — or "all"]
  Modes     : [truck | rail | ocean | air  — or "all"]
  Time range: [quarter/year, e.g. "Q4 2024"  — or "latest available"]
  Volume    : [units if mentioned, else "not specified"]
  Budget    : [dollar amount if mentioned, else "not specified"]

ANALYSIS TASKS:
  1. [Specific task — one sentence, name the exact tool/query needed]
  2. [Second task if required]
  3. [Third task if required — maximum 3 tasks total]

TOOL ASSIGNMENTS:
  Task 1 → [query_supply_chain_data | predict_shipping_cost | optimize_network]
  Task 2 → [tool name or "n/a"]
  Task 3 → [tool name or "n/a"]

Known IDs (always use these exact strings):
  Suppliers : SUP-SH (Shanghai) | SUP-SZ (Shenzhen) | SUP-MU (Munich)
              SUP-MO (Monterrey) | SUP-DE (Detroit)
  DCs       : DC-FR (Fremont CA) | DC-AU (Austin TX)
              DC-LA (Lathrop CA) | DC-ME (Memphis TN)
  Modes     : truck | rail | ocean | air   (lowercase)
  Date range: 2023-01-01 → 2024-12-31; "last quarter" = latest 90 days in DB

Available tools (Analyst has all four):
  1. query_supply_chain_data  — SQL SELECT on live shipment/route data
  2. predict_shipping_cost    — XGBoost ML cost prediction for a specific lane+mode
  3. optimize_network         — PuLP LP solver, minimum-cost network configuration
  4. run_scenario             — Digital Twin SimPy simulation for what-if scenarios

Tool selection guide:
  "what if X happens / port closes / disruption / stress test / demand doubles"
      → run_scenario
  "optimize / minimize cost / which DCs to open"
      → optimize_network
  "predict cost / estimate / ML forecast"
      → predict_shipping_cost
  "historical data / on-time rates / totals / SQL lookup"
      → query_supply_chain_data

run_scenario scenario_type values (choose the closest match):
  port_closure   target=supplier_id  value=disruption_days  (e.g. SUP-SH, 14)
  cost_increase  target=mode|sup_id  value=pct              (e.g. ocean, 20)
  demand_shock   target=dc_id        value=multiplier        (e.g. DC-FR, 2.0)
  dc_closure     target=dc_id        value=1                 (e.g. DC-ME, 1)
  mode_shift     target=src_mode     value=1                 (e.g. ocean, 1)

Hard limits on tool assignments:
- optimize_network: EXACTLY ONE call. Never request both constrained + unconstrained.
- run_scenario:     EXACTLY ONE call per response.
- predict_shipping_cost: at most TWO calls (one per mode being compared).
- query_supply_chain_data: at most TWO SQL calls total.
- Maximum 3 tasks total regardless of question complexity.

Be concise and precise. The Analyst will execute exactly what you write here.\
"""


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 2 — ANALYST SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

ANALYST_PROMPT = """\
You are the Analyst Agent in ChainMind's 3-agent supply chain AI system for \
Tesla's inbound distribution network.

You receive a structured execution plan from the Planner Agent. Execute every \
task in that plan precisely using the available tools.

Your output must be raw findings only — numbers, tables, tool results.
Do NOT add recommendations, conclusions, or business interpretations.
The Recommendation Agent handles that.

═══ DATABASE SCHEMA — use EXACT column names ═══
  suppliers:            id | name | city | country | lat | lon | capacity_units_per_day
  distribution_centers: id | name | city | state | country | lat | lon
                        | capacity_units | fixed_cost_monthly | is_active
  routes:               id | origin_id | destination_id | mode
                        | distance_miles | base_cost_per_unit | transit_days
                        | capacity_units_per_day    ← NOT "daily_capacity"
  shipments:            id | route_id | shipment_date | units | actual_cost
                        | actual_transit_days | on_time | congestion_factor | season

  JOIN: shipments.route_id → routes.id
        routes.origin_id   → suppliers.id
        routes.destination_id → distribution_centers.id

  Supplier IDs : SUP-SH (Shanghai) | SUP-SZ (Shenzhen) | SUP-MU (Munich)
                 SUP-MO (Monterrey) | SUP-DE (Detroit)
  DC IDs       : DC-FR (Fremont CA) | DC-AU (Austin TX)
                 DC-LA (Lathrop CA) | DC-ME (Memphis TN)
  Modes        : truck | rail | ocean | air   (always lowercase)
  "Last quarter": date((SELECT MAX(shipment_date) FROM shipments), '-90 days')
═══════════════════════════════════════════════════

Tools available:
  1. query_supply_chain_data  — read-only SQL on shipments/routes/suppliers/DCs
  2. predict_shipping_cost    — XGBoost ML cost prediction
  3. optimize_network         — PuLP LP network optimizer
  4. run_scenario             — Digital Twin SimPy what-if simulator
     Scenario types: port_closure | cost_increase | demand_shock | dc_closure | mode_shift

Guidelines:
- Execute ALL tasks in the plan — do not skip any.
- STOP once all tasks are complete. Do not add extra queries.
- If a tool errors, fix the query immediately and retry once.
- Call optimize_network at most ONCE — never run a second unconstrained solve.
- Call run_scenario at most ONCE per response.
- Maximum 3 tool calls total.\
"""


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 3 — RECOMMENDATION SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

RECOMMENDATION_PROMPT = """\
You are the Recommendation Agent in ChainMind's 3-agent supply chain AI system \
for Tesla's inbound distribution network.

You receive:
  1. The user's original question
  2. The Analyst Agent's raw findings (tool outputs, numbers, tables)

Your job: synthesise these findings into a concise, executive-ready response.

Response structure (always follow this order):
  1. Opening sentence — state the key answer/insight directly.
     Bold (**text**) the single most important number.
  2. Supporting data — use a markdown table (| col | col |) if comparing ≥2 options.
     Use ▸ bullet points for non-tabular lists.
  3. **Recommendation:** — one specific, actionable decision.
     Example: "Use ocean freight on RT-001 — saves $1,514 vs air for this shipment."

Style rules:
  - Express costs in USD with commas: $1,234,567
  - Express time in days with 1 decimal: 22.0 days
  - Use ### for section headings if the response has multiple logical sections
  - Be concise — supply chain managers are busy; avoid lengthy prose
  - Never repeat the Analyst's raw tool output verbatim; interpret it

You represent Tesla's supply chain excellence. Be precise, data-driven, \
and decisive.\
"""


# ══════════════════════════════════════════════════════════════════════════════
# LLM + AGENT SINGLETONS
# ══════════════════════════════════════════════════════════════════════════════

_llm: AzureChatOpenAI | None = None
_analyst_agent = None


def _get_llm() -> AzureChatOpenAI:
    global _llm
    if _llm is None:
        kwargs: dict = dict(
            azure_endpoint   = config.AZURE_OPENAI_ENDPOINT,
            azure_deployment = config.AZURE_OPENAI_DEPLOYMENT,
            api_key          = config.AZURE_OPENAI_API_KEY,
            api_version      = config.AZURE_OPENAI_API_VERSION,
            streaming        = True,
            temperature      = 1,          # required for o-series reasoning models
        )
        if config.REASONING_EFFORT:
            kwargs["reasoning_effort"] = config.REASONING_EFFORT
        _llm = AzureChatOpenAI(**kwargs)
    return _llm


def _get_analyst_agent():
    global _analyst_agent
    if _analyst_agent is None:
        _analyst_agent = create_react_agent(
            model  = _get_llm(),
            tools  = ALL_TOOLS,
            prompt = ANALYST_PROMPT,
        )
    return _analyst_agent


# ══════════════════════════════════════════════════════════════════════════════
# MAIN STREAMING FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

async def stream_multi_agent(
    user_message: str,
    history: list | None = None,
) -> AsyncIterator[dict]:
    """
    Run all 3 agents in sequence, yielding SSE-ready event dicts throughout.

    Phase 1 — Planner       : single ainvoke call (no tools); the complete plan
                               is yielded as ONE thinking event so it renders
                               as a clean formatted block, not scattered tokens.
    Phase 2 — Analyst       : ReAct astream loop with tools; tool_call /
                               tool_result events stream in real-time.
    Phase 3 — Recommendation: single ainvoke call (no tools); full synthesised
                               answer yielded as the answer event.
    """
    llm = _get_llm()

    # ── build conversation context (shared across all 3 agents) ───────────────
    def _history_messages():
        msgs = []
        for m in (history or []):
            role    = m.role if hasattr(m, "role") else m.get("role", "user")
            content = m.content if hasattr(m, "content") else m.get("content", "")
            if role == "user":
                msgs.append(HumanMessage(content=content))
            elif role == "assistant":
                msgs.append(AIMessage(content=content))
        return msgs

    try:

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 1 — PLANNER AGENT
        # ══════════════════════════════════════════════════════════════════════
        yield {
            "type":  "agent_start",
            "agent": "planner",
            "label": "Planner Agent — Decomposing your request",
        }

        planner_messages = (
            [SystemMessage(content=PLANNER_PROMPT)]
            + _history_messages()
            + [HumanMessage(content=user_message)]
        )

        # ainvoke — collect the complete plan as one response, then emit it as
        # a single thinking event.  astream would fire one event per token,
        # causing every word to appear on its own line in the reasoning panel.
        planner_response = await llm.ainvoke(planner_messages)
        planner_output   = str(planner_response.content).strip()

        if not planner_output:
            yield {"type": "error", "content": "Planner Agent returned an empty plan."}
            return

        yield {"type": "thinking", "content": planner_output}

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 2 — ANALYST AGENT
        # ══════════════════════════════════════════════════════════════════════
        yield {
            "type":  "agent_start",
            "agent": "analyst",
            "label": "Analyst Agent — Running analysis",
        }

        analyst_input = (
            f"Execute this analysis plan:\n\n{planner_output}"
            f"\n\n---\nOriginal user question: {user_message}"
        )
        analyst_messages = (
            _history_messages()
            + [HumanMessage(content=analyst_input)]
        )

        analyst_output_parts: list[str] = []
        analyst = _get_analyst_agent()

        async for chunk in analyst.astream(
            {"messages": analyst_messages},
            stream_mode="updates",
            config={"recursion_limit": 12},
        ):
            for node_name, node_output in chunk.items():

                # ── agent node — LLM decisions ──────────────────────────────
                if node_name == "agent":
                    for msg in node_output.get("messages", []):
                        if not isinstance(msg, AIMessage):
                            continue
                        has_tool_calls = bool(msg.tool_calls)
                        content_text   = str(msg.content).strip() if msg.content else ""

                        if has_tool_calls:
                            if content_text:
                                yield {"type": "thinking", "content": content_text}
                            for tc in msg.tool_calls:
                                yield {
                                    "type":  "tool_call",
                                    "tool":  tc["name"],
                                    "input": tc.get("args", {}),
                                    "id":    tc.get("id", ""),
                                }
                        elif content_text:
                            # Analyst's final summary — capture for recommendation
                            analyst_output_parts.append(content_text)

                # ── tools node — results come back ──────────────────────────
                elif node_name == "tools":
                    for msg in node_output.get("messages", []):
                        if isinstance(msg, ToolMessage):
                            yield {
                                "type":         "tool_result",
                                "tool":         msg.name,
                                "output":       str(msg.content),
                                "tool_call_id": getattr(msg, "tool_call_id", ""),
                            }

        analyst_output = "\n\n".join(analyst_output_parts).strip()

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 3 — RECOMMENDATION AGENT
        # ══════════════════════════════════════════════════════════════════════
        yield {
            "type":  "agent_start",
            "agent": "recommendation",
            "label": "Recommendation Agent — Synthesizing insights",
        }

        rec_human = (
            f"User's question: {user_message}\n\n"
            f"Analyst's findings:\n{analyst_output if analyst_output else '(analyst produced no text summary — use the tool results streamed above)'}\n\n"
            f"Write the final response now."
        )
        rec_messages = [
            SystemMessage(content=RECOMMENDATION_PROMPT),
            HumanMessage(content=rec_human),
        ]

        response = await llm.ainvoke(rec_messages)
        final_answer = str(response.content).strip()

        if final_answer:
            yield {"type": "answer", "content": final_answer}
        else:
            yield {"type": "error", "content": "Recommendation Agent returned an empty response."}

    except Exception as exc:
        yield {"type": "error", "content": f"Multi-agent error: {exc}"}
