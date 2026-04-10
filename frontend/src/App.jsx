import { useState, useEffect } from 'react'
import {
  MessageSquare, LayoutDashboard, Network, Zap, AlertTriangle,
  Cpu, RefreshCw,
} from 'lucide-react'
import { healthCheck } from './api/client.js'
import ChatPanel   from './components/ChatPanel.jsx'
import Dashboard   from './components/Dashboard.jsx'
import NetworkMap  from './components/NetworkMap.jsx'

// ── Design tokens ──────────────────────────────────────────────────────────────
const RED    = '#e82127'
const DIM    = '#6b7280'
const BORDER = '#2a2a2a'

// ═══════════════════════════════════════════════════════════════════════════════
// Backend health banner
// ═══════════════════════════════════════════════════════════════════════════════
function BackendBanner({ status, onRetry }) {
  if (status === 'ok' || status === 'checking' || status === null) return null

  return (
    <div style={{ background: '#1a0606', borderBottom: '1px solid #7f1d1d' }}
      className="px-5 py-2 flex items-center gap-3 shrink-0 fade-in">
      <AlertTriangle size={12} color="#ef4444" />
      <span style={{ color: '#fca5a5' }} className="text-xs">
        Backend offline — run:{' '}
        <code style={{ background: '#2d0a0a', color: '#fca5a5', border: '1px solid #7f1d1d' }}
          className="text-[10px] px-2 py-0.5 rounded font-mono">
          cd backend && uvicorn main:app --reload --port 8000
        </code>
      </span>
      <button
        onClick={onRetry}
        style={{ color: '#6b7280' }}
        className="ml-auto flex items-center gap-1 text-[10px] hover:text-gray-400 transition-colors">
        <RefreshCw size={10} /> retry
      </button>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Sidebar
// ═══════════════════════════════════════════════════════════════════════════════
function Sidebar({ active, setActive, backendStatus }) {
  const nav = [
    { id: 'chat',      icon: MessageSquare,   label: 'AI Chat'    },
    { id: 'dashboard', icon: LayoutDashboard,  label: 'Dashboard'  },
    { id: 'network',   icon: Network,          label: 'Network Map'},
  ]

  return (
    <aside style={{ background: '#0d0d0d', borderRight: `1px solid ${BORDER}` }}
      className="w-16 flex flex-col items-center py-4 gap-1 shrink-0 z-10">

      {/* Logo mark */}
      <div className="mb-6 flex flex-col items-center gap-1">
        <div style={{ background: RED }}
          className="w-8 h-8 rounded flex items-center justify-center">
          <Zap size={16} color="white" strokeWidth={2.5} />
        </div>
      </div>

      {nav.map(({ id, icon: Icon, label }) => (
        <button
          key={id}
          onClick={() => setActive(id)}
          title={label}
          style={{
            background: active === id ? '#1a1a1a' : 'transparent',
            borderLeft: active === id ? `2px solid ${RED}` : '2px solid transparent',
            color: active === id ? '#f5f5f5' : DIM,
          }}
          className="w-12 h-12 flex items-center justify-center rounded-r transition-all hover:text-white">
          <Icon size={20} strokeWidth={1.5} />
        </button>
      ))}

      {/* Backend status dot */}
      <div className="mt-auto mb-1" title={`Backend: ${backendStatus ?? 'unknown'}`}>
        <div style={{
          width: 6, height: 6, borderRadius: '50%',
          background: backendStatus === 'ok'
            ? '#10b981'
            : backendStatus === 'checking' || backendStatus === null
              ? '#f59e0b'
              : '#ef4444',
          boxShadow: backendStatus === 'ok' ? '0 0 4px #10b98160' : 'none',
          transition: 'background 0.4s',
        }} />
      </div>
    </aside>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Header
// ═══════════════════════════════════════════════════════════════════════════════
function Header({ view }) {
  const titles = {
    chat:      'AI Supply Chain Analyst',
    dashboard: 'Network Performance Dashboard',
    network:   'Inbound Network Map',
  }
  return (
    <header style={{ borderBottom: `1px solid ${BORDER}`, background: '#0d0d0d' }}
      className="h-12 flex items-center px-6 shrink-0">
      <span style={{ color: RED }} className="font-bold tracking-wider text-sm mr-3">
        CHAINMIND
      </span>
      <span style={{ color: BORDER }} className="mr-3">|</span>
      <span style={{ color: '#9ca3af' }} className="text-sm">{titles[view]}</span>
    </header>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Footer badge
// ═══════════════════════════════════════════════════════════════════════════════
function Footer() {
  return (
    <footer
      style={{ borderTop: `1px solid #161616`, background: '#0a0a0a', height: 26 }}
      className="flex items-center justify-between px-5 shrink-0">
      <span style={{ color: '#1e1e1e' }} className="text-[10px] tracking-wide select-none">
        ChainMind v1.0 · Tesla MLE Demo
      </span>
      <div className="flex items-center gap-2 select-none">
        <Cpu size={9} color="#2a2a2a" />
        <span style={{ color: '#2a2a2a' }} className="text-[10px]">Powered by</span>
        {[
          { label: 'Azure OpenAI gpt-5.2', color: '#0070f3' },
          { label: '3-Agent LangGraph',   color: '#7c3aed' },
          { label: 'XGBoost',             color: '#f59e0b' },
          { label: 'PuLP LP',             color: '#10b981' },
        ].map(({ label, color }, i, arr) => (
          <span key={label} className="flex items-center gap-2">
            <span style={{ color: color + '80' }} className="text-[10px] font-medium">
              {label}
            </span>
            {i < arr.length - 1 && (
              <span style={{ color: '#1e1e1e' }}>·</span>
            )}
          </span>
        ))}
      </div>
    </footer>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Root App
// ═══════════════════════════════════════════════════════════════════════════════
export default function App() {
  const [view,          setView]          = useState('chat')
  const [backendStatus, setBackendStatus] = useState(null) // null | 'checking' | 'ok' | 'error'

  const checkHealth = () => {
    setBackendStatus('checking')
    healthCheck()
      .then(() => setBackendStatus('ok'))
      .catch(() => setBackendStatus('error'))
  }

  // Check once on mount; re-check every 30s
  useEffect(() => {
    checkHealth()
    const id = setInterval(checkHealth, 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div style={{ background: '#080808' }} className="flex flex-col h-screen w-screen overflow-hidden">
      {/* Backend offline banner */}
      <BackendBanner status={backendStatus} onRetry={checkHealth} />

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar active={view} setActive={setView} backendStatus={backendStatus} />

        <div className="flex flex-col flex-1 overflow-hidden">
          <Header view={view} />
          {/*
            All three views stay mounted at all times so chat history,
            scroll position, and loaded data survive tab switches.
            display:none hides the inactive views without unmounting them.
          */}
          <main className="flex-1 overflow-hidden relative">
            <div className="absolute inset-0 flex flex-col overflow-hidden"
              style={{ display: view === 'chat' ? 'flex' : 'none' }}>
              <ChatPanel />
            </div>
            <div className="absolute inset-0 flex flex-col overflow-hidden"
              style={{ display: view === 'dashboard' ? 'flex' : 'none' }}>
              <Dashboard />
            </div>
            <div className="absolute inset-0 flex flex-col overflow-hidden"
              style={{ display: view === 'network' ? 'flex' : 'none' }}>
              <NetworkMap />
            </div>
          </main>
          <Footer />
        </div>
      </div>
    </div>
  )
}
