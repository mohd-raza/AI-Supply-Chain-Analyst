/**
 * ChainMind API client
 *
 * fetchStream()     — POST /api/chat, yields parsed SSE event objects
 * getKPIs()         — GET /api/dashboard/kpis
 * getCostBreakdown()— GET /api/dashboard/cost-breakdown
 * getTopRoutes()    — GET /api/dashboard/top-routes
 * getBottlenecks()  — GET /api/dashboard/bottlenecks
 * getNetwork()      — GET /api/network
 * getSuppliers()    — GET /api/network/suppliers
 * getDCs()          — GET /api/network/dcs
 * getRoutes()       — GET /api/network/routes
 * healthCheck()     — GET /health
 */

// const BASE = ''  // Vite proxy rewrites /api → localhost:8000
const BASE = import.meta.env.VITE_API_BASE_URL || "";
// ── Generic fetch helpers ─────────────────────────────────────────────────────

async function get(path) {
  let res;
  try {
    res = await fetch(BASE + path);
  } catch (err) {
    throw new Error(
      `Backend unreachable — make sure uvicorn is running on port 8000. (${err.message})`,
    );
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`GET ${path} → ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

// ── SSE streaming  ────────────────────────────────────────────────────────────

/**
 * POST /api/chat and yield SSE event objects as they arrive.
 *
 * Each yielded object is one of:
 *   { type: "thinking",    content: string }
 *   { type: "tool_call",   tool: string, input: object }
 *   { type: "tool_result", tool: string, output: string }
 *   { type: "answer",      content: string }
 *   { type: "error",       content: string }
 *
 * Yields null when the stream is finished ([DONE] sentinel).
 *
 * @param {string} message  — user's question
 * @param {Array}  history  — [{role, content}, ...] prior messages
 * @returns {AsyncGenerator<object>}
 */
export async function* fetchStream(message, history = []) {
  let res;
  try {
    res = await fetch(BASE + "/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    });
  } catch (err) {
    yield {
      type: "error",
      content:
        "Cannot reach the backend server.\n\n" +
        "Make sure it is running:\n" +
        "  cd backend\n" +
        "  uvicorn main:app --reload --port 8000\n\n" +
        `(${err.message})`,
    };
    return;
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    yield {
      type: "error",
      content: `Server error ${res.status}: ${text || res.statusText}`,
    };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE lines are separated by \n\n; process complete events
    const parts = buffer.split("\n\n");
    buffer = parts.pop(); // keep trailing incomplete fragment

    for (const part of parts) {
      for (const line of part.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") return; // stream finished
        try {
          yield JSON.parse(raw);
        } catch {
          // malformed chunk — skip
        }
      }
    }
  }
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export const getKPIs = () => get("/api/dashboard/kpis");
export const getCostBreakdown = () => get("/api/dashboard/cost-breakdown");
export const getTopRoutes = (limit = 10) =>
  get(`/api/dashboard/top-routes?limit=${limit}`);
export const getBottlenecks = () => get("/api/dashboard/bottlenecks");

// ── Network ───────────────────────────────────────────────────────────────────

export const getNetwork = () => get("/api/network");
export const getSuppliers = () => get("/api/network/suppliers");
export const getDCs = () => get("/api/network/dcs");
export const getRoutes = () => get("/api/network/routes");

// ── Meta ──────────────────────────────────────────────────────────────────────

export const healthCheck = () => get("/health");
