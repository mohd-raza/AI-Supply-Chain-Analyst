"""
LangGraph ReAct agent orchestrator for ChainMind.

Uses Azure OpenAI gpt-5.2 with reasoning_effort=xhigh.

Stream events emitted to the SSE chat router:
  {"type": "thinking",    "content": "..."}   ← agent intermediate reasoning text
  {"type": "tool_call",   "tool": "...", "input": {...}}
  {"type": "tool_result", "tool": "...", "output": "..."}
  {"type": "answer",      "content": "..."}   ← final response to user
  {"type": "error",       "content": "..."}
"""
from __future__ import annotations

from typing import AsyncIterator

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_openai import AzureChatOpenAI
from langgraph.prebuilt import create_react_agent

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from agent.tools import ALL_TOOLS

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are ChainMind, an expert AI supply chain analyst for Tesla's inbound \
distribution network. You help supply chain managers make data-driven decisions about \
logistics costs, route optimization, and network design.

═══ DATABASE SCHEMA — use EXACT column names below ═══
  suppliers:            id | name | city | country | lat | lon | capacity_units_per_day
  distribution_centers: id | name | city | state | country | lat | lon
                        | capacity_units | fixed_cost_monthly | is_active
  routes:               id | origin_id | destination_id | mode
                        | distance_miles | base_cost_per_unit | transit_days
                        | capacity_units_per_day          ← NOT "daily_capacity"
  shipments:            id | route_id | shipment_date | units | actual_cost
                        | actual_transit_days | on_time | congestion_factor | season

  JOIN pattern:  shipments.route_id → routes.id
                 routes.origin_id   → suppliers.id
                 routes.destination_id → distribution_centers.id

  Supplier IDs:   SUP-SH (Shanghai) | SUP-SZ (Shenzhen) | SUP-MU (Munich)
                  SUP-MO (Monterrey) | SUP-DE (Detroit)
  DC IDs:         DC-FR (Fremont CA) | DC-AU (Austin TX)
                  DC-LA (Lathrop CA) | DC-ME (Memphis TN)
  Modes (exact):  truck | rail | ocean | air   (always lowercase)
  Date range:     shipment_date TEXT 'YYYY-MM-DD', data from 2023-01-01 to 2024-12-31
  "Last quarter": use date((SELECT MAX(shipment_date) FROM shipments), '-90 days')
═══════════════════════════════════════════════════════

You have access to three tools:
1. query_supply_chain_data  — run SQL SELECT queries against live shipment and route data
2. predict_shipping_cost    — ML-based cost prediction (XGBoost) for specific lanes and modes
3. optimize_network         — LP solver (PuLP) that finds the minimum-cost network configuration

Workflow guidelines:
- ALWAYS ground answers in data. Call at least one tool before concluding.
- For cost questions → predict_shipping_cost OR query historical averages first.
- For "optimize / minimize cost / best route" requests → optimize_network.
- For factual lookups (route lists, supplier capacities, on-time rates) → SQL query.
- After tool results, synthesize a clear, actionable recommendation in 3-5 bullet points.
- Express costs in USD with commas ($1,234,567). Express time in days.
- Use markdown tables (| col | col |) for tabular comparisons.
- STOP after getting enough data — do NOT keep querying once you have the answer.
- If a tool errors, fix the query immediately and retry ONCE. If it fails again, explain why.
- Maximum 3 tool calls per response unless the question explicitly requires more.

You represent Tesla's supply chain excellence — be precise, data-driven, and decisive."""


# ── LLM factory ───────────────────────────────────────────────────────────────

def _build_llm() -> AzureChatOpenAI:
    kwargs: dict = dict(
        azure_endpoint   = config.AZURE_OPENAI_ENDPOINT,
        azure_deployment = config.AZURE_OPENAI_DEPLOYMENT,
        api_key          = config.AZURE_OPENAI_API_KEY,
        api_version      = config.AZURE_OPENAI_API_VERSION,
        streaming        = True,
        temperature      = 1,          # required=1 for o-series / reasoning models
    )
    if config.REASONING_EFFORT:
        kwargs["reasoning_effort"] = config.REASONING_EFFORT
    return AzureChatOpenAI(**kwargs)


# ── Agent singleton ────────────────────────────────────────────────────────────

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        llm = _build_llm()
        _agent = create_react_agent(
            model  = llm,
            tools  = ALL_TOOLS,
            prompt = SYSTEM_PROMPT,
        )
    return _agent


# ── Streaming ─────────────────────────────────────────────────────────────────

async def stream_agent(
    user_message: str,
    history: list | None = None,
) -> AsyncIterator[dict]:
    """
    Yield SSE-ready event dicts as the ReAct agent works through a question.

    LangGraph stream_mode="updates" emits per-node state updates:
      • "agent" node → AIMessage: tool_calls present = decision step,
                                  no tool_calls + content = final answer
      • "tools" node → ToolMessage(s): results of each tool call

    We never re-invoke the agent; the final answer is extracted from the stream.
    """
    agent = _get_agent()

    # Build message history
    messages: list = []
    for m in (history or []):
        role = m.role if hasattr(m, "role") else m.get("role", "user")
        content = m.content if hasattr(m, "content") else m.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=user_message))

    try:
        async for chunk in agent.astream(
            {"messages": messages},
            stream_mode="updates",
            config={"recursion_limit": 12},   # cap at ~5 tool round-trips
        ):
            for node_name, node_output in chunk.items():

                # ── Agent node ─────────────────────────────────────────────
                if node_name == "agent":
                    for msg in node_output.get("messages", []):
                        if not isinstance(msg, AIMessage):
                            continue

                        has_tool_calls = bool(msg.tool_calls)
                        content_text   = str(msg.content).strip() if msg.content else ""

                        if has_tool_calls:
                            # Emit any prefacing text as "thinking"
                            if content_text:
                                yield {"type": "thinking", "content": content_text}
                            # Emit each tool invocation — include id so the frontend
                            # can match this call to its result unambiguously.
                            for tc in msg.tool_calls:
                                yield {
                                    "type": "tool_call",
                                    "tool": tc["name"],
                                    "input": tc.get("args", {}),
                                    "id":   tc.get("id", ""),
                                }
                        elif content_text:
                            # No tool calls + content = this IS the final answer
                            yield {"type": "answer", "content": content_text}

                # ── Tools node ─────────────────────────────────────────────
                elif node_name == "tools":
                    for msg in node_output.get("messages", []):
                        if isinstance(msg, ToolMessage):
                            yield {
                                "type":         "tool_result",
                                "tool":         msg.name,
                                "output":       str(msg.content),
                                "tool_call_id": getattr(msg, "tool_call_id", ""),
                            }

    except Exception as exc:
        yield {"type": "error", "content": f"Agent error: {exc}"}
