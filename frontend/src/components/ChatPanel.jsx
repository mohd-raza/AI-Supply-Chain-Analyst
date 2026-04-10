/**
 * ChatPanel — Demo centerpiece for ChainMind.
 *
 * Features:
 *  • fetchStream() SSE loop with live event rendering
 *  • Per-event-type styling: thinking / tool_call / tool_result / answer / error
 *  • Tool-specific icons and accent colors (SQL=blue, Predict=purple, Optimize=green)
 *  • Smart text renderer: handles ━━ headers, bullet trees, $-numbers, code spans
 *  • Collapsible "Agent Reasoning" section per message
 *  • Auto-scroll with momentum, auto-resize textarea
 *  • Copy answer, clear conversation
 *  • Typing indicator skeleton while streaming
 */

import {
  useState, useEffect, useRef, useCallback, useMemo,
} from 'react'
import {
  Send, Loader2, Zap, ChevronDown, ChevronRight,
  Database, BarChart3, Network, Brain, CheckCircle2,
  AlertCircle, Copy, Check, RotateCcw, Wrench, Sparkles,
  Clock, FlaskConical,
} from 'lucide-react'
import { fetchStream } from '../api/client.js'

// ── Design constants ───────────────────────────────────────────────────────────
const RED    = '#e82127'
const BORDER = '#2a2a2a'
const DIM    = '#6b7280'

// Per-tool visual identity
const TOOL_META = {
  query_supply_chain_data: {
    label:  'SQL Query',
    Icon:   Database,
    color:  '#3b82f6',
    bg:     '#3b82f615',
    border: '#3b82f630',
  },
  predict_shipping_cost: {
    label:  'Cost Predictor',
    Icon:   BarChart3,
    color:  '#8b5cf6',
    bg:     '#8b5cf615',
    border: '#8b5cf630',
  },
  optimize_network: {
    label:  'Network Optimizer',
    Icon:   Network,
    color:  '#10b981',
    bg:     '#10b98115',
    border: '#10b98130',
  },
  run_scenario: {
    label:  'Digital Twin',
    Icon:   FlaskConical,
    color:  '#f97316',
    bg:     '#f9731615',
    border: '#f9731630',
  },
}

const DEFAULT_TOOL = {
  label:  'Tool',
  Icon:   Wrench,
  color:  DIM,
  bg:     '#1a1a1a',
  border: BORDER,
}

function getToolMeta(toolName) {
  return TOOL_META[toolName] ?? DEFAULT_TOOL
}

// The 5 canonical demo queries (exactly as specified in .cursorrules)
const SUGGESTIONS = [
  { icon: '💰', text: 'What is our total inbound shipping cost this quarter?' },
  { icon: '🚢', text: "What's the cheapest way to ship 100 units from Shanghai to Fremont?" },
  { icon: '⚡', text: 'Optimize our network to minimize total cost with a $500K monthly budget' },
  { icon: '📦', text: 'Which routes have the worst on-time delivery rates?' },
  { icon: '🚛', text: 'Compare shipping costs: truck vs ocean from Shenzhen to Austin' },
]

// ── Utility: format timestamp ─────────────────────────────────────────────────
function fmtTime(date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// ── Inline token renderer ──────────────────────────────────────────────────────
// Turns $1,234 → green, mode words → pills, **bold**, `code`, emojis → pass-through
function renderInline(text) {
  const tokens = []
  // Case-insensitive flag so TRUCK / OCEAN / ocean / truck all match
  const pattern = /(\$[\d,]+(?:\.\d+)?[KMB]?|\b(truck|rail|ocean|air)\b|`[^`]+`|\*\*[^*]+\*\*)/gi
  let last = 0; let idx = 0; let m
  const MODE_COL = { ocean:'#3b82f6', truck:'#f59e0b', rail:'#10b981', air:'#8b5cf6' }

  while ((m = pattern.exec(text)) !== null) {
    if (m.index > last) tokens.push(<span key={idx++} style={{ color: '#ececec' }}>{text.slice(last, m.index)}</span>)
    const tok = m[0]
    if (/^\$[\d,]/.test(tok)) {
      tokens.push(<span key={idx++} style={{ color: '#34d399' }} className="font-mono font-medium">{tok}</span>)
    } else if (MODE_COL[tok.toLowerCase()]) {
      const mc = MODE_COL[tok.toLowerCase()]
      tokens.push(
        <span key={idx++}
          style={{ background: mc+'22', color: mc, border:`1px solid ${mc}44` }}
          className="text-[10px] px-1.5 py-0.5 rounded uppercase mx-0.5 inline-block leading-tight">
          {tok.toLowerCase()}
        </span>
      )
    } else if (tok.startsWith('`')) {
      tokens.push(
        <code key={idx++} style={{ background:'#1e1e1e', color:'#a78bfa', border:'1px solid #333' }}
          className="text-[11px] px-1.5 py-0.5 rounded font-mono">{tok.slice(1,-1)}</code>
      )
    } else if (tok.startsWith('**')) {
      const inner = tok.slice(2, -2).trim()
      const modeColor = MODE_COL[inner.toLowerCase()]
      if (modeColor) {
        // **ocean** / **truck** etc → render as coloured pill, not plain bold
        tokens.push(
          <span key={idx++}
            style={{ background: modeColor+'22', color: modeColor, border:`1px solid ${modeColor}44` }}
            className="text-[10px] px-1.5 py-0.5 rounded uppercase mx-0.5 inline-block leading-tight">
            {inner}
          </span>
        )
      } else {
        tokens.push(<strong key={idx++} className="font-semibold text-white">{inner}</strong>)
      }
    } else {
      tokens.push(<span key={idx++}>{tok}</span>)
    }
    last = m.index + tok.length
  }
  if (last < text.length) tokens.push(<span key={idx++} style={{ color: '#ececec' }}>{text.slice(last)}</span>)
  return tokens
}

// ── Markdown table ──────────────────────────────────────────────────────────────
function MarkdownTable({ lines }) {
  const parseRow = (line) =>
    line.split('|').slice(1, -1).map(c => c.trim())

  const isSep = (line) => /^\s*\|[\s\-:|]+\|\s*$/.test(line)
  const sepIdx = lines.findIndex(isSep)

  let headers = [], aligns = [], rows = []

  if (sepIdx === 1) {
    headers = parseRow(lines[0])
    aligns  = parseRow(lines[1]).map(c => {
      if (c.startsWith(':') && c.endsWith(':')) return 'center'
      if (c.endsWith(':')) return 'right'
      return 'left'
    })
    rows = lines.slice(2).map(parseRow)
  } else {
    rows = lines.map(parseRow)
  }

  return (
    <div className="my-2 overflow-x-auto rounded-lg"
      style={{ border: '1px solid #2a2a2a', background: '#0d0d0d' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
        {headers.length > 0 && (
          <thead>
            <tr style={{ background: '#161616' }}>
              {headers.map((h, i) => (
                <th key={i} style={{
                  textAlign: aligns[i] || 'left',
                  padding: '7px 14px',
                  borderBottom: '1px solid #2a2a2a',
                  color: '#c8d0d8',
                  fontSize: 11,
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                  letterSpacing: '0.04em',
                  textTransform: 'uppercase',
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} style={{
              borderBottom: ri < rows.length - 1 ? '1px solid #1a1a1a' : 'none',
              background: ri % 2 === 1 ? '#0a0a0a' : 'transparent',
            }}>
              {row.map((cell, ci) => {
                const isMoney = /^\$[\d,]/.test(cell)
                const isPct   = /^\d+(\.\d+)?%$/.test(cell)
                return (
                  <td key={ci} style={{
                    textAlign: aligns[ci] || 'left',
                    padding: '6px 14px',
                    color: isMoney ? '#34d399' : isPct ? '#f5f5f5' : '#e4e8ec',
                    fontFamily: (isMoney || isPct) ? 'ui-monospace,monospace' : 'inherit',
                    fontWeight: isMoney ? 500 : 400,
                  }}>
                    {renderInline(cell)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Single text line renderer ──────────────────────────────────────────────────
function renderLine(line, i) {
  // Markdown headings  #  ##  ###  ####
  if (/^#{1,4}\s/.test(line)) {
    const level = (line.match(/^(#+)/)?.[1] ?? '#').length
    const title = line.replace(/^#+\s*/, '').trim()
    return (
      <div key={i} style={{ marginTop: level <= 2 ? 14 : 10, marginBottom: 4 }}>
        <span style={{
          color: '#f5f5f5',
          fontSize: level === 1 ? 15 : level === 2 ? 13.5 : 12.5,
          fontWeight: level <= 2 ? 700 : 600,
          letterSpacing: level >= 3 ? '0.01em' : 0,
        }}>
          {renderInline(title)}
        </span>
        {level <= 2 && (
          <div style={{ height: 1, background: '#2a2a2a', marginTop: 4 }} />
        )}
      </div>
    )
  }

  if (/^━+/.test(line)) {
    const title = line.replace(/━+/g, '').trim()
    return (
      <div key={i} style={{ borderBottom: '1px solid #2a2a2a' }}
        className="pb-1 mb-2 mt-3 first:mt-0">
        <span style={{ color: '#ececec', fontSize: 12, fontWeight: 600, letterSpacing: '0.04em' }}>{title}</span>
      </div>
    )
  }
  if (/^[-=]{10,}$/.test(line.trim()))
    return <hr key={i} style={{ borderColor: '#2a2a2a' }} className="my-2" />
  if (!line.trim()) return <div key={i} className="h-1.5" />

  const indent  = line.match(/^(\s+)/)?.[1]?.length ?? 0
  const isBullet = /^\s*[•\-*]\s/.test(line)
  return (
    <div key={i}
      style={{ paddingLeft: Math.max(indent * 6, isBullet ? 12 : 0) }}
      className={`leading-relaxed ${isBullet ? 'flex gap-1 items-start' : ''}`}>
      {isBullet && <span style={{ color: RED, flexShrink: 0 }} className="mt-0.5 text-[10px]">▸</span>}
      <span style={{ fontSize: 13, color: '#ececec' }}>{renderInline(line.replace(/^\s*[•\-*]\s/, ''))}</span>
    </div>
  )
}

// ── Smart text — splits into table blocks and regular lines ────────────────────
function SmartText({ text }) {
  const lines = (text || '').split('\n')
  const segments = []
  let i = 0
  while (i < lines.length) {
    if (/^\s*\|/.test(lines[i])) {
      const tableLines = []
      while (i < lines.length && /^\s*\|/.test(lines[i])) {
        tableLines.push(lines[i])
        i++
      }
      segments.push({ type: 'table', lines: tableLines })
    } else {
      segments.push({ type: 'line', text: lines[i], idx: i })
      i++
    }
  }
  return (
    <div className="flex flex-col gap-0.5">
      {segments.map((seg, si) =>
        seg.type === 'table'
          ? <MarkdownTable key={si} lines={seg.lines} />
          : renderLine(seg.text, si)
      )}
    </div>
  )
}

// ── Copy button ────────────────────────────────────────────────────────────────
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }
  return (
    <button onClick={copy} title="Copy"
      style={{ color: copied ? '#10b981' : DIM }}
      className="hover:text-white transition-colors p-1 rounded">
      {copied ? <Check size={12}/> : <Copy size={12}/>}
    </button>
  )
}

// ── Thinking event ─────────────────────────────────────────────────────────────
function ThinkingStep({ content }) {
  // Filter out "Task N → n/a" lines — they add visual noise without information.
  // Use <pre> so the planner's structured output (newlines, indentation) renders
  // correctly; white-space: pre-wrap prevents horizontal overflow.
  const filtered = (content || '')
    .split('\n')
    .filter(line => !/→\s*n\/a\s*$/i.test(line.trim()))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')   // collapse triple+ blank lines to double
    .trim()

  if (!filtered) return null
  return (
    <div className="flex items-start gap-2.5">
      <div className="flex gap-0.5 shrink-0 mt-1.5">
        {[0,1,2].map(i => (
          <span key={i} className="thinking-dot w-1.5 h-1.5 rounded-full"
            style={{ background: RED, animationDelay: `${i*0.2}s` }} />
        ))}
      </div>
      <pre style={{
        color: '#9aabb8',
        fontSize: 11,
        fontFamily: 'inherit',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        lineHeight: 1.65,
        margin: 0,
      }}>{filtered}</pre>
    </div>
  )
}

// ── Tool call event ────────────────────────────────────────────────────────────
function ToolCallStep({ event, resultEvent }) {
  const [open, setOpen] = useState(false)
  const meta = getToolMeta(event.tool)
  const { Icon, color, bg, border } = meta

  // Format inputs as readable key-value pairs
  const inputPairs = Object.entries(event.input || {})

  return (
    <div className="rounded-lg overflow-hidden" style={{ border: `1px solid ${border}` }}>
      {/* Header row */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left transition-colors hover:brightness-110"
        style={{ background: bg }}>

        <div style={{ background: color+'30', borderRadius: 4, padding: 3 }}>
          <Icon size={11} style={{ color }} />
        </div>

        <span style={{ color }} className="text-xs font-medium">{meta.label}</span>

        {/* Status badge */}
        {resultEvent ? (
          <span style={{ background:'#10b98120', color:'#10b981', border:'1px solid #10b98130' }}
            className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full flex items-center gap-1">
            <CheckCircle2 size={9}/> done
          </span>
        ) : (
          <span style={{ background:'#f59e0b20', color:'#f59e0b', border:'1px solid #f59e0b30' }}
            className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full flex items-center gap-1">
            <Loader2 size={9} className="animate-spin"/> running
          </span>
        )}

        <span style={{ color: DIM }}>
          {open ? <ChevronDown size={11}/> : <ChevronRight size={11}/>}
        </span>
      </button>

      {/* Expanded: inputs + result */}
      {open && (
        <div style={{ borderTop: `1px solid ${border}` }}>
          {/* Inputs */}
          {inputPairs.length > 0 && (
            <div style={{ background: '#0d0d0d' }} className="px-3 py-2">
              <p style={{ color: DIM }} className="text-[10px] uppercase tracking-widest mb-1.5">Inputs</p>
              <div className="flex flex-col gap-1">
                {inputPairs.map(([k, v]) => (
                  <div key={k} className="flex gap-2 text-xs">
                    <span style={{ color: DIM }} className="shrink-0 w-32 font-mono">{k}</span>
                    <span style={{ color: '#d1d5db' }} className="font-mono break-all">
                      {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Result */}
          {resultEvent && (
            <div style={{ background: '#0a0a0a', borderTop: `1px solid ${border}` }}
              className="px-3 py-2">
              <div className="flex items-center justify-between mb-1.5">
                <p style={{ color: DIM }} className="text-[10px] uppercase tracking-widest">Output</p>
                <CopyButton text={resultEvent.output} />
              </div>
              <pre style={{ color: '#9ca3af', fontFamily: 'ui-monospace, monospace' }}
                className="text-[11px] leading-relaxed whitespace-pre-wrap break-words max-h-52 overflow-y-auto">
                {resultEvent.output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Agent divider constants ─────────────────────────────────────────────────
const AGENT_META = {
  planner:        { color: '#7c3aed', icon: '🎯', label: 'Planner Agent' },
  analyst:        { color: '#0ea5e9', icon: '🔬', label: 'Analyst Agent' },
  recommendation: { color: '#10b981', icon: '💡', label: 'Recommendation Agent' },
}

// ── Reasoning panel (groups all steps for one message) ─────────────────────────
function ReasoningPanel({ steps, isStreaming }) {
  const [collapsed, setCollapsed] = useState(false)

  // Three-pass build:
  //   Pass 1 — flatten all events into ordered entries (agent dividers + thinking + tool calls)
  //   Pass 2 — attach tool_results to their calls by id (or FIFO fallback)
  const rendered = useMemo(() => {
    const out = []
    const byId = {}

    // Pass 1
    for (let i = 0; i < steps.length; i++) {
      const s = steps[i]
      if (s.type === 'agent_start') {
        out.push({ kind: 'agent_divider', step: s, key: i })
      } else if (s.type === 'thinking') {
        out.push({ kind: 'thinking', step: s, key: i })
      } else if (s.type === 'tool_call') {
        const entry = { kind: 'tool', callStep: s, resultStep: null, key: i }
        out.push(entry)
        if (s.id) byId[s.id] = entry
      }
    }

    // Pass 2 — attach results; prefer id-match, fall back to FIFO per tool name
    const queues = {}
    for (const entry of out) {
      if (entry.kind === 'tool') {
        const name = entry.callStep.tool
        if (!queues[name]) queues[name] = []
        queues[name].push(entry)
      }
    }
    for (const s of steps) {
      if (s.type !== 'tool_result') continue
      if (s.tool_call_id && byId[s.tool_call_id]) {
        byId[s.tool_call_id].resultStep = s
      } else {
        const q = queues[s.tool]
        if (q?.length) q.shift().resultStep = s
      }
    }

    return out
  }, [steps])

  if (!rendered.length) return null

  const toolCount = rendered.filter(r => r.kind === 'tool').length
  const doneCount = rendered.filter(r => r.kind === 'tool' && r.resultStep).length
  const agentCount = rendered.filter(r => r.kind === 'agent_divider').length
  const is3Agent = agentCount > 0

  return (
    <div style={{ border: `1px solid ${BORDER}`, background: '#0b0b0b' }}
      className="rounded-xl overflow-hidden">

      {/* Toggle header */}
      <button
        onClick={() => setCollapsed(c => !c)}
        className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-[#111] transition-colors">

        <Brain size={12} style={{ color: RED }} />
        <span style={{ color: '#b8c0cc' }} className="text-xs font-medium">
          {is3Agent ? '3-Agent Reasoning' : 'Agent Reasoning'}
        </span>

        {/* Agent badges when 3-agent mode active */}
        {is3Agent && (
          <div className="flex items-center gap-1 ml-1">
            {['planner', 'analyst', 'recommendation'].map(a => {
              const meta = AGENT_META[a]
              const active = steps.some(s => s.type === 'agent_start' && s.agent === a)
              return active ? (
                <span key={a} style={{
                  background: meta.color + '18',
                  color: meta.color,
                  border: `1px solid ${meta.color}40`,
                  fontSize: 9,
                  padding: '1px 5px',
                  borderRadius: 4,
                  fontWeight: 600,
                  letterSpacing: '0.03em',
                }}>
                  {meta.icon} {a}
                </span>
              ) : null
            })}
          </div>
        )}

        <div className="flex items-center gap-1.5 ml-2">
          {toolCount > 0 && (
            <span style={{ background: '#1e1e1e', color: DIM, border: `1px solid ${BORDER}` }}
              className="text-[10px] px-1.5 py-0.5 rounded-full">
              {doneCount}/{toolCount} tools
            </span>
          )}
          {isStreaming && (
            <span style={{ color: '#f59e0b' }} className="text-[10px] flex items-center gap-1">
              <Loader2 size={9} className="animate-spin" /> working
            </span>
          )}
        </div>

        <span style={{ color: DIM }} className="ml-auto">
          {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
        </span>
      </button>

      {/* Steps */}
      {!collapsed && (
        <div style={{ borderTop: `1px solid ${BORDER}` }}
          className="px-4 py-3 flex flex-col gap-2.5">
          {rendered.map(r => {
            if (r.kind === 'agent_divider') {
              const meta = AGENT_META[r.step.agent] || { color: '#6b7280', icon: '◈', label: r.step.agent }
              return (
                <div key={r.key} className="flex items-center gap-2"
                  style={{ marginTop: r.key === 0 ? 0 : 6, marginBottom: 2 }}>
                  <div style={{ height: 1, background: meta.color + '30', flex: 1 }} />
                  <span style={{
                    color: meta.color,
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: '0.05em',
                    whiteSpace: 'nowrap',
                  }}>
                    {meta.icon} {r.step.label || meta.label}
                  </span>
                  <div style={{ height: 1, background: meta.color + '30', flex: 1 }} />
                </div>
              )
            }
            if (r.kind === 'thinking') return <ThinkingStep key={r.key} content={r.step.content} />
            return <ToolCallStep key={r.key} event={r.callStep} resultEvent={r.resultStep} />
          })}
        </div>
      )}
    </div>
  )
}

// ── Typing indicator (while waiting for first byte) ────────────────────────────
function TypingIndicator() {
  return (
    <div className="flex items-center gap-2 px-4 py-3 rounded-xl"
      style={{ background: '#111', border: `1px solid ${BORDER}`, width: 'fit-content' }}>
      <div className="flex gap-1">
        {[0, 1, 2].map(i => (
          <span key={i} className="thinking-dot w-2 h-2 rounded-full"
            style={{ background: '#4b5563', animationDelay: `${i * 0.15}s` }} />
        ))}
      </div>
      <span style={{ color: DIM }} className="text-xs">ChainMind is thinking…</span>
    </div>
  )
}

// ── User message bubble ────────────────────────────────────────────────────────
function UserBubble({ content, timestamp }) {
  return (
    <div className="flex flex-col items-end gap-1 fade-in">
      <div style={{ background: '#1c1c1c', border: `1px solid #333`, borderTopRightRadius: 4 }}
        className="rounded-2xl px-4 py-3 max-w-[72%]">
        <p style={{ color: '#f5f5f5', fontSize: 13, lineHeight: 1.6 }}>{content}</p>
      </div>
      {timestamp && (
        <span style={{ color: '#444' }} className="text-[10px] flex items-center gap-1 pr-1">
          <Clock size={9}/>{fmtTime(timestamp)}
        </span>
      )}
    </div>
  )
}

// ── Agent message bubble ───────────────────────────────────────────────────────
function AgentBubble({ msg }) {
  const { content, steps, streaming, timestamp, error } = msg

  const showTypingIndicator = streaming && !steps?.length && !content

  return (
    <div className="flex gap-3 items-start fade-in max-w-[88%]">
      {/* Avatar */}
      <div style={{ background: error ? '#7f1d1d' : '#1a0a0a', border: `1px solid ${error ? '#991b1b' : '#2a1010'}` }}
        className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
        {error
          ? <AlertCircle size={13} color="#ef4444" />
          : <Zap size={13} style={{ color: RED }} strokeWidth={2.5} />
        }
      </div>

      <div className="flex flex-col gap-2 min-w-0 flex-1">
        {/* Reasoning panel */}
        {steps && steps.length > 0 && (
          <ReasoningPanel steps={steps} isStreaming={streaming && !content} />
        )}

        {/* Typing indicator before first content */}
        {showTypingIndicator && <TypingIndicator />}

        {/* Answer bubble */}
        {content && (
          <div style={{
            background: error ? '#1a0808' : '#111',
            border: `1px solid ${error ? '#7f1d1d' : BORDER}`,
            borderTopLeftRadius: steps?.length ? 8 : 4,
          }}
            className="rounded-2xl px-4 py-3 relative group">

            {/* Copy button (shows on hover) */}
            <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <CopyButton text={content} />
            </div>

            <SmartText text={content} />

            {streaming && (
              <span className="cursor-blink" />
            )}
          </div>
        )}

        {timestamp && !streaming && (
          <span style={{ color: '#444' }} className="text-[10px] flex items-center gap-1 pl-1">
            <Clock size={9}/>{fmtTime(timestamp)}
          </span>
        )}
      </div>
    </div>
  )
}

// ── Suggestion chips ───────────────────────────────────────────────────────────
function SuggestionChips({ onSelect }) {
  return (
    <div className="px-6 pb-4 fade-in">
      <p style={{ color: DIM }} className="text-xs mb-3 flex items-center gap-1.5">
        <Sparkles size={11} style={{ color: RED }}/> Try asking…
      </p>
      <div className="flex flex-wrap gap-2">
        {SUGGESTIONS.map(({ icon, text }, i) => (
          <button key={i} onClick={() => onSelect(text)}
            style={{ border: `1px solid ${BORDER}`, color: '#9ca3af', background: '#111' }}
            className="text-xs px-3 py-2 rounded-xl hover:border-[#444] hover:text-white hover:bg-[#161616] transition-all flex items-center gap-1.5">
            <span>{icon}</span>
            <span>{text}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main ChatPanel
// ═══════════════════════════════════════════════════════════════════════════════
export default function ChatPanel() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: [
        "Hello! I'm **ChainMind**, Tesla's AI supply chain analyst.",
        '',
        'I have live access to our inbound network:',
        '  • 5 global suppliers (Shanghai, Shenzhen, Munich, Monterrey, Detroit)',
        '  • 4 Distribution Centers (Fremont, Austin, Lathrop, Memphis)',
        '  • 30 active routes across truck, rail, ocean & air',
        '  • 20,000+ historical shipments over 2 years',
        '',
        'Ask me about costs, route optimization, bottlenecks, or network design.',
      ].join('\n'),
      steps: [],
      streaming: false,
      timestamp: new Date(),
    },
  ])
  const [input, setInput]     = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef             = useRef(null)
  const textareaRef           = useRef(null)
  const isFirstMessage        = messages.length <= 1

  // Auto-scroll on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 140) + 'px'
  }, [input])

  const send = useCallback(async (overrideText) => {
    const text = (overrideText ?? input).trim()
    if (!text || loading) return

    setInput('')
    setLoading(true)
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    const userTs = new Date()

    // Snapshot history before adding new messages
    const history = messages
      .filter(m => m.content && m.role)
      .map(m => ({ role: m.role, content: m.content }))

    // Add user bubble
    setMessages(prev => [...prev,
      { role: 'user', content: text, steps: [], streaming: false, timestamp: userTs },
    ])

    // Add empty assistant placeholder
    setMessages(prev => [...prev,
      { role: 'assistant', content: '', steps: [], streaming: true, timestamp: null },
    ])

    const steps = []
    let answered = false

    try {
      for await (const event of fetchStream(text, history)) {
        if (event.type === 'thinking' || event.type === 'tool_call' || event.type === 'tool_result' || event.type === 'agent_start') {
          steps.push(event)
          setMessages(prev => {
            const next = [...prev]
            const last = { ...next[next.length - 1], steps: [...steps] }
            next[next.length - 1] = last
            return next
          })
        } else if (event.type === 'answer') {
          answered = true
          setMessages(prev => {
            const next = [...prev]
            next[next.length - 1] = {
              ...next[next.length - 1],
              content: event.content,
              steps: [...steps],
              streaming: false,
              timestamp: new Date(),
            }
            return next
          })
        } else if (event.type === 'error') {
          setMessages(prev => {
            const next = [...prev]
            next[next.length - 1] = {
              ...next[next.length - 1],
              content: `Error: ${event.content}`,
              steps: [...steps],
              streaming: false,
              timestamp: new Date(),
              error: true,
            }
            return next
          })
          answered = true
        }
      }

      // Stream ended without an answer event (agent produced nothing after tools)
      if (!answered) {
        setMessages(prev => {
          const next = [...prev]
          const last = next[next.length - 1]
          if (last.streaming) {
            next[next.length - 1] = {
              ...last,
              content: last.content || '(No response received — the agent may still be processing.)',
              streaming: false,
              timestamp: new Date(),
            }
          }
          return next
        })
      }
    } catch (err) {
      setMessages(prev => {
        const next = [...prev]
        next[next.length - 1] = {
          ...next[next.length - 1],
          content: `Connection error: ${err.message}`,
          steps: [...steps],
          streaming: false,
          timestamp: new Date(),
          error: true,
        }
        return next
      })
    }

    setLoading(false)
  }, [input, loading, messages])

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const clearHistory = () => {
    setMessages([
      {
        role: 'assistant',
        content: [
          'Fresh session started. I still have live access to the full network:',
          '  • 20,000+ shipments · Q4 2024 data · 30 active routes',
          '',
          'What do you want to dig into?',
        ].join('\n'),
        steps: [],
        streaming: false,
        timestamp: new Date(),
      },
    ])
  }

  return (
    <div className="flex flex-col h-full" style={{ background: '#080808' }}>

      {/* ── Message list ─────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto py-6 flex flex-col gap-5"
        style={{ paddingLeft: '1.5rem', paddingRight: '1.5rem' }}>

        {messages.map((msg, i) =>
          msg.role === 'user'
            ? <UserBubble key={i} content={msg.content} timestamp={msg.timestamp} />
            : <AgentBubble key={i} msg={msg} />
        )}

        {/* Suggestion chips appear only before first real exchange */}
        {isFirstMessage && (
          <SuggestionChips onSelect={(t) => send(t)} />
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Input area ───────────────────────────────────────────────────── */}
      <div style={{ borderTop: `1px solid ${BORDER}`, background: '#0d0d0d' }}
        className="px-5 py-4 shrink-0">

        {/* Toolbar */}
        <div className="flex items-center justify-between mb-2">
          <span style={{ color: '#333' }} className="text-[10px] uppercase tracking-widest">
            Supply Chain Analyst
          </span>
          <button onClick={clearHistory}
            style={{
              color: '#6b7280',
              border: '1px solid #242424',
              borderRadius: 8,
              padding: '3px 10px',
              fontSize: 11,
              background: 'transparent',
              transition: 'all 0.15s',
            }}
            className="flex items-center gap-1.5 hover:text-gray-300 hover:border-[#3a3a3a]">
            <RotateCcw size={10}/> Start Over
          </button>
        </div>

        {/* Textarea + Send */}
        <div style={{
          border: `1px solid ${loading ? RED + '60' : BORDER}`,
          background: '#111',
          borderRadius: 14,
          transition: 'border-color 0.2s',
        }}
          className="flex items-end overflow-hidden">

          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about costs, routes, bottlenecks, or optimization…"
            disabled={loading}
            rows={1}
            style={{
              background: 'transparent',
              color: '#f5f5f5',
              resize: 'none',
              outline: 'none',
              caretColor: RED,
              lineHeight: 1.6,
              fontSize: 13,
              overflowY: 'hidden',
            }}
            className="flex-1 px-4 py-3 placeholder-gray-700 disabled:opacity-40"
          />

          <button
            onClick={() => send()}
            disabled={loading || !input.trim()}
            style={{
              background: (loading || !input.trim()) ? 'transparent' : RED,
              margin: 8,
              width: 34,
              height: 34,
              borderRadius: 9,
              flexShrink: 0,
              transition: 'all 0.15s',
              border: `1px solid ${(loading || !input.trim()) ? BORDER : 'transparent'}`,
            }}
            className="flex items-center justify-center disabled:opacity-30">
            {loading
              ? <Loader2 size={15} color={RED} className="animate-spin" />
              : <Send size={15} color={input.trim() ? 'white' : DIM} />
            }
          </button>
        </div>

        {/* Footer hint */}
        <p style={{ color: '#2d2d2d' }} className="text-[10px] mt-2 text-center tracking-wide">
          gpt-5.2 reasoning · XGBoost ML · PuLP LP · SQLite · Enter to send
        </p>
      </div>
    </div>
  )
}
