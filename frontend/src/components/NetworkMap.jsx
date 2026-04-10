/**
 * NetworkMap — Schematic supply chain diagram.
 *
 * NOT a geo-projection. Nodes are hand-placed in a clean left→right
 * flow layout: Suppliers (Asia / Europe / Americas) → US DCs.
 *
 * Features:
 *  • Bezier arc routes, one arc per mode so lanes don't overlap
 *  • Arc thickness ∝ flow volume, color & dash pattern by mode
 *  • Hover tooltip on routes (route id, mode, cost, transit, capacity)
 *  • Click node → detail panel below the canvas
 *  • Region zone labels + dotted region backgrounds
 *  • Legend with mode line samples
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Loader2, X, Package, Ship, Truck, Train, Plane,
  MapPin, Layers, AlertTriangle,
} from 'lucide-react'
import { getNetwork } from '../api/client.js'

// ── Tokens ─────────────────────────────────────────────────────────────────────
const RED    = '#e82127'
const BORDER = '#2a2a2a'
const DIM    = '#8b95a1'

const MODE = {
  ocean: { color: '#3b82f6', dash: '8 4',  label: 'Ocean',  Icon: Ship  },
  truck: { color: '#f59e0b', dash: 'none', label: 'Truck',  Icon: Truck },
  rail:  { color: '#10b981', dash: '3 3',  label: 'Rail',   Icon: Train },
  air:   { color: '#8b5cf6', dash: '10 5', label: 'Air',    Icon: Plane },
}

// ── Schematic node positions (SVG canvas 860 × 400) ────────────────────────────
// Columns:  Asia ≈ 70-110  |  Europe ≈ 195  |  Mexico ≈ 375  |  Detroit ≈ 485  |  US DCs ≈ 650-760
const NODE_POS = {
  // Suppliers
  'SUP-SH': { x: 75,  y: 125 },   // Shanghai
  'SUP-SZ': { x: 75,  y: 210 },   // Shenzhen
  'SUP-MU': { x: 195, y: 80  },   // Munich
  'SUP-MO': { x: 375, y: 295 },   // Monterrey
  'SUP-DE': { x: 485, y: 155 },   // Detroit
  // DCs
  'DC-FR':  { x: 655, y: 110 },   // Fremont CA
  'DC-LA':  { x: 660, y: 175 },   // Lathrop CA
  'DC-AU':  { x: 710, y: 265 },   // Austin TX
  'DC-ME':  { x: 760, y: 200 },   // Memphis TN
}

// Vertical arc offset per mode — ensures same-lane routes don't overlap
const MODE_ARC_OFFSET = {
  ocean: -90,
  air:   -45,
  rail:  +30,
  truck: -15,
}

// ── Region zones (visual grouping backgrounds) ─────────────────────────────────
const REGIONS = [
  { label: 'ASIA',    x: 28,  y: 28, w: 120, h: 235, color: '#3b82f6' },
  { label: 'EUROPE',  x: 158, y: 28, w: 80,  h: 100, color: '#8b5cf6' },
  { label: 'MEXICO',  x: 340, y: 245, w: 80, h: 80,  color: '#f59e0b' },
  { label: 'US',      x: 440, y: 28, w: 60,  h: 160, color: '#10b981' },
  { label: 'US DCs',  x: 620, y: 60, w: 180, h: 255, color: '#10b981' },
]

// ── Bezier path ────────────────────────────────────────────────────────────────
function arcPath(x1, y1, x2, y2, yOffset) {
  const cx = (x1 + x2) / 2
  const cy = (y1 + y2) / 2 + yOffset
  return `M ${x1},${y1} Q ${cx},${cy} ${x2},${y2}`
}

// ── Tooltip ────────────────────────────────────────────────────────────────────
function Tooltip({ edge, srcNode, tgtNode, mousePos, svgRect }) {
  if (!edge || !mousePos || !svgRect) return null

  const m = MODE[edge.mode] || MODE.truck
  const left = mousePos.x - svgRect.left + 12
  const top  = mousePos.y - svgRect.top  - 60

  return (
    <div
      style={{
        position: 'absolute',
        left: Math.min(left, svgRect.width - 220),
        top:  Math.max(top, 8),
        background: '#161616',
        border: `1px solid ${BORDER}`,
        borderLeft: `3px solid ${m.color}`,
        borderRadius: 10,
        padding: '10px 14px',
        pointerEvents: 'none',
        zIndex: 50,
        minWidth: 200,
        boxShadow: '0 8px 32px #00000090',
      }}>
      <div className="flex items-center gap-2 mb-2">
        <m.Icon size={12} style={{ color: m.color }} />
        <span style={{ color: m.color }} className="text-xs font-semibold uppercase">
          {m.label}
        </span>
        <span style={{ color: DIM }} className="text-[10px] ml-auto">{edge.id}</span>
      </div>
      <div className="flex flex-col gap-1 text-[11px]">
        <div className="flex justify-between gap-6">
          <span style={{ color: DIM }}>Route</span>
          <span style={{ color: '#e5e7eb' }}>{srcNode?.city} → {tgtNode?.city}</span>
        </div>
        <div className="flex justify-between gap-6">
          <span style={{ color: DIM }}>Base cost</span>
          <span style={{ color: '#34d399' }} className="font-mono">${edge.base_cost_per_unit}/unit</span>
        </div>
        <div className="flex justify-between gap-6">
          <span style={{ color: DIM }}>Transit</span>
          <span style={{ color: '#e5e7eb' }}>{edge.transit_days}d</span>
        </div>
        <div className="flex justify-between gap-6">
          <span style={{ color: DIM }}>Distance</span>
          <span style={{ color: '#e5e7eb' }}>{edge.distance_miles?.toLocaleString()} mi</span>
        </div>
        <div className="flex justify-between gap-6">
          <span style={{ color: DIM }}>Daily cap</span>
          <span style={{ color: '#e5e7eb' }}>{edge.capacity_units_per_day} units</span>
        </div>
        {edge.flow_volume && (
          <div className="flex justify-between gap-6">
            <span style={{ color: DIM }}>Avg flow</span>
            <span style={{ color: '#e5e7eb' }}>{edge.flow_volume.toFixed(0)} units</span>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Node detail panel ──────────────────────────────────────────────────────────
function NodeDetail({ node, edges, nodeMap, onClose }) {
  if (!node) return null

  const isSupplier = node.type === 'supplier'
  const fill = isSupplier ? '#3b82f6' : '#10b981'
  const connected = edges.filter(e =>
    e.source === node.id || e.target === node.id
  )

  return (
    <div style={{ background: '#111', border: `1px solid ${BORDER}`, borderTop: `2px solid ${fill}` }}
      className="rounded-xl p-5 fade-in">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div style={{ background: fill + '20', border: `1px solid ${fill}40`, borderRadius: 8, padding: 8 }}>
            <MapPin size={14} style={{ color: fill }} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-100">{node.name}</h3>
            <p style={{ color: DIM }} className="text-xs mt-0.5">
              {node.city}, {node.country} · {isSupplier ? 'Supplier' : 'Distribution Center'}
            </p>
          </div>
        </div>
        <button onClick={onClose}
          style={{ color: DIM }}
          className="hover:text-white transition-colors">
          <X size={14} />
        </button>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div style={{ background: '#161616', borderRadius: 8 }} className="p-3">
          <p style={{ color: DIM }} className="text-[10px] uppercase tracking-wider mb-1">Capacity</p>
          <p className="text-sm font-semibold">{node.capacity.toLocaleString()}</p>
          <p style={{ color: DIM }} className="text-[10px]">units/day</p>
        </div>
        <div style={{ background: '#161616', borderRadius: 8 }} className="p-3">
          <p style={{ color: DIM }} className="text-[10px] uppercase tracking-wider mb-1">Routes</p>
          <p className="text-sm font-semibold">{connected.length}</p>
          <p style={{ color: DIM }} className="text-[10px]">active lanes</p>
        </div>
        <div style={{ background: '#161616', borderRadius: 8 }} className="p-3">
          <p style={{ color: DIM }} className="text-[10px] uppercase tracking-wider mb-1">Modes</p>
          <p className="text-sm font-semibold">{[...new Set(connected.map(e => e.mode))].length}</p>
          <p style={{ color: DIM }} className="text-[10px]">transport types</p>
        </div>
      </div>

      {/* Connected routes */}
      <div>
        <p style={{ color: DIM }} className="text-[10px] uppercase tracking-widest mb-2 flex items-center gap-1.5">
          <Layers size={10}/> Connected Routes
        </p>
        <div className="flex flex-wrap gap-2">
          {connected.map(e => {
            const m = MODE[e.mode] || MODE.truck
            const other = e.source === node.id
              ? nodeMap[e.target]
              : nodeMap[e.source]
            return (
              <div key={e.id}
                style={{
                  background: m.color + '12',
                  border: `1px solid ${m.color}30`,
                  borderRadius: 8,
                }}
                className="px-3 py-2 flex items-center gap-2">
                <m.Icon size={11} style={{ color: m.color }} />
                <div>
                  <p style={{ color: '#d1d5db' }} className="text-[11px] font-medium">
                    {other?.city ?? other?.id}
                  </p>
                  <p style={{ color: DIM }} className="text-[10px]">
                    ${e.base_cost_per_unit}/unit · {e.transit_days}d
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main NetworkMap
// ═══════════════════════════════════════════════════════════════════════════════
export default function NetworkMap() {
  const [data,        setData]        = useState(null)
  const [loading,     setLoading]     = useState(true)
  const [error,       setError]       = useState(null)
  const [selected,    setSelected]    = useState(null)   // clicked node
  const [hoveredEdge, setHoveredEdge] = useState(null)   // hovered route
  const [mousePos,    setMousePos]    = useState(null)
  const [modeFilter,  setModeFilter]  = useState('all')  // legend filter
  const svgRef = useRef(null)

  const W = 860, H = 400

  useEffect(() => {
    getNetwork()
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  const handleMouseMove = useCallback((e) => {
    setMousePos({ x: e.clientX, y: e.clientY })
  }, [])

  if (loading) return (
    <div className="flex-1 flex items-center justify-center">
      <Loader2 size={28} style={{ color: RED }} className="animate-spin" />
    </div>
  )

  if (error || !data) return (
    <div className="flex-1 flex items-center justify-center gap-3 text-sm" style={{ color: DIM }}>
      <AlertTriangle size={16} color={RED} />
      {error || 'Failed to load network data'}
    </div>
  )

  const nodeMap = Object.fromEntries(data.nodes.map(n => [n.id, n]))

  // Flow volume range for stroke scaling
  const flows     = data.edges.map(e => e.flow_volume || 50)
  const maxFlow   = Math.max(...flows)
  const minFlow   = Math.min(...flows)
  const flowRange = maxFlow - minFlow || 1

  const strokeWidth = (flow) =>
    1.0 + ((( flow || 50) - minFlow) / flowRange) * 2.5

  // Filter edges by selected mode
  const visibleEdges = modeFilter === 'all'
    ? data.edges
    : data.edges.filter(e => e.mode === modeFilter)

  // Highlight edges connected to selected node
  const highlightIds = selected
    ? new Set(data.edges
        .filter(e => e.source === selected.id || e.target === selected.id)
        .map(e => e.id))
    : null

  const svgRect = svgRef.current?.getBoundingClientRect() ?? null

  return (
    <div className="flex-1 overflow-y-auto" style={{ background: '#080808' }}
      onMouseMove={handleMouseMove}>
      <div className="max-w-5xl mx-auto p-5 flex flex-col gap-4">

        {/* ── Toolbar ──────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold text-gray-100">Inbound Network Schematic</h1>
            <p style={{ color: DIM }} className="text-xs mt-0.5">
              {data.nodes.filter(n=>n.type==='supplier').length} suppliers ·{' '}
              {data.nodes.filter(n=>n.type==='dc').length} DCs ·{' '}
              {data.edges.length} active routes
            </p>
          </div>

          {/* Mode filter */}
          <div className="flex items-center gap-1.5">
            {['all', ...Object.keys(MODE)].map(m => {
              const meta = MODE[m]
              const active = modeFilter === m
              return (
                <button key={m}
                  onClick={() => setModeFilter(m)}
                  style={{
                    background: active ? (meta?.color ?? RED) + '25' : 'transparent',
                    color:      active ? (meta?.color ?? '#f5f5f5') : DIM,
                    border:     `1px solid ${active ? (meta?.color ?? RED) + '50' : BORDER}`,
                  }}
                  className="text-[10px] px-2.5 py-1 rounded-full uppercase transition-all hover:border-[#444]">
                  {m}
                </button>
              )
            })}
          </div>
        </div>

        {/* ── SVG canvas ───────────────────────────────────────────────── */}
        <div style={{ background: '#0a0d12', border: `1px solid ${BORDER}`, position: 'relative' }}
          className="rounded-xl overflow-hidden">

          {/* Floating tooltip */}
          {hoveredEdge && (
            <Tooltip
              edge={hoveredEdge}
              srcNode={nodeMap[hoveredEdge.source]}
              tgtNode={nodeMap[hoveredEdge.target]}
              mousePos={mousePos}
              svgRect={svgRect}
            />
          )}

          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            className="w-full"
            style={{ display: 'block', maxHeight: 420 }}>

            {/* ── Background region zones ─────────────────────────────── */}
            {REGIONS.map(r => (
              <g key={r.label}>
                <rect
                  x={r.x} y={r.y} width={r.w} height={r.h}
                  rx={8}
                  fill={r.color}
                  opacity={0.03}
                  stroke={r.color}
                  strokeWidth={0.5}
                  strokeOpacity={0.12}
                />
                <text
                  x={r.x + r.w / 2} y={r.y + 14}
                  textAnchor="middle"
                  fill={r.color}
                  fontSize={7}
                  fontFamily="system-ui"
                  opacity={0.4}
                  letterSpacing={1.5}>
                  {r.label}
                </text>
              </g>
            ))}

            {/* ── Subtle horizontal flow guide ────────────────────────── */}
            <line x1={30} y1={H/2} x2={W-30} y2={H/2}
              stroke="#ffffff" strokeWidth={0.3} opacity={0.03} />

            {/* ── Route arcs ───────────────────────────────────────────── */}
            {visibleEdges.map(edge => {
              const srcPos = NODE_POS[edge.source]
              const tgtPos = NODE_POS[edge.target]
              if (!srcPos || !tgtPos) return null

              const m        = MODE[edge.mode] || MODE.truck
              const sw       = strokeWidth(edge.flow_volume)
              const yOffset  = MODE_ARC_OFFSET[edge.mode] ?? -30
              const path     = arcPath(srcPos.x, srcPos.y, tgtPos.x, tgtPos.y, yOffset)
              const isHovered = hoveredEdge?.id === edge.id
              const isDimmed  = highlightIds && !highlightIds.has(edge.id)

              return (
                <g key={edge.id}>
                  {/* Invisible wide hit zone for easy hover */}
                  <path
                    d={path}
                    fill="none"
                    stroke="transparent"
                    strokeWidth={14}
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={() => setHoveredEdge(edge)}
                    onMouseLeave={() => setHoveredEdge(null)}
                  />
                  {/* Visible route arc */}
                  <path
                    d={path}
                    fill="none"
                    stroke={m.color}
                    strokeWidth={isHovered ? sw + 1.5 : sw}
                    strokeDasharray={m.dash === 'none' ? undefined : m.dash}
                    opacity={isDimmed ? 0.1 : isHovered ? 0.95 : 0.45}
                    style={{
                      transition: 'opacity 0.15s, stroke-width 0.1s',
                      filter: isHovered ? `drop-shadow(0 0 4px ${m.color}80)` : 'none',
                    }}
                    pointerEvents="none"
                  />
                  {/* Arrow at destination */}
                  {isHovered && (() => {
                    // Approximate arrow at 95% along the bezier
                    const t = 0.95
                    const mx = (srcPos.x + tgtPos.x) / 2
                    const my = (srcPos.y + tgtPos.y) / 2 + yOffset
                    const bx = (1-t)*(1-t)*srcPos.x + 2*(1-t)*t*mx + t*t*tgtPos.x
                    const by = (1-t)*(1-t)*srcPos.y + 2*(1-t)*t*my + t*t*tgtPos.y
                    return (
                      <circle cx={bx} cy={by} r={3}
                        fill={m.color} opacity={0.9} pointerEvents="none" />
                    )
                  })()}
                </g>
              )
            })}

            {/* ── Nodes ────────────────────────────────────────────────── */}
            {data.nodes.map(node => {
              const pos = NODE_POS[node.id]
              if (!pos) return null

              const isSupplier = node.type === 'supplier'
              const isSelected = selected?.id === node.id
              const fill = isSupplier ? '#3b82f6' : '#10b981'
              const r    = isSupplier ? 9 : 10

              return (
                <g key={node.id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => setSelected(isSelected ? null : node)}>

                  {/* Selection ring */}
                  {isSelected && (
                    <circle cx={pos.x} cy={pos.y} r={r + 7}
                      fill="none" stroke={fill} strokeWidth={1.5}
                      opacity={0.5} />
                  )}

                  {/* Glow */}
                  <circle cx={pos.x} cy={pos.y} r={r + 4}
                    fill={fill}
                    opacity={isSelected ? 0.15 : 0.06}
                    style={{ transition: 'opacity 0.2s' }}
                  />

                  {/* Main node */}
                  {isSupplier ? (
                    <circle cx={pos.x} cy={pos.y} r={r}
                      fill={fill}
                      stroke={isSelected ? 'white' : fill}
                      strokeWidth={isSelected ? 1.5 : 0.5}
                      strokeOpacity={0.6}
                      style={{
                        filter: isSelected ? `drop-shadow(0 0 6px ${fill}90)` : 'none',
                        transition: 'all 0.15s',
                      }}
                    />
                  ) : (
                    // DC = rounded square
                    <rect
                      x={pos.x - r} y={pos.y - r}
                      width={r * 2} height={r * 2}
                      rx={3}
                      fill={fill}
                      stroke={isSelected ? 'white' : fill}
                      strokeWidth={isSelected ? 1.5 : 0.5}
                      strokeOpacity={0.6}
                      style={{
                        filter: isSelected ? `drop-shadow(0 0 6px ${fill}90)` : 'none',
                        transition: 'all 0.15s',
                      }}
                    />
                  )}

                  {/* City label */}
                  <text
                    x={isSupplier ? pos.x + r + 4 : pos.x + r + 4}
                    y={pos.y + 4}
                    fill={isSelected ? '#f5f5f5' : '#94a3b8'}
                    fontSize={isSelected ? 10 : 8.5}
                    fontFamily="system-ui"
                    fontWeight={isSelected ? 600 : 400}
                    style={{ transition: 'all 0.15s', userSelect: 'none' }}>
                    {node.city}
                  </text>
                </g>
              )
            })}
          </svg>
        </div>

        {/* ── Legend ───────────────────────────────────────────────────── */}
        <div className="flex items-center flex-wrap gap-5">
          {/* Node types */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <svg width={14} height={14}>
                <circle cx={7} cy={7} r={6} fill="#3b82f6" opacity={0.85} />
              </svg>
              <span style={{ color: '#b8c0cc' }} className="text-xs">Supplier</span>
            </div>
            <div className="flex items-center gap-1.5">
              <svg width={14} height={14}>
                <rect x={1} y={1} width={12} height={12} rx={2} fill="#10b981" opacity={0.85} />
              </svg>
              <span style={{ color: '#b8c0cc' }} className="text-xs">Distribution Center</span>
            </div>
          </div>

          {/* Divider */}
          <div style={{ background: BORDER, width: 1, height: 16 }} />

          {/* Route modes */}
          {Object.entries(MODE).map(([key, m]) => (
            <div key={key} className="flex items-center gap-1.5">
              <svg width={24} height={10}>
                <line
                  x1={0} y1={5} x2={24} y2={5}
                  stroke={m.color}
                  strokeWidth={2}
                  strokeDasharray={m.dash === 'none' ? undefined : m.dash}
                />
              </svg>
              <span style={{ color: '#b8c0cc' }} className="text-xs">{m.label}</span>
            </div>
          ))}

          <p style={{ color: '#2a2a2a' }} className="ml-auto text-[10px] uppercase tracking-widest">
            Arc thickness = flow volume
          </p>
        </div>

        {/* ── Node detail panel ─────────────────────────────────────────── */}
        {selected && (
          <NodeDetail
            node={selected}
            edges={data.edges}
            nodeMap={nodeMap}
            onClose={() => setSelected(null)}
          />
        )}

      </div>
    </div>
  )
}
