/**
 * Dashboard — Live supply chain performance overview.
 *
 * Layout:
 *   Row 1 — 4 KPI cards  (cost · transit · service level · utilization)
 *   Row 2 — Cost by mode bar chart  +  Cost by supplier horizontal bar chart
 *   Row 3 — Full top-routes table  (7 columns, sortable mode filter)
 *
 * Data:  /api/dashboard/kpis  +  /api/dashboard/cost-breakdown  +  /api/dashboard/top-routes
 */

import { useState, useEffect, useCallback } from 'react'
import {
  DollarSign, Clock, ShieldCheck, Activity,
  TrendingUp, TrendingDown, Minus,
  RefreshCw, Loader2, AlertTriangle,
  Package, Truck, Ship, Train, Plane,
  ArrowUpDown,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, LabelList,
  ReferenceLine,
} from 'recharts'
import { getKPIs, getCostBreakdown, getTopRoutes } from '../api/client.js'

// ── Tokens ─────────────────────────────────────────────────────────────────────
const RED    = '#e82127'
const BORDER = '#2a2a2a'
const DIM    = '#8b95a1'

const MODE_COLOR = { ocean:'#3b82f6', truck:'#f59e0b', rail:'#10b981', air:'#8b5cf6' }
const MODE_ICON  = {
  ocean: Ship,
  truck: Truck,
  rail:  Train,
  air:   Plane,
}

// ── Formatters ─────────────────────────────────────────────────────────────────
const fmtMoney = (n) => {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000)     return `$${(n / 1_000).toFixed(1)}K`
  return `$${n.toFixed(0)}`
}

const fmtPct = (n) => `${Number(n).toFixed(1)}%`

// ── Threshold colour helpers ───────────────────────────────────────────────────
function svcColor(pct)  { return pct >= 90 ? '#10b981' : pct >= 80 ? '#f59e0b' : RED }
function utilColor(pct) { return pct <= 70 ? '#10b981' : pct <= 85 ? '#f59e0b' : RED }

// ═══════════════════════════════════════════════════════════════════════════════
// KPI Cards
// ═══════════════════════════════════════════════════════════════════════════════

const KPI_DEFS = [
  {
    key:   'total_cost_quarter',
    label: 'Total Inbound Cost',
    sub:   'Last 90 days',
    Icon:  DollarSign,
    fmt:   fmtMoney,
    iconBg: '#e8212715',
    iconColor: RED,
    valueColor: () => '#f5f5f5',
    trend: 'flat',
  },
  {
    key:   'avg_transit_days',
    label: 'Avg Transit Time',
    sub:   'All modes · days',
    Icon:  Clock,
    fmt:   (v) => `${Number(v).toFixed(1)}d`,
    iconBg: '#3b82f615',
    iconColor: '#3b82f6',
    valueColor: () => '#f5f5f5',
    trend: 'down',
  },
  {
    key:   'service_level_pct',
    label: 'Service Level',
    sub:   'On-time delivery',
    Icon:  ShieldCheck,
    fmt:   fmtPct,
    iconBg: '#10b98115',
    iconColor: '#10b981',
    valueColor: svcColor,
    trend: 'up',
  },
  {
    key:   'network_utilization_pct',
    label: 'Network Utilization',
    sub:   'Avg route capacity used',
    Icon:  Activity,
    fmt:   fmtPct,
    iconBg: '#8b5cf615',
    iconColor: '#8b5cf6',
    valueColor: utilColor,
    trend: 'flat',
  },
]

function TrendBadge({ trend, pctChange }) {
  if (!pctChange) {
    const Icon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus
    const color = trend === 'up' ? '#10b981' : trend === 'down' ? '#f59e0b' : DIM
    return <Icon size={14} color={color} />
  }
  const positive = pctChange > 0
  const Icon = positive ? TrendingUp : TrendingDown
  const color = positive ? '#10b981' : RED
  return (
    <span style={{ color, background: color + '15' }}
      className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full font-medium">
      <Icon size={10}/>{Math.abs(pctChange).toFixed(1)}%
    </span>
  )
}

function KPICard({ def, value }) {
  const { label, sub, Icon, fmt, iconBg, iconColor, valueColor, trend } = def
  const display = value != null ? fmt(value) : '—'
  const vColor  = value != null ? valueColor(value) : DIM

  return (
    <div style={{ background: '#111', border: `1px solid ${BORDER}` }}
      className="rounded-xl p-5 flex flex-col gap-3 hover:border-[#333] transition-colors fade-in">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div style={{ background: iconBg, borderRadius: 8, padding: 7 }}>
          <Icon size={15} style={{ color: iconColor }} strokeWidth={1.8} />
        </div>
        <TrendBadge trend={trend} />
      </div>

      {/* Value */}
      <div>
        <p style={{ color: vColor }} className="text-2xl font-semibold tracking-tight leading-none">
          {display}
        </p>
        <p style={{ color: DIM }} className="text-xs mt-1.5">{label}</p>
      </div>

      {/* Sub-label */}
      <p style={{ color: '#3d3d3d', borderTop: `1px solid #1a1a1a` }}
        className="text-[10px] pt-2.5 uppercase tracking-widest">
        {sub}
      </p>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Custom tooltip for charts
// ═══════════════════════════════════════════════════════════════════════════════

function DarkTooltip({ active, payload, label, prefix = '$', suffix = 'K' }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: '#161616',
      border: `1px solid ${BORDER}`,
      borderRadius: 10,
      padding: '10px 14px',
      boxShadow: '0 8px 32px #00000080',
    }}>
      <p style={{ color: '#b8c0cc', fontSize: 11, marginBottom: 4 }}>{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color || '#f5f5f5', fontSize: 13, fontWeight: 600 }}>
          {prefix}{p.value.toLocaleString()}{suffix}
        </p>
      ))}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Cost by Mode chart
// ═══════════════════════════════════════════════════════════════════════════════

function ModeBarChart({ data }) {
  if (!data?.by_mode?.length) return null

  const items = data.by_mode.map(d => ({
    name:  d.category.charAt(0).toUpperCase() + d.category.slice(1),
    mode:  d.category,
    costK: Math.round(d.cost / 1000),
    cpuDollars: d.avg_cost_per_unit.toFixed(2),
    count: d.shipment_count,
  }))

  return (
    <div style={{ background: '#111', border: `1px solid ${BORDER}` }}
      className="rounded-xl p-5 flex flex-col">

      <div className="flex items-center justify-between mb-5">
        <div>
          <p className="text-sm font-medium text-gray-200">Cost by Transport Mode</p>
          <p style={{ color: DIM }} className="text-xs mt-0.5">Last 90 days · $K</p>
        </div>
        {/* Legend pills */}
        <div className="flex gap-2">
          {items.map(d => (
            <span key={d.mode}
              style={{ background: MODE_COLOR[d.mode]+'18', color: MODE_COLOR[d.mode], border:`1px solid ${MODE_COLOR[d.mode]}30` }}
              className="text-[10px] px-2 py-0.5 rounded-full uppercase">
              {d.mode}
            </span>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={items} barCategoryGap="35%" margin={{ top: 8, right: 4, bottom: 0, left: -10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1c1c1c" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: '#9aabb8', fontSize: 11 }}
            axisLine={false} tickLine={false}
          />
          <YAxis
            tick={{ fill: '#9aabb8', fontSize: 11 }}
            axisLine={false} tickLine={false}
            unit="K"
          />
          <Tooltip content={<DarkTooltip />} cursor={{ fill: '#ffffff08' }} />
          <Bar dataKey="costK" radius={[5, 5, 0, 0]} maxBarSize={60}>
            {items.map((entry, i) => (
              <Cell key={i} fill={MODE_COLOR[entry.mode] || RED} />
            ))}
            <LabelList
              dataKey="costK"
              position="top"
              formatter={(v) => `$${v}K`}
              style={{ fill: '#4b5563', fontSize: 10 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Per-mode stats row */}
      <div className="grid grid-cols-4 gap-2 mt-4">
        {items.map(d => {
          const MIcon = MODE_ICON[d.mode] || Package
          return (
            <div key={d.mode}
              style={{ background: MODE_COLOR[d.mode]+'0d', border:`1px solid ${MODE_COLOR[d.mode]}20`, borderRadius: 8 }}
              className="p-2.5 flex flex-col gap-1">
              <div className="flex items-center gap-1.5">
                <MIcon size={11} style={{ color: MODE_COLOR[d.mode] }} />
                <span style={{ color: MODE_COLOR[d.mode] }} className="text-[10px] uppercase font-medium">
                  {d.mode}
                </span>
              </div>
              <p style={{ color: '#e5e7eb' }} className="text-sm font-semibold">${d.costK}K</p>
              <p style={{ color: DIM }} className="text-[10px]">${d.cpuDollars}/unit avg</p>
              <p style={{ color: '#3d3d3d' }} className="text-[10px]">{d.count} shipments</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Cost by Supplier chart (horizontal)
// ═══════════════════════════════════════════════════════════════════════════════

function SupplierBarChart({ data }) {
  if (!data?.by_supplier?.length) return null

  const items = [...data.by_supplier]
    .sort((a, b) => b.cost - a.cost)
    .map(d => ({
      name:  d.category.split(' ')[0],   // first word (e.g. "Shanghai")
      full:  d.category,
      costK: Math.round(d.cost / 1000),
      cpu:   d.avg_cost_per_unit.toFixed(2),
      count: d.shipment_count,
    }))

  const maxCost = Math.max(...items.map(d => d.costK))

  return (
    <div style={{ background: '#111', border: `1px solid ${BORDER}` }}
      className="rounded-xl p-5 flex flex-col">

      <div className="mb-5">
        <p className="text-sm font-medium text-gray-200">Cost by Supplier</p>
        <p style={{ color: DIM }} className="text-xs mt-0.5">Last 90 days · $K</p>
      </div>

      <ResponsiveContainer width="100%" height={200}>
        <BarChart
          data={items}
          layout="vertical"
          barCategoryGap="30%"
          margin={{ top: 0, right: 40, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1c1c1c" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fill: '#9aabb8', fontSize: 11 }}
            axisLine={false} tickLine={false}
            unit="K"
          />
          <YAxis
            dataKey="name"
            type="category"
            tick={{ fill: '#9aabb8', fontSize: 11 }}
            axisLine={false} tickLine={false}
            width={62}
          />
          <Tooltip content={<DarkTooltip />} cursor={{ fill: '#ffffff06' }} />
          <Bar dataKey="costK" radius={[0, 5, 5, 0]} maxBarSize={22} fill={RED}>
            {items.map((entry, i) => {
              const intensity = entry.costK / maxCost
              const r = Math.round(232 * intensity)
              const g = Math.round(33  * intensity)
              const b = Math.round(39  * intensity)
              return <Cell key={i} fill={`rgb(${r},${g},${b})`} />
            })}
            <LabelList
              dataKey="costK"
              position="right"
              formatter={(v) => `$${v}K`}
              style={{ fill: '#4b5563', fontSize: 10 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Cost-per-unit mini table */}
      <div style={{ borderTop: `1px solid ${BORDER}` }} className="mt-4 pt-3">
        <p style={{ color: DIM }} className="text-[10px] uppercase tracking-widest mb-2">
          Avg Cost / Unit
        </p>
        <div className="flex flex-col gap-1.5">
          {items.map(d => (
            <div key={d.name} className="flex items-center gap-2">
              <span style={{ color: '#9aabb8' }} className="text-[11px] w-20 truncate">{d.full}</span>
              <div className="flex-1 h-1 rounded-full" style={{ background: '#1e1e1e' }}>
                <div style={{
                  width: `${(d.cpu / Math.max(...items.map(x => +x.cpu))) * 100}%`,
                  background: RED,
                  height: '100%',
                  borderRadius: 9999,
                }} />
              </div>
              <span style={{ color: '#d1d5db' }} className="text-[11px] font-mono w-14 text-right">
                ${d.cpu}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Route table
// ═══════════════════════════════════════════════════════════════════════════════

const COLUMNS = [
  { key: 'origin',       label: 'Origin',       align: 'left'  },
  { key: 'destination',  label: 'Destination',  align: 'left'  },
  { key: 'mode',         label: 'Mode',         align: 'left'  },
  { key: 'total_cost',   label: 'Total Cost',   align: 'right' },
  { key: 'avg_transit',  label: 'Transit Days', align: 'right' },
  { key: 'shipments',    label: 'Shipments',    align: 'right' },
  { key: 'on_time',      label: 'On-Time',      align: 'right' },
]

function OnTimeBadge({ pct }) {
  const color = pct >= 70 ? '#10b981' : pct >= 50 ? '#f59e0b' : RED
  const bg    = color + '18'
  return (
    <span style={{ color, background: bg, border: `1px solid ${color}30` }}
      className="text-[11px] font-medium px-2 py-0.5 rounded-full">
      {pct.toFixed(0)}%
    </span>
  )
}

function ModeBadge({ mode }) {
  const color = MODE_COLOR[mode] || DIM
  const MIcon = MODE_ICON[mode] || Package
  return (
    <span style={{
      color, background: color + '18',
      border: `1px solid ${color}30`,
    }}
      className="text-[10px] font-medium px-2 py-1 rounded-md flex items-center gap-1 w-fit uppercase">
      <MIcon size={10} />
      {mode}
    </span>
  )
}

function RouteTable({ routes, onSortMode }) {
  const [modeFilter, setModeFilter] = useState('all')

  if (!routes?.length) return null

  const filtered = modeFilter === 'all'
    ? routes
    : routes.filter(r => r.mode === modeFilter)

  const modes = ['all', ...new Set(routes.map(r => r.mode))]

  return (
    <div style={{ background: '#111', border: `1px solid ${BORDER}` }}
      className="rounded-xl overflow-hidden">

      {/* Table header */}
      <div style={{ borderBottom: `1px solid ${BORDER}` }}
        className="px-5 py-3.5 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-gray-200">Top Routes by Cost</p>
          <p style={{ color: DIM }} className="text-xs mt-0.5">Last 90 days · sorted by total spend</p>
        </div>
        {/* Mode filter pills */}
        <div className="flex gap-1.5">
          {modes.map(m => (
            <button key={m}
              onClick={() => setModeFilter(m)}
              style={{
                background: modeFilter === m ? (MODE_COLOR[m] || RED) + '25' : 'transparent',
                color: modeFilter === m ? (MODE_COLOR[m] || '#f5f5f5') : DIM,
                border: `1px solid ${modeFilter === m ? (MODE_COLOR[m] || RED) + '50' : BORDER}`,
              }}
              className="text-[10px] px-2.5 py-1 rounded-full uppercase transition-all hover:border-[#444]">
              {m}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr style={{ borderBottom: `1px solid ${BORDER}` }}>
              {COLUMNS.map(col => (
                <th key={col.key}
                  style={{ color: DIM }}
                  className={`px-4 py-2.5 font-normal text-[11px] uppercase tracking-wider
                    ${col.align === 'right' ? 'text-right' : 'text-left'}`}>
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 10).map((r, i) => (
              <tr key={i}
                style={{ borderBottom: `1px solid #161616` }}
                className="group hover:bg-[#161616] transition-colors">

                {/* Origin */}
                <td className="px-4 py-3">
                  <div>
                    <p className="text-gray-200 font-medium">{r.origin.split(' ')[0]}</p>
                    <p style={{ color: DIM }} className="text-[10px] mt-0.5">
                      {r.origin.split(' ').slice(1).join(' ')}
                    </p>
                  </div>
                </td>

                {/* Destination */}
                <td className="px-4 py-3">
                  <div>
                    <p className="text-gray-200 font-medium">{r.destination.split(' ')[0]}</p>
                    <p style={{ color: DIM }} className="text-[10px] mt-0.5">
                      {r.destination.split(' ').slice(1).join(' ')}
                    </p>
                  </div>
                </td>

                {/* Mode */}
                <td className="px-4 py-3">
                  <ModeBadge mode={r.mode} />
                </td>

                {/* Total cost */}
                <td className="px-4 py-3 text-right">
                  <p style={{ color: '#e5e7eb' }} className="font-mono font-medium">
                    {fmtMoney(r.total_cost)}
                  </p>
                  <p style={{ color: DIM }} className="text-[10px] mt-0.5">
                    ${(r.total_cost / r.shipment_count / (r.units_avg || 80)).toFixed(2)}/unit est.
                  </p>
                </td>

                {/* Transit days */}
                <td className="px-4 py-3 text-right">
                  <p style={{ color: '#e5e7eb' }} className="font-mono">
                    {r.avg_transit_days.toFixed(1)}d
                  </p>
                </td>

                {/* Shipment count */}
                <td className="px-4 py-3 text-right">
                  <p style={{ color: '#b8c0cc' }} className="font-mono">
                    {r.shipment_count.toLocaleString()}
                  </p>
                </td>

                {/* On-time */}
                <td className="px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-2">
                    {/* Mini bar */}
                    <div className="w-12 h-1 rounded-full" style={{ background: '#1e1e1e' }}>
                      <div style={{
                        width: `${r.on_time_pct}%`,
                        background: r.on_time_pct >= 70 ? '#10b981' : r.on_time_pct >= 50 ? '#f59e0b' : RED,
                        height: '100%',
                        borderRadius: 9999,
                      }} />
                    </div>
                    <OnTimeBadge pct={r.on_time_pct} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      {filtered.length > 10 && (
        <div style={{ borderTop:`1px solid ${BORDER}` }}
          className="px-5 py-2.5 text-center">
          <p style={{ color: DIM }} className="text-[11px]">
            Showing 10 of {filtered.length} routes
          </p>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Error / empty states
// ═══════════════════════════════════════════════════════════════════════════════

function ErrorBanner({ message, onRetry }) {
  return (
    <div style={{ background: '#1a0808', border: `1px solid #7f1d1d` }}
      className="rounded-xl p-4 flex items-center gap-3">
      <AlertTriangle size={16} color={RED} />
      <p style={{ color: '#fca5a5' }} className="text-sm flex-1">{message}</p>
      {onRetry && (
        <button onClick={onRetry}
          style={{ color: RED, border: `1px solid #7f1d1d` }}
          className="text-xs px-3 py-1.5 rounded hover:bg-[#2a0a0a] transition-colors">
          Retry
        </button>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main Dashboard
// ═══════════════════════════════════════════════════════════════════════════════

export default function Dashboard() {
  const [kpis,      setKpis]      = useState(null)
  const [breakdown, setBreakdown] = useState(null)
  const [routes,    setRoutes]    = useState(null)
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)
  const [lastFetch, setLastFetch] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [k, b, r] = await Promise.all([
        getKPIs(),
        getCostBreakdown(),
        getTopRoutes(20),
      ])
      setKpis(k)
      setBreakdown(b)
      setRoutes(r)
      setLastFetch(new Date())
    } catch (e) {
      setError(e.message || 'Failed to load dashboard data. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="flex-1 overflow-y-auto" style={{ background: '#080808' }}>
      <div className="max-w-7xl mx-auto p-6 flex flex-col gap-6">

        {/* ── Toolbar ──────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold text-gray-100">
              Network Performance
            </h1>
            <p style={{ color: DIM }} className="text-xs mt-0.5">
              Last 90 days · live data from SQLite
            </p>
          </div>
          <div className="flex items-center gap-3">
            {lastFetch && (
              <p style={{ color: '#3d3d3d' }} className="text-[11px]">
                Updated {lastFetch.toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' })}
              </p>
            )}
            <button
              onClick={load}
              disabled={loading}
              style={{ border: `1px solid ${BORDER}`, color: DIM }}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg hover:text-white hover:border-[#444] transition-all disabled:opacity-40">
              <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
              {loading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
        </div>

        {/* ── Error ────────────────────────────────────────────────────── */}
        {error && <ErrorBanner message={error} onRetry={load} />}

        {/* ── KPI cards ────────────────────────────────────────────────── */}
        {loading && !kpis ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[0,1,2,3].map(i => (
              <div key={i}
                style={{ background: '#111', border: `1px solid ${BORDER}` }}
                className="rounded-xl p-5 h-32 animate-pulse" />
            ))}
          </div>
        ) : kpis && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {KPI_DEFS.map(def => (
              <KPICard
                key={def.key}
                def={def}
                value={kpis[def.key]}
              />
            ))}
          </div>
        )}

        {/* ── Charts row ───────────────────────────────────────────────── */}
        {loading && !breakdown ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {[0,1].map(i => (
              <div key={i}
                style={{ background: '#111', border: `1px solid ${BORDER}` }}
                className="rounded-xl p-5 h-72 animate-pulse" />
            ))}
          </div>
        ) : breakdown && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ModeBarChart data={breakdown} />
            <SupplierBarChart data={breakdown} />
          </div>
        )}

        {/* ── Route table ──────────────────────────────────────────────── */}
        {loading && !routes ? (
          <div style={{ background: '#111', border: `1px solid ${BORDER}` }}
            className="rounded-xl h-64 animate-pulse" />
        ) : routes && (
          <RouteTable routes={routes} />
        )}

        {/* ── Footer ───────────────────────────────────────────────────── */}
        <div className="pb-2 text-center">
          <p style={{ color: '#2a2a2a' }} className="text-[10px] uppercase tracking-widest">
            ChainMind · Tesla Supply Chain Optimizer · Powered by XGBoost + PuLP
          </p>
        </div>

      </div>
    </div>
  )
}
