import React, { useState, useEffect, useRef } from 'react';
import {
  Activity,
  Server,
  Box,
  AlertTriangle,
  Play,
  RotateCw,
  Square,
  Terminal,
  Shield,
  Send,
  Zap,
  CheckCircle2,
  XCircle,
  Clock,
  Cpu,
  Layers,
  Sparkles,
  RefreshCw,
  LogOut,
  ListOrdered,
  Radio,
  FileText,
  Sliders,
  ChevronRight
} from 'lucide-react';

const API_BASE = '/api';
const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;

// ── Pure SVG Sparkline Component (Phase 4) ──────────────────────────────────
function Sparkline({ data = [], color = 'var(--cyan-400)', height = 24, width = 100, strokeWidth = 1.75, unit = '' }) {
  if (!data || data.length === 0) {
    return (
      <div style={{ height, width, display: 'flex', alignItems: 'center', opacity: 0.25 }}>
        <span className="font-mono" style={{ fontSize: '0.65rem' }}>—</span>
      </div>
    );
  }

  const ptsData = data.length === 1 ? [data[0], data[0]] : data;
  const min = Math.min(...ptsData);
  const max = Math.max(...ptsData);
  const diff = max - min === 0 ? 1 : max - min;
  const pad = 2;
  const usableW = width - pad * 2;
  const usableH = height - pad * 2;

  const coords = ptsData.map((val, i) => {
    const x = pad + (i / (ptsData.length - 1)) * usableW;
    const y = height - pad - ((val - min) / diff) * usableH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const pathLine = `M ${coords.join(' L ')}`;
  const pathArea = `M ${coords[0].split(',')[0]},${height} L ${coords.join(' L ')} L ${coords[coords.length - 1].split(',')[0]},${height} Z`;
  const lastCoord = coords[coords.length - 1].split(',');

  return (
    <div style={{ position: 'relative', width, height }} title={`Min: ${min.toFixed(1)}${unit} • Max: ${max.toFixed(1)}${unit} • Latest: ${ptsData[ptsData.length - 1].toFixed(1)}${unit}`}>
      <svg width={width} height={height} style={{ overflow: 'visible' }}>
        <defs>
          <linearGradient id={`grad-${color.replace(/[^a-zA-Z0-9]/g, '')}`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={color} stopOpacity="0.25" />
            <stop offset="100%" stopColor={color} stopOpacity="0.0" />
          </linearGradient>
        </defs>
        <path d={pathArea} fill={`url(#grad-${color.replace(/[^a-zA-Z0-9]/g, '')})`} />
        <path d={pathLine} fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
        <circle cx={lastCoord[0]} cy={lastCoord[1]} r="2" fill={color} />
      </svg>
    </div>
  );
}

// ── Interactive Cluster Topology Map (Phase 4) ──────────────────────────────
function ClusterTopologyMap({ slaves = [], masterStats, selectedNodeFilter, onSelectNode, containers = [] }) {
  const masterContainerCount = containers.filter(c => !c.slave_id || c.slave_id === 'local').length;

  return (
    <div className="card-glass mb-6" style={{ padding: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
        <div>
          <h3 className="text-base font-semibold flex items-center gap-2">
            <Radio size={18} className="text-cyan" /> Interactive Cluster Topology Map (Phase 4)
          </h3>
          <div className="text-xs text-dim">
            Real-time encrypted mTLS data bus architecture • Click any node to filter container fleet
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          {selectedNodeFilter && (
            <button
              className="btn btn-secondary btn-sm"
              style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem', color: 'var(--cyan-400)' }}
              onClick={() => onSelectNode(null)}
            >
              ✕ Filtered: {selectedNodeFilter} (Show All)
            </button>
          )}
          <span className="badge badge-cyan" style={{ fontSize: '0.7rem' }}>
            {1 + slaves.length} Active Nodes
          </span>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-around', position: 'relative', minHeight: '180px', padding: '1rem 0' }}>
        {/* Master Controller Node */}
        <div
          className={`card-glass cursor-pointer ${selectedNodeFilter === 'local' ? 'border-cyan' : ''}`}
          style={{
            width: '260px',
            padding: '1rem',
            background: selectedNodeFilter === 'local' ? 'rgba(6, 182, 212, 0.12)' : 'rgba(15, 23, 42, 0.75)',
            borderColor: selectedNodeFilter === 'local' ? 'var(--cyan-400)' : 'var(--emerald-400)',
            borderLeft: '4px solid var(--emerald-400)',
            transition: 'all 0.2s',
            zIndex: 2,
          }}
          onClick={() => onSelectNode(selectedNodeFilter === 'local' ? null : 'local')}
          title="Click to filter containers on Master host"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
            <div>
              <div className="font-bold text-sm text-emerald flex items-center gap-1.5">
                <Server size={15} /> master (local)
              </div>
              <div className="font-mono text-xs text-dim">127.0.0.1:8000</div>
            </div>
            <span className="badge badge-ok" style={{ fontSize: '0.65rem' }}>CONTROLLER</span>
          </div>
          <div className="text-xs text-muted mb-2">Primary Orchestrator & AI Engine</div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontFamily: 'monospace' }}>
            <span className="text-dim">Containers:</span>
            <span className="text-cyan font-bold">{masterContainerCount}</span>
          </div>
          {masterStats && (
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontFamily: 'monospace', marginTop: '0.25rem' }}>
              <span className="text-dim">Host CPU:</span>
              <span className="text-emerald">{masterStats.cpu_pct?.toFixed(1) || 0}%</span>
            </div>
          )}
        </div>

        {/* Central Data Bus Vector Line */}
        <div style={{ flex: 1, height: '80px', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg style={{ position: 'absolute', width: '100%', height: '100%', overflow: 'visible' }}>
            <defs>
              <linearGradient id="bus-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="var(--emerald-400)" stopOpacity="0.8" />
                <stop offset="50%" stopColor="var(--cyan-400)" stopOpacity="1" />
                <stop offset="100%" stopColor="var(--violet-400)" stopOpacity="0.8" />
              </linearGradient>
            </defs>
            <line
              x1="0"
              y1="40"
              x2="100%"
              y2="40"
              stroke="url(#bus-grad)"
              strokeWidth="2.5"
              strokeDasharray="6,4"
              style={{ animation: 'dash-stream 1.5s linear infinite' }}
            />
          </svg>
          <div
            className="badge badge-secondary"
            style={{
              zIndex: 3,
              background: 'rgba(15, 23, 42, 0.9)',
              border: '1px solid var(--cyan-400)',
              color: 'var(--cyan-400)',
              fontSize: '0.7rem',
              boxShadow: '0 0 10px rgba(6,182,212,0.3)',
              padding: '0.25rem 0.6rem',
            }}
          >
            ⚡ mTLS Data Bus (Active Heartbeat)
          </div>
        </div>

        {/* Slave Edge Nodes */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', zIndex: 2 }}>
          {slaves.map((slave) => {
            const isOnline = slave.is_online || slave.status === 'online';
            const isSelected = selectedNodeFilter === slave.slave_id;
            const slaveContainers = containers.filter(c => c.slave_id === slave.slave_id).length || slave.container_count || 0;

            return (
              <div
                key={slave.slave_id}
                className={`card-glass cursor-pointer ${isSelected ? 'border-cyan' : ''}`}
                style={{
                  width: '260px',
                  padding: '1rem',
                  background: isSelected ? 'rgba(6, 182, 212, 0.12)' : 'rgba(15, 23, 42, 0.75)',
                  borderColor: isSelected ? 'var(--cyan-400)' : isOnline ? 'var(--cyan-400)' : 'var(--rose-400)',
                  borderLeft: `4px solid ${isOnline ? 'var(--cyan-400)' : 'var(--rose-400)'}`,
                  transition: 'all 0.2s',
                }}
                onClick={() => onSelectNode(isSelected ? null : slave.slave_id)}
                title="Click to filter containers on this slave node"
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                  <div>
                    <div className="font-bold text-sm text-cyan flex items-center gap-1.5">
                      <Radio size={15} /> {slave.slave_id}
                    </div>
                    <div className="font-mono text-xs text-dim">{slave.ip || '172.28.0.2'}:{slave.port || 8080}</div>
                  </div>
                  <span className={`badge ${isOnline ? 'badge-ok' : 'badge-error'}`} style={{ fontSize: '0.65rem' }}>
                    {isOnline ? 'ONLINE' : 'OFFLINE'}
                  </span>
                </div>
                <div className="text-xs text-muted mb-2">Remote Edge Agent (Docker Worker)</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontFamily: 'monospace' }}>
                  <span className="text-dim">Containers:</span>
                  <span className="text-cyan font-bold">{slaveContainers}</span>
                </div>
                {slave.host_stats && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontFamily: 'monospace', marginTop: '0.25rem' }}>
                    <span className="text-dim">Edge CPU:</span>
                    <span className="text-cyan">{slave.host_stats.cpu_pct?.toFixed(1) || 0}%</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Login Screen Component ──────────────────────────────────────────────────
function LoginScreen({ onLoginSuccess }) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('admin123');
  const [role, setRole] = useState('admin');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handlePreset = (u, p, r) => {
    setUsername(u);
    setPassword(p);
    setRole(r);
    setError('');
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('Please provide both username and password.');
      return;
    }
    setError('');
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password: password.trim() }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || 'Invalid username or password.');
        setLoading(false);
        return;
      }

      const data = await res.json();
      const ranks = { viewer: 0, operator: 1, admin: 2 };
      const actualRole = data.role || 'viewer';
      if ((ranks[actualRole] ?? 0) < (ranks[role] ?? 0)) {
        setError(`Access Denied: Account '${username}' has role '${actualRole}', which cannot elevate to '${role}'.`);
        setLoading(false);
        return;
      }

      localStorage.setItem('dockermind_token', data.access_token);
      localStorage.setItem('dockermind_user', data.username || username);
      localStorage.setItem('dockermind_role', data.role || role);

      onLoginSuccess(data.access_token, {
        username: data.username || username,
        role: data.role || role,
      });
    } catch (err) {
      setError('Connection failed. Please ensure the DockerMind master container is online.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrapper">
      <div className="login-card">
        <div className="login-header">
          <div className="login-icon-box">
            <Activity className="icon-cyan pulse" size={32} />
          </div>
          <h1 className="login-title font-mono">DOCKERMIND</h1>
          <p className="login-subtitle">Autonomous AI SRE & Control Plane</p>
        </div>

        {error && (
          <div className="login-error-banner font-mono">
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleLogin} className="login-form">
          <div className="form-group">
            <label className="form-label font-mono" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Username</label>
            <input
              type="text"
              className="input-field font-mono"
              placeholder="e.g. admin"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label font-mono" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Password</label>
            <input
              type="password"
              className="input-field font-mono"
              placeholder="e.g. admin123"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label font-mono" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Role Selection</label>
            <select
              className="input-field font-mono"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              style={{ cursor: 'pointer' }}
            >
              <option value="admin">admin (Full Cluster Control & Exec)</option>
              <option value="operator">operator (Remediate, Restart & Dispatch)</option>
              <option value="viewer">viewer (Read-Only Telemetry & Logs)</option>
            </select>
          </div>

          <button
            type="submit"
            className="btn btn-primary font-mono"
            style={{ width: '100%', marginTop: '0.5rem', padding: '0.75rem', justifyContent: 'center' }}
            disabled={loading}
          >
            {loading ? 'Authenticating...' : 'Sign In to Cluster'}
          </button>
        </form>

        <div className="login-presets" style={{ marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid var(--border-subtle)' }}>
          <div className="text-xs font-mono text-dim" style={{ marginBottom: '0.5rem' }}>QUICK PRESETS:</div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              type="button"
              className="btn btn-secondary btn-xs font-mono"
              style={{ flex: 1, borderColor: role === 'admin' ? 'var(--cyan-400)' : 'var(--border-subtle)' }}
              onClick={() => handlePreset('admin', 'admin123', 'admin')}
            >
              admin
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-xs font-mono"
              style={{ flex: 1, borderColor: role === 'operator' ? 'var(--amber-400)' : 'var(--border-subtle)' }}
              onClick={() => handlePreset('uday', 'test123', 'operator')}
            >
              uday:op
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-xs font-mono"
              style={{ flex: 1, borderColor: role === 'viewer' ? 'var(--emerald-400)' : 'var(--border-subtle)' }}
              onClick={() => handlePreset('uday2', 'test123', 'viewer')}
            >
              uday2:view
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}


// Host Telemetry Gauges Renderer (CPU, Memory, Disk)
const renderHostGauges = (stats, isOnline = true) => {
  if (!isOnline) {
    return (
      <div className="mt-3 pt-3 text-xs text-rose font-mono flex items-center gap-1.5" style={{ borderTop: '1px solid rgba(51,65,85,0.4)' }}>
        <XCircle size={13} /> Node unreachable — telemetry stream disconnected
      </div>
    );
  }

  if (!stats || !stats.mem_total_gb) {
    return (
      <div className="mt-3 pt-3 text-xs text-muted font-mono flex items-center gap-1.5" style={{ borderTop: '1px solid rgba(51,65,85,0.4)' }}>
        <Sparkles size={12} className="animate-spin text-cyan" /> Polling host metrics (RAM, Disk, CPU)...
      </div>
    );
  }

  const cpuPct = stats.cpu_pct || 0;
  const memPct = stats.mem_pct || 0;
  const diskPct = stats.disk_pct || 0;

  const getFill = (pct) => pct > 85 ? 'fill-rose' : pct > 70 ? 'fill-amber' : 'fill-emerald';

  return (
    <div className="mt-3 pt-2.5" style={{ borderTop: '1px solid rgba(51,65,85,0.4)' }}>
      {/* CPU */}
      <div className="mb-2">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }} className="text-xs font-mono">
          <span className="text-muted flex items-center gap-1"><Cpu size={12} className="text-cyan" /> CPU Load</span>
          <span className="font-semibold text-slate-200">{cpuPct.toFixed(1)}%</span>
        </div>
        <div className="progress-bar-bg" style={{ height: '5px', marginTop: '0.25rem' }}>
          <div className={`progress-bar-fill ${cpuPct > 85 ? 'fill-rose' : cpuPct > 70 ? 'fill-amber' : 'fill-cyan'}`} style={{ width: `${Math.min(100, Math.max(3, cpuPct))}%` }} />
        </div>
      </div>

      {/* Memory (RAM) */}
      <div className="mb-2">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }} className="text-xs font-mono">
          <span className="text-muted flex items-center gap-1"><Activity size={12} className="text-violet" /> Host RAM</span>
          <span className="font-semibold text-slate-200">{stats.mem_used_gb} GB / {stats.mem_total_gb} GB ({memPct.toFixed(1)}%)</span>
        </div>
        <div className="progress-bar-bg" style={{ height: '5px', marginTop: '0.25rem' }}>
          <div className={`progress-bar-fill ${getFill(memPct)}`} style={{ width: `${Math.min(100, Math.max(3, memPct))}%` }} />
        </div>
      </div>

      {/* Storage (Disk) */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }} className="text-xs font-mono">
          <span className="text-muted flex items-center gap-1"><Layers size={12} className="text-amber" /> Disk Storage</span>
          <span className="font-semibold text-slate-200">{stats.disk_used_gb} GB / {stats.disk_total_gb} GB ({diskPct.toFixed(1)}%)</span>
        </div>
        <div className="progress-bar-bg" style={{ height: '5px', marginTop: '0.25rem' }}>
          <div className={`progress-bar-fill ${getFill(diskPct)}`} style={{ width: `${Math.min(100, Math.max(3, diskPct))}%` }} />
        </div>
      </div>
    </div>
  );
};

export default function App() {
  const [activeTab, setActiveTab] = useState('fleet'); // fleet | logs | incidents | dispatch | audit | chat
  const [token, setToken] = useState(localStorage.getItem('dockermind_token') || '');
  const [currentUser, setCurrentUser] = useState(() => {
    const u = localStorage.getItem('dockermind_user');
    const r = localStorage.getItem('dockermind_role');
    return u ? { username: u, role: r || 'viewer' } : null;
  });
  const [wsConnected, setWsConnected] = useState(false);
  const [lastPing, setLastPing] = useState(null);

  // Cluster State
  const [slaves, setSlaves] = useState([]);
  const [containers, setContainers] = useState([]);
  const [statsMap, setStatsMap] = useState({}); // containerName -> { cpu_pct, mem_pct, mem_used_mb, mem_limit_mb }
  const [alerts, setAlerts] = useState([]);
  const [crashLoops, setCrashLoops] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [masterHostStats, setMasterHostStats] = useState(null);
  const [metricsSummary, setMetricsSummary] = useState({ containers: {}, hosts: {} });
  const [selectedNodeFilter, setSelectedNodeFilter] = useState(null);

  // Log & AI Diagnosis State
  const [selectedContainer, setSelectedContainer] = useState('dockermind-master');
  const [containerLogs, setContainerLogs] = useState('');
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);

  // Fleet Dispatch Modal State
  const [dispatchModalOpen, setDispatchModalOpen] = useState(false);
  const [dispatchTarget, setDispatchTarget] = useState('all');
  const [dispatchAction, setDispatchAction] = useState('log_check');
  const [dispatchContainer, setDispatchContainer] = useState('');
  const [dispatchCommand, setDispatchCommand] = useState('uptime');
  const [dispatchResult, setDispatchResult] = useState(null);
  const [dispatching, setDispatching] = useState(false);

  // Exec Modal State
  const [execModalOpen, setExecModalOpen] = useState(false);
  const [execTargetContainer, setExecTargetContainer] = useState('');
  const [execCmd, setExecCmd] = useState('echo "DockerMind agent online"');
  const [execResult, setExecResult] = useState(null);
  const [executing, setExecuting] = useState(false);

  // AI Diagnosis & Remediation Modal State
  const [healModalOpen, setHealModalOpen] = useState(false);
  const [healTargetContainer, setHealTargetContainer] = useState('');
  const [healTargetSlave, setHealTargetSlave] = useState('local');
  const [healLoading, setHealLoading] = useState(false);
  const [healDiagnosis, setHealDiagnosis] = useState(null);
  const [healLogSnippet, setHealLogSnippet] = useState('');
  const [healExecuting, setHealExecuting] = useState(false);

  // Chat State
  const [chatMessages, setChatMessages] = useState([
    { role: 'assistant', text: 'Hello! I am your DockerMind AI DevOps assistant. Ask me to diagnose crashing containers, explain OOM kills, or generate remediation runbooks.' }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);

  // Runbooks State (Phase 3)
  const [runbooks, setRunbooks] = useState([]);
  const [selectedRunbookId, setSelectedRunbookId] = useState('');
  const [rbTargetSlave, setRbTargetSlave] = useState('local');
  const [rbTargetContainer, setRbTargetContainer] = useState('dockermind-slave-local');
  const [rbStopOnFailure, setRbStopOnFailure] = useState(true);
  const [rbRetryCount, setRbRetryCount] = useState(1);
  const [rbExecuting, setRbExecuting] = useState(false);
  const [rbExecutionResult, setRbExecutionResult] = useState(null);

  // Create Runbook Modal State
  const [createRbModalOpen, setCreateRbModalOpen] = useState(false);
  const [newRbName, setNewRbName] = useState('');
  const [newRbDesc, setNewRbDesc] = useState('');
  const [newRbTrigger, setNewRbTrigger] = useState('manual');
  const [newRbStopOnFailure, setNewRbStopOnFailure] = useState(true);
  const [newRbRetryCount, setNewRbRetryCount] = useState(1);
  const [newRbSteps, setNewRbSteps] = useState([
    { type: 'log_check', description: 'Pre-flight log verification', optional: true },
    { type: 'restart', description: 'Container restart', retry_count: 2 },
    { type: 'log_check', description: 'Verify service recovery' },
  ]);

  // Webhook & Alerting Settings Modal State (Phase 3)
  const [webhookModalOpen, setWebhookModalOpen] = useState(false);
  const [webhookSettings, setWebhookSettings] = useState({
    slack_webhook_url: '',
    discord_webhook_url: '',
    generic_webhook_url: '',
    min_severity: 'warn',
  });
  const [webhookSaving, setWebhookSaving] = useState(false);
  const [webhookTesting, setWebhookTesting] = useState(false);

  // Toast Notifications
  const [toasts, setToasts] = useState([]);

  const addToast = (type, title, msg) => {
    const id = Date.now() + Math.random();
    setToasts(prev => [{ id, type, title, msg }, ...prev.slice(0, 4)]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 6000);
  };

  const handleLogout = () => {
    localStorage.removeItem('dockermind_token');
    localStorage.removeItem('dockermind_user');
    localStorage.removeItem('dockermind_role');
    setToken('');
    setCurrentUser(null);
  };

  // Helper fetch with Bearer token
  const apiFetch = async (endpoint, options = {}) => {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    const currentToken = token || localStorage.getItem('dockermind_token');
    if (currentToken) headers['Authorization'] = `Bearer ${currentToken}`;
    try {
      const res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
      if (res.status === 401) {
        handleLogout();
        return null;
      }
      return await res.json();
    } catch (err) {
      console.error(`API Fetch Error ${endpoint}:`, err);
      return null;
    }
  };

  // Initialize Data concurrently with Promise.all
  const refreshAll = async () => {
    try {
      const [slavesData, containersData, alertsData, crashData, auditData, jobsData, meData, runbooksData, metricsData] = await Promise.all([
        apiFetch('/slaves'),
        apiFetch('/containers'),
        apiFetch('/alerts'),
        apiFetch('/slaves/crash-loops'),
        apiFetch('/jobs/audit/log?limit=25'),
        apiFetch('/jobs'),
        apiFetch('/auth/me'),
        apiFetch('/runbooks'),
        apiFetch('/metrics/summary'),
      ]);

      if (slavesData?.slaves) setSlaves(slavesData.slaves);
      if (slavesData?.master_host_stats) setMasterHostStats(slavesData.master_host_stats);
      if (containersData?.containers) setContainers(containersData.containers);
      if (alertsData?.alerts) setAlerts(alertsData.alerts);
      if (crashData?.crash_loops) setCrashLoops(crashData.crash_loops);
      if (auditData?.audit_log) setAuditLogs(auditData.audit_log);
      if (jobsData?.jobs) setJobs(jobsData.jobs);
      if (meData?.username) setCurrentUser(meData);
      if (metricsData?.containers) setMetricsSummary(metricsData);
      if (runbooksData?.runbooks) {
        setRunbooks(runbooksData.runbooks);
        if (!selectedRunbookId && runbooksData.runbooks.length > 0) {
          setSelectedRunbookId(runbooksData.runbooks[0].id);
        }
      }
    } catch (e) {
      console.error('refreshAll error:', e);
    }
  };

  useEffect(() => {
    if (token) {
      apiFetch('/auth/me').then(me => {
        if (me && me.username) {
          setCurrentUser(me);
          refreshAll();
        } else {
          handleLogout();
        }
      }).catch(() => handleLogout());
    }
  }, [token]);

  // Webhook Settings Helpers (Phase 3)
  const openWebhookModal = async () => {
    setWebhookModalOpen(true);
    const data = await apiFetch('/alerts/settings');
    if (data) {
      setWebhookSettings({
        slack_webhook_url: data.slack_webhook_url || '',
        discord_webhook_url: data.discord_webhook_url || '',
        generic_webhook_url: data.generic_webhook_url || '',
        min_severity: data.min_severity || 'warn',
      });
    }
  };

  const handleSaveWebhookSettings = async () => {
    setWebhookSaving(true);
    const res = await apiFetch('/alerts/settings', {
      method: 'POST',
      body: JSON.stringify(webhookSettings),
    });
    setWebhookSaving(false);
    if (res?.status === 'updated') {
      addToast('ok', 'Alert Settings Saved', 'Slack/Discord webhook configuration persisted to database.');
      setWebhookModalOpen(false);
    } else {
      addToast('crit', 'Save Failed', res?.detail || 'Could not update alert settings.');
    }
  };

  const handleSendTestWebhook = async () => {
    setWebhookTesting(true);
    const res = await apiFetch('/alerts/test-webhook', { method: 'POST' });
    setWebhookTesting(false);
    if (res?.status === 'dispatched') {
      const slackRes = res.results?.slack || 'not_configured';
      const discordRes = res.results?.discord || 'not_configured';
      addToast('ok', 'Diagnostic Ping Dispatched', `Slack: ${slackRes} | Discord: ${discordRes}`);
    } else {
      addToast('crit', 'Test Failed', 'Could not dispatch test notification.');
    }
  };

  // Runbook Execution Helpers (Phase 3)
  const handleExecuteRunbook = async (runbookId) => {
    if (!rbTargetContainer) {
      addToast('warn', 'Container Required', 'Please enter or select a target container.');
      return;
    }
    setRbExecuting(true);
    setRbExecutionResult(null);
    const res = await apiFetch(`/runbooks/${runbookId}/execute`, {
      method: 'POST',
      body: JSON.stringify({
        slave_id: rbTargetSlave,
        container: rbTargetContainer,
        stop_on_failure: rbStopOnFailure,
        retry_count: rbRetryCount,
      }),
    });
    setRbExecuting(false);
    if (res) {
      setRbExecutionResult(res);
      if (res.success) {
        addToast('ok', 'Runbook Passed', `${res.runbook_name} completed all steps successfully.`);
      } else {
        addToast('crit', 'Runbook Execution Failed', `${res.runbook_name} failed ${res.stopped_on_failure ? '(Execution halted early by Stop on Failure policy)' : ''}`);
      }
      refreshAll();
    }
  };

  const handleCreateRunbook = async () => {
    if (!newRbName.trim() || newRbSteps.length === 0) {
      addToast('warn', 'Validation Error', 'Runbook must have a valid name and at least one step.');
      return;
    }
    const res = await apiFetch('/runbooks', {
      method: 'POST',
      body: JSON.stringify({
        name: newRbName.trim(),
        description: newRbDesc.trim(),
        trigger: newRbTrigger,
        stop_on_failure: newRbStopOnFailure,
        retry_count: newRbRetryCount,
        steps: newRbSteps,
      }),
    });
    if (res?.status === 'created') {
      addToast('ok', 'Runbook Created', `Runbook '${newRbName}' created with automated execution policy.`);
      setCreateRbModalOpen(false);
      setNewRbName('');
      setNewRbDesc('');
      refreshAll();
    } else {
      addToast('crit', 'Creation Failed', res?.detail || 'Could not create runbook.');
    }
  };

  const handleAddStepToNewRb = () => {
    setNewRbSteps(prev => [...prev, { type: 'log_check', description: 'Additional verification step' }]);
  };

  const handleUpdateNewRbStep = (index, field, value) => {
    setNewRbSteps(prev => prev.map((s, i) => i === index ? { ...s, [field]: value } : s));
  };

  const handleRemoveNewRbStep = (index) => {
    setNewRbSteps(prev => prev.filter((_, i) => i !== index));
  };

  // Fetch Container Logs
  const fetchLogs = async (containerName) => {
    setSelectedContainer(containerName);
    const data = await apiFetch(`/containers/${containerName}/logs?tail=80`);
    if (data?.logs) {
      setContainerLogs(data.logs);
    } else {
      setContainerLogs(`[No recent logs found for container ${containerName}]`);
    }
  };

  useEffect(() => {
    if (selectedContainer) {
      fetchLogs(selectedContainer);
    }
  }, [selectedContainer]);

  // Run AI Analysis on Logs
  const runAiAnalysis = async (containerName) => {
    setAnalyzing(true);
    setAiAnalysis(null);
    try {
      const res = await apiFetch(`/logs/${containerName}/analyze?tail=100`);
      if (res?.analysis) {
        setAiAnalysis(res.analysis);
        addToast('ai', 'AI Diagnosis Ready', `Identified: ${res.analysis.severity.toUpperCase()} on ${containerName}`);
      }
    } catch (err) {
      addToast('error', 'Analysis Failed', String(err));
    } finally {
      setAnalyzing(false);
    }
  };

  // Open Interactive AI Diagnosis Modal
  const openHealModal = async (containerName, slaveId = 'local') => {
    setHealTargetContainer(containerName);
    setHealTargetSlave(slaveId);
    setHealDiagnosis(null);
    setHealLogSnippet('');
    setHealLoading(true);
    setHealModalOpen(true);
    try {
      const res = await apiFetch(`/logs/${encodeURIComponent(containerName)}/analyze?tail=100`);
      if (res?.analysis) {
        setHealDiagnosis(res.analysis);
        setHealLogSnippet(res.log_snippet || '');
      } else {
        setHealDiagnosis({
          severity: 'warn',
          root_cause: 'Could not parse diagnosis from AI',
          fix: 'Inspect container logs manually',
          auto_heal: false,
          heal_action: 'none',
        });
      }
    } catch (err) {
      setHealDiagnosis({
        severity: 'error',
        root_cause: `Failed to contact AI diagnostic service: ${err.message}`,
        fix: 'Ensure master service is running and LLM is reachable',
        auto_heal: false,
        heal_action: 'none',
      });
    } finally {
      setHealLoading(false);
    }
  };

  const handleExecuteHealAction = async (action) => {
    setHealExecuting(true);
    await triggerAutoHeal(healTargetContainer, healTargetSlave, action);
    setHealExecuting(false);
    setHealModalOpen(false);
  };

  const handleForceRestartFromModal = async () => {
    setHealExecuting(true);
    try {
      await apiFetch(`/containers/${healTargetContainer}/restart`, { method: 'POST' });
      addToast('ok', 'Container Restarted', `Successfully restarted ${healTargetContainer}`);
      refreshAll();
    } catch (err) {
      addToast('error', 'Restart Failed', String(err));
    } finally {
      setHealExecuting(false);
      setHealModalOpen(false);
    }
  };

  // Trigger Auto-Heal
  const triggerAutoHeal = async (containerName, slaveId = 'local', action = null) => {
    addToast('info', 'Heal Triggered', `Initiating healing for ${containerName}...`);
    const res = await apiFetch('/heal', {
      method: 'POST',
      body: JSON.stringify({ container_name: containerName, slave_id: slaveId, action }),
    });
    if (res?.success) {
      addToast('ok', 'Heal Successful', res.message || `Container ${containerName} recovered`);
    } else if (res?.circuit_breaker) {
      addToast('error', 'Circuit Breaker Tripped', res.reason);
    } else if (res?.skipped) {
      addToast('warn', 'Heal Cooldown Active', res.reason);
    } else {
      addToast('error', 'Heal Failed', res?.message || 'Could not heal container');
    }
    refreshAll();
  };

  // Reset Circuit Breaker
  const resetCircuitBreaker = async (slaveId, containerName) => {
    const res = await apiFetch('/slaves/circuit-breaker/reset', {
      method: 'POST',
      body: JSON.stringify({ slave_id: slaveId, container_name: containerName }),
    });
    if (res?.status === 'reset') {
      addToast('ok', 'Circuit Breaker Reset', `Cleared backoff for ${containerName}`);
      refreshAll();
    }
  };

  // Acknowledge Alert
  const acknowledgeAlert = async (alertId) => {
    const res = await apiFetch(`/alerts/${alertId}/acknowledge`, { method: 'POST' });
    if (res?.status === 'acknowledged') {
      addToast('ok', 'Alert Acknowledged', `Incident ${alertId} silenced`);
      refreshAll();
    }
  };

  // Multi-Slave Fleet Dispatch
  const handleFleetDispatch = async () => {
    setDispatching(true);
    setDispatchResult(null);
    try {
      const payload = dispatchAction === 'exec' ? { command: dispatchCommand } : {};
      const res = await apiFetch('/slaves/dispatch', {
        method: 'POST',
        body: JSON.stringify({
          action: dispatchAction,
          container: dispatchContainer,
          targets: dispatchTarget === 'all' ? 'all' : [dispatchTarget],
          payload,
        }),
      });
      setDispatchResult(res);
      addToast('ok', 'Fleet Command Complete', `Dispatched to ${res?.total || 0} nodes (${res?.successful || 0} succeeded)`);
      refreshAll();
    } catch (e) {
      addToast('error', 'Dispatch Error', String(e));
    } finally {
      setDispatching(false);
    }
  };

  // Exec in Container
  const handleExec = async () => {
    setExecuting(true);
    setExecResult(null);
    try {
      const res = await apiFetch('/containers/exec', {
        method: 'POST',
        body: JSON.stringify({
          container_name: execTargetContainer,
          command: execCmd,
          slave_id: 'local',
        }),
      });
      setExecResult(res);
      addToast('ok', 'Command Executed', `Exit code: ${res?.exit_code ?? 0}`);
    } catch (e) {
      addToast('error', 'Exec Error', String(e));
    } finally {
      setExecuting(false);
    }
  };

  // Send AI Chat Message
  const sendChatMessage = async () => {
    if (!chatInput.trim()) return;
    const userMsg = chatInput.trim();
    setChatMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setChatInput('');
    setChatLoading(true);

    try {
      const res = await apiFetch('/chat', {
        method: 'POST',
        body: JSON.stringify({ message: userMsg, context: `Current active cluster has ${containers.length} containers and ${alerts.length} alerts.` }),
      });
      if (res?.reply) {
        setChatMessages(prev => [...prev, { role: 'assistant', text: res.reply, provider: res.provider }]);
      } else {
        setChatMessages(prev => [...prev, { role: 'assistant', text: 'Error connecting to LLM provider. Please check backend API keys.' }]);
      }
    } catch (e) {
      setChatMessages(prev => [...prev, { role: 'assistant', text: `Failed to fetch response: ${e.message}` }]);
    } finally {
      setChatLoading(false);
    }
  };

  // WebSocket Live Stream Connection with Token Auth & Reconnection Guard
  useEffect(() => {
    if (!token) return;
    let ws = null;
    let pingInterval = null;
    let reconnectTimer = null;
    let isCancelled = false;

    const connectWS = () => {
      if (isCancelled) return;
      try {
        const url = `${WS_URL}?token=${encodeURIComponent(token)}`;
        ws = new WebSocket(url);

        ws.onopen = () => {
          if (isCancelled) {
            if (ws) ws.close();
            return;
          }
          setWsConnected(true);
          pingInterval = setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
              ws.send('ping');
              setLastPing(new Date().toLocaleTimeString());
            }
          }, 15000);
        };

        ws.onmessage = (event) => {
          if (isCancelled) return;
          try {
            const data = JSON.parse(event.data);
            if (data.event === 'init') {
              if (data.slaves) setSlaves(data.slaves);
              if (data.containers) setContainers(data.containers);
              if (data.master_host_stats) setMasterHostStats(data.master_host_stats);

            } else if (data.event === 'alert') {
              setAlerts(prev => [data.alert, ...prev]);
              addToast(data.alert.severity === 'critical' ? 'crit' : 'warn', 'Incident Alert', `${data.container}: ${data.alert.root_cause}`);
            } else if (data.event === 'auto_heal') {
              addToast('ok', 'Auto-Heal Executed', `${data.result?.container}: ${data.result?.action} (${data.result?.success ? 'Success' : 'Failed'})`);
              refreshAll();
            } else if (data.event === 'container_lifecycle_event') {
              addToast('info', 'Lifecycle Event', `${data.data?.container_name}: ${data.data?.event_type}`);
              refreshAll();
            } else if (data.event === 'slave_status') {
              if (data.data) setSlaves(data.data);
              if (data.master_host_stats) setMasterHostStats(data.master_host_stats);
            } else if (data.event === 'stats_update') {
              if (data.stats) {
                setStatsMap(prev => {
                  const updated = { ...prev };
                  data.stats.forEach(s => { updated[s.name] = s; });
                  return updated;
                });
                setMetricsSummary(prev => {
                  const nextContainers = { ...(prev.containers || {}) };
                  data.stats.forEach(s => {
                    const existing = nextContainers[s.name] || { cpu: [], mem: [], mem_pct: [], leak_risk: false, mem_trend_mb_hr: 0 };
                    const newCpu = [...(existing.cpu || []).slice(-19), Number(s.cpu_pct.toFixed(1))];
                    const newMem = [...(existing.mem || []).slice(-19), Number(s.mem_used_mb.toFixed(1))];
                    const newMemPct = [...(existing.mem_pct || []).slice(-19), Number(s.mem_pct.toFixed(1))];
                    nextContainers[s.name] = { ...existing, cpu: newCpu, mem: newMem, mem_pct: newMemPct };
                  });
                  return { ...prev, containers: nextContainers };
                });
              }
              if (data.host_stats && data.slave_id) {
                setSlaves(prev => prev.map(s => s.slave_id === data.slave_id ? { ...s, host_stats: data.host_stats } : s));
              }
            }
          } catch (e) {
            console.error('WS Parse error:', e);
          }
        };

        ws.onclose = (event) => {
          setWsConnected(false);
          if (pingInterval) clearInterval(pingInterval);
          // If connection was rejected due to authentication (code 1008), do not retry indefinitely
          if (event && event.code === 1008) {
            console.warn('[DockerMind WS] Connection closed by policy violation (1008): Unauthorized or expired token');
            return;
          }
          if (!isCancelled && token) {
            reconnectTimer = setTimeout(connectWS, 4000);
          }
        };

        ws.onerror = () => {
          setWsConnected(false);
        };
      } catch (err) {
        setWsConnected(false);
        if (!isCancelled && token) {
          reconnectTimer = setTimeout(connectWS, 4000);
        }
      }
    };

    connectWS();

    return () => {
      isCancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (pingInterval) clearInterval(pingInterval);
      if (ws) {
        ws.onclose = null; // Detach listener so closing during unmount does not trigger reconnect
        ws.close();
      }
    };
  }, [token]);

  const userRole = currentUser?.role || localStorage.getItem('dockermind_role') || 'viewer';
  const isOperator = userRole === 'operator' || userRole === 'admin';
  const isAdmin = userRole === 'admin';

  const totalContainers = containers.length;
  const runningContainers = containers.filter(c => c.status === 'running' || c.status?.toLowerCase().includes('up')).length;
  const critAlerts = alerts.filter(a => a.severity === 'critical' && !a.healed).length;

  if (!token) {
    return (
      <LoginScreen
        onLoginSuccess={(tok, user) => {
          setToken(tok);
          setCurrentUser(user);
        }}
      />
    );
  }

  return (
    <div className="app-container">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            <Activity size={20} />
          </div>
          <div>
            <div className="brand-title">DockerMind</div>
            <div className="text-xs text-dim">Autonomous AI SRE</div>
          </div>
        </div>

        <nav className="nav-links">
          <div className={`nav-item ${activeTab === 'fleet' ? 'active' : ''}`} onClick={() => setActiveTab('fleet')}>
            <Box size={18} />
            <span>Fleet & Nodes</span>
          </div>
          <div className={`nav-item ${activeTab === 'logs' ? 'active' : ''}`} onClick={() => setActiveTab('logs')}>
            <Terminal size={18} />
            <span>AI Logs & Terminal</span>
          </div>
          <div className={`nav-item ${activeTab === 'incidents' ? 'active' : ''}`} onClick={() => setActiveTab('incidents')}>
            <AlertTriangle size={18} />
            <span>Incidents & Backoff</span>
            {critAlerts > 0 && <span className="badge badge-crit text-xs" style={{ marginLeft: 'auto' }}>{critAlerts}</span>}
          </div>
          <div className={`nav-item ${activeTab === 'dispatch' ? 'active' : ''}`} onClick={() => setActiveTab('dispatch')}>
            <Sliders size={18} />
            <span>Fleet Dispatch</span>
          </div>
          <div className={`nav-item ${activeTab === 'runbooks' ? 'active' : ''}`} onClick={() => setActiveTab('runbooks')}>
            <ListOrdered size={18} />
            <span>Automated Runbooks</span>
          </div>
          <div className={`nav-item ${activeTab === 'audit' ? 'active' : ''}`} onClick={() => setActiveTab('audit')}>
            <FileText size={18} />
            <span>Audit & Jobs</span>
          </div>
          <div className={`nav-item ${activeTab === 'chat' ? 'active' : ''}`} onClick={() => setActiveTab('chat')}>
            <Sparkles size={18} />
            <span>AI DevOps Assistant</span>
          </div>
        </nav>

        <div style={{ marginTop: 'auto', borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <div className="text-xs text-muted">Role: <span className="badge badge-cyan">{currentUser?.role || 'admin'}</span></div>
            <div className="text-xs font-mono text-dim">{currentUser?.username || 'admin'}</div>
          </div>
          <button className="btn btn-secondary btn-sm" style={{ width: '100%', marginBottom: '0.5rem' }} onClick={refreshAll}>
            <RefreshCw size={14} /> Refresh Cluster
          </button>
          <button className="btn btn-secondary btn-sm" style={{ width: '100%', color: 'var(--rose-400)', borderColor: 'rgba(239, 68, 68, 0.3)' }} onClick={handleLogout}>
            <LogOut size={14} /> Logout
          </button>
        </div>
      </aside>

      {/* ── Main Workspace ── */}
      <div className="main-content">
        {/* Top Header Bar */}
        <header className="top-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span className={`live-dot ${wsConnected ? '' : 'style-offline'}`} style={{ background: wsConnected ? 'var(--emerald-400)' : 'var(--rose-400)' }} />
              <span className="text-xs font-mono font-semibold" style={{ color: wsConnected ? 'var(--emerald-400)' : 'var(--rose-400)' }}>
                {wsConnected ? 'LIVE FEED ACTIVE' : 'RECONNECTING WS...'}
              </span>
            </div>
            {lastPing && <div className="text-xs font-mono text-dim">Sync: {lastPing}</div>}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div className="badge badge-ok">Slaves: {slaves.length || 1} Online</div>
            <div className="badge badge-cyan">Containers: {runningContainers} / {totalContainers} Running</div>
            {critAlerts > 0 && <div className="badge badge-crit">{critAlerts} Critical Incidents</div>}
            {isOperator && (
              <button className="btn btn-primary btn-sm" onClick={() => setDispatchModalOpen(true)}>
                <Sliders size={14} /> Fleet Command
              </button>
            )}
          </div>
        </header>

        {/* Dynamic Content Views */}
        <main className="content-body">
          {/* ── TAB 1: FLEET & NODES ── */}
          {activeTab === 'fleet' && (
            <div>
              {/* Top Metrics Row */}
              <div className="grid grid-cols-4 gap-4 mb-6">
                <div className="card-glass">
                  <div className="text-xs text-muted mb-2 flex items-center justify-between">
                    <span>CONNECTED SLAVES</span>
                    <Server size={16} className="text-cyan" />
                  </div>
                  <div className="text-2xl font-bold font-mono">{slaves.length}</div>
                  <div className="text-xs text-emerald mt-1">mTLS Secured</div>
                </div>

                <div className="card-glass">
                  <div className="text-xs text-muted mb-2 flex items-center justify-between">
                    <span>ACTIVE CONTAINERS</span>
                    <Box size={16} className="text-cyan" />
                  </div>
                  <div className="text-2xl font-bold font-mono">{runningContainers} <span className="text-sm text-dim">/ {totalContainers}</span></div>
                  <div className="text-xs text-muted mt-1">{totalContainers - runningContainers} stopped / exited</div>
                </div>

                <div className="card-glass">
                  <div className="text-xs text-muted mb-2 flex items-center justify-between">
                    <span>CRASH LOOPS</span>
                    <RefreshCw size={16} className="text-amber" />
                  </div>
                  <div className="text-2xl font-bold font-mono text-amber">{crashLoops.length}</div>
                  <div className="text-xs text-muted mt-1">5-min sliding window</div>
                </div>

                <div className="card-glass">
                  <div className="text-xs text-muted mb-2 flex items-center justify-between">
                    <span>UNHEALED ALERTS</span>
                    <AlertTriangle size={16} className="text-rose" />
                  </div>
                  <div className="text-2xl font-bold font-mono text-rose">{critAlerts}</div>
                  <div className="text-xs text-rose mt-1">Needs attention</div>
                </div>
              </div>

              {/* Cluster Architecture & Topology Map (Phase 4) */}
              <ClusterTopologyMap
                slaves={slaves}
                masterStats={masterHostStats}
                selectedNodeFilter={selectedNodeFilter}
                onSelectNode={setSelectedNodeFilter}
                containers={containers}
              />

              {/* Slaves Node Cards */}
              <div className="mb-6">
                <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
                  <Server size={18} className="text-cyan" /> Registered Host Nodes
                </h3>
                <div className="grid grid-cols-2 gap-4">
                  {/* Master Node Card */}
                  <div className="card-glass" style={{ borderLeft: '4px solid var(--emerald-400)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div className="font-semibold text-base flex items-center gap-2">
                          <Server size={16} className="text-emerald" /> master (local)
                        </div>
                        <div className="text-xs text-dim font-mono">127.0.0.1:8000 • Master Controller</div>
                      </div>
                      <span className="badge badge-ok">HEALTHY</span>
                    </div>
                    {renderHostGauges(masterHostStats, true)}
                  </div>

                  {/* Registered Slave Node Cards */}
                  {slaves.map((slave) => {
                    const isOnline = slave.is_online || slave.status === 'online';
                    const tagList = Array.isArray(slave.tags) ? slave.tags.join(', ') : (slave.tags || 'worker');
                    return (
                      <div key={slave.slave_id} className="card-glass" style={{ borderLeft: `4px solid ${isOnline ? 'var(--cyan-400)' : 'var(--rose-400)'}` }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <div className="font-semibold text-base flex items-center gap-2">
                              <Radio size={16} className={isOnline ? 'text-cyan' : 'text-rose'} /> {slave.slave_id}
                            </div>
                            <div className="text-xs text-dim font-mono">{slave.ip || slave.address || 'localhost'}:{slave.port || 8080} • Containers: {slave.container_count ?? 0} • Tags: {tagList}</div>
                          </div>
                          <span className={`badge ${isOnline ? 'badge-ok' : 'badge-error'}`}>
                            {isOnline ? 'ONLINE' : 'OFFLINE'}
                          </span>
                        </div>
                        {renderHostGauges(slave.host_stats, isOnline)}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Containers Fleet Table */}
              <div className="card-glass">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <h3 className="text-base font-semibold flex items-center gap-2">
                    <Box size={18} className="text-cyan" /> Container Fleet Telemetry & Quick Actions
                  </h3>
                  <div className="text-xs text-dim">Real-time stats updating every 30s</div>
                </div>

                <div className="table-container">
                  <table>
                    <thead>
                      <tr>
                        <th>Container</th>
                        <th>Image</th>
                        <th>Status</th>
                        <th>CPU Usage</th>
                        <th>Memory Utilization</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {containers
                        .filter(c => {
                          if (!selectedNodeFilter) return true;
                          if (selectedNodeFilter === 'local') return !c.slave_id || c.slave_id === 'local';
                          return c.slave_id === selectedNodeFilter;
                        })
                        .map((c) => {
                          const stats = statsMap[c.name] || {};
                          const cpu = stats.cpu_pct || 0;
                          const memPct = stats.mem_pct || 0;
                          const memUsed = stats.mem_used_mb || 0;
                          const memLimit = stats.mem_limit_mb || 0;
                          const isRunning = c.status === 'running' || c.status?.toLowerCase().includes('up');
                          const cMetrics = metricsSummary?.containers?.[c.name] || {};
                          const cpuHistory = cMetrics.cpu && cMetrics.cpu.length > 0 ? cMetrics.cpu : [cpu];
                          const memHistory = cMetrics.mem_pct && cMetrics.mem_pct.length > 0 ? cMetrics.mem_pct : [memPct];

                          return (
                            <tr key={c.id || c.name}>
                              <td>
                                <div className="font-semibold font-mono text-cyan">{c.name}</div>
                                <div className="text-xs text-dim font-mono">{c.id?.substring(0, 12)}</div>
                              </td>
                              <td className="font-mono text-xs text-muted">{c.image}</td>
                              <td>
                                <span className={`badge ${isRunning ? 'badge-ok' : 'badge-error'}`}>
                                  {c.status}
                                </span>
                              </td>
                              <td style={{ width: '200px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.2rem' }}>
                                  <span className="text-xs font-mono font-bold text-cyan">{cpu.toFixed(1)}%</span>
                                  <Sparkline data={cpuHistory} color="var(--cyan-400)" width={95} height={20} unit="%" />
                                </div>
                                <div className="progress-bar-bg">
                                  <div className={`progress-bar-fill ${cpu > 80 ? 'fill-rose' : 'fill-emerald'}`} style={{ width: `${Math.min(100, cpu)}%` }} />
                                </div>
                              </td>
                              <td style={{ width: '240px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.2rem' }}>
                                  <div className="text-xs font-mono">
                                    <span className="font-bold text-violet">{memPct.toFixed(1)}%</span>
                                    <span className="text-dim ml-1" style={{ fontSize: '0.7rem' }}>({memUsed > 0 ? `${memUsed.toFixed(0)}MB` : '—'})</span>
                                  </div>
                                  <Sparkline data={memHistory} color="var(--violet-400)" width={95} height={20} unit="%" />
                                </div>
                                <div className="progress-bar-bg" style={{ marginBottom: cMetrics.leak_risk ? '0.25rem' : '0' }}>
                                  <div
                                    className={`progress-bar-fill ${memPct > 90 ? 'fill-rose' : memPct > 80 ? 'fill-amber' : 'fill-emerald'}`}
                                    style={{ width: `${Math.min(100, memPct)}%` }}
                                  />
                                </div>
                                {cMetrics.leak_risk && (
                                  <span className="badge badge-warn text-xs" style={{ fontSize: '0.65rem', padding: '0.1rem 0.4rem' }}>
                                    📈 +{cMetrics.mem_trend_mb_hr} MB/hr (Leak Risk)
                                  </span>
                                )}
                              </td>
                            <td>
                              <div style={{ display: 'flex', gap: '0.4rem' }}>
                                <button
                                  className="btn btn-secondary btn-sm"
                                  title="Inspect Logs"
                                  onClick={() => {
                                    setSelectedContainer(c.name);
                                    setActiveTab('logs');
                                  }}
                                >
                                  <Terminal size={12} />
                                </button>
                                {isOperator && (
                                  <button
                                    className="btn btn-secondary btn-sm"
                                    title="Restart Container"
                                    onClick={() => apiFetch(`/containers/${c.name}/restart`, { method: 'POST' }).then(() => addToast('ok', 'Restarted', c.name))}
                                  >
                                    <RotateCw size={12} />
                                  </button>
                                )}
                                {isOperator && (
                                  <button
                                    className="btn btn-ai btn-sm"
                                    title="Diagnose & Heal Container with AI"
                                    onClick={() => openHealModal(c.name, 'local')}
                                  >
                                    <Zap size={12} /> Heal
                                  </button>
                                )}
                                {isAdmin && (
                                  <button
                                    className="btn btn-secondary btn-sm"
                                    title="Execute Command (Admin Only)"
                                    onClick={() => {
                                      setExecTargetContainer(c.name);
                                      setExecModalOpen(true);
                                    }}
                                  >
                                    <Sliders size={12} />
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ── TAB 2: AI LOGS & TERMINAL ── */}
          {activeTab === 'logs' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <span className="text-sm text-muted">Select Target Container:</span>
                  <select
                    className="input-field"
                    style={{ width: '220px' }}
                    value={selectedContainer}
                    onChange={(e) => setSelectedContainer(e.target.value)}
                  >
                    {containers.map(c => (
                      <option key={c.name} value={c.name}>{c.name}</option>
                    ))}
                  </select>
                </div>

                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <button className="btn btn-secondary btn-sm" onClick={() => fetchLogs(selectedContainer)}>
                    <RefreshCw size={14} /> Refresh Logs
                  </button>
                  <button className="btn btn-ai btn-sm" onClick={() => runAiAnalysis(selectedContainer)} disabled={analyzing}>
                    <Sparkles size={14} /> {analyzing ? 'AI Diagnosing...' : 'Run LLM Diagnosis'}
                  </button>
                </div>
              </div>

              {/* AI Diagnosis Result Card */}
              {aiAnalysis && (
                <div className={`card-glass mb-6 ${aiAnalysis.severity === 'critical' || aiAnalysis.severity === 'error' ? 'alert-crit' : ''}`} style={{ borderLeft: '4px solid var(--violet-400)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <Sparkles size={18} className="text-violet" />
                      <span className="font-semibold text-base">DockerMind AI Incident Diagnosis</span>
                    </div>
                    <span className={`badge badge-${aiAnalysis.severity}`}>
                      {aiAnalysis.severity}
                    </span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '0.5rem' }}>
                    <div>
                      <div className="text-xs font-semibold text-muted uppercase">Root Cause</div>
                      <div className="text-sm font-medium mt-1 text-main">{aiAnalysis.root_cause || 'No critical anomalies detected.'}</div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-muted uppercase">Recommended Remediation</div>
                      <div className="text-sm font-medium mt-1 text-cyan">{aiAnalysis.fix || 'No action needed.'}</div>
                    </div>
                  </div>

                  {aiAnalysis.auto_heal && isOperator && (
                    <div style={{ marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span className="text-xs text-emerald flex items-center gap-1">
                        <CheckCircle2 size={14} /> Safe for Automated Remediation ({aiAnalysis.heal_action})
                      </span>
                      <button className="btn btn-ai btn-sm" onClick={() => triggerAutoHeal(selectedContainer, 'local', aiAnalysis.heal_action)}>
                        Execute Recommended Action ({aiAnalysis.heal_action})
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Terminal Viewer */}
              <div className="terminal-window">
                <div className="terminal-header">
                  <div className="terminal-dots">
                    <span className="dot dot-red" />
                    <span className="dot dot-yellow" />
                    <span className="dot dot-green" />
                  </div>
                  <div className="text-xs text-dim font-mono">stdout/stderr: {selectedContainer} (last 80 lines)</div>
                  <div className="text-xs text-dim">ASCII Live Output</div>
                </div>
                <div className="terminal-body font-mono">
                  {containerLogs || 'Loading logs...'}
                </div>
              </div>
            </div>
          )}

          {/* ── TAB 3: INCIDENTS & CIRCUIT BREAKER ── */}
          {activeTab === 'incidents' && (
            <div>
              <div className="mb-6">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <h3 className="text-base font-semibold flex items-center gap-2">
                    <RefreshCw size={18} className="text-amber" /> Active Crash Loops & Circuit Breakers (Task 2 & 3)
                  </h3>
                  <button className="btn btn-secondary btn-sm" onClick={openWebhookModal}>
                    <Radio size={14} className="text-violet" /> Alerting & Webhooks
                  </button>
                </div>

                {crashLoops.length === 0 ? (
                  <div className="card-glass" style={{ textAlign: 'center', padding: '2rem' }}>
                    <CheckCircle2 size={32} className="text-emerald" style={{ margin: '0 auto 0.5rem' }} />
                    <div className="font-semibold text-base">No Active Crash Loops Detected</div>
                    <div className="text-xs text-dim">All containers are operating within stable parameters in the 5-minute window.</div>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-4">
                    {crashLoops.map((cl, i) => (
                      <div key={i} className="card-glass alert-crit">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <div>
                            <div className="font-mono font-bold text-base text-rose">{cl.container}</div>
                            <div className="text-xs text-dim font-mono">Node: {cl.slave_id}</div>
                          </div>
                          <span className={`badge ${cl.is_crash_loop ? 'badge-crit' : 'badge-warn'}`}>
                            {cl.is_crash_loop ? 'CRASH LOOP ACTIVE' : 'UNSTABLE'}
                          </span>
                        </div>

                        <div style={{ marginTop: '0.75rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.8rem' }}>
                          <div>Restarts in 5m: <span className="font-mono font-bold text-amber">{cl.restarts_in_window}</span></div>
                          <div>OOM Incidents: <span className="font-mono font-bold text-rose">{cl.oom_count || 0}</span></div>
                        </div>

                        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
                          {isOperator ? (
                            <>
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => resetCircuitBreaker(cl.slave_id, cl.container)}
                              >
                                Reset Circuit Breaker
                              </button>
                              <button
                                className="btn btn-ai btn-sm"
                                title="Diagnose & Heal Incident with AI"
                                onClick={() => openHealModal(cl.container, cl.slave_id)}
                              >
                                <Zap size={12} /> AI Diagnosis & Heal
                              </button>
                            </>
                          ) : (
                            <span className="badge badge-secondary text-xs" style={{ padding: '0.35rem 0.65rem' }}>
                              Observation Mode (Operator required for manual reset)
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Alerts Log */}
              <div className="card-glass">
                <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
                  <AlertTriangle size={18} className="text-cyan" /> Incident Alerts & Remediation Feed
                </h3>

                <div className="table-container">
                  <table>
                    <thead>
                      <tr>
                        <th>Severity</th>
                        <th>Target Container</th>
                        <th>Root Cause Diagnosis</th>
                        <th>Recommended Fix</th>
                        <th>Status</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {alerts.map((a) => (
                        <tr key={a.alert_id}>
                          <td>
                            <span className={`badge badge-${a.severity}`}>
                              {a.severity}
                            </span>
                          </td>
                          <td className="font-mono font-bold text-xs">{a.container_name}</td>
                          <td className="text-sm">{a.root_cause}</td>
                          <td className="text-sm text-cyan">{a.fix}</td>
                          <td>
                            <span className={`badge ${a.healed ? 'badge-ok' : 'badge-error'}`}>
                              {a.healed ? 'RESOLVED' : 'UNRESOLVED'}
                            </span>
                          </td>
                          <td>
                            {!a.healed ? (
                              isOperator ? (
                                <button
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => acknowledgeAlert(a.alert_id)}
                                >
                                  Acknowledge
                                </button>
                              ) : (
                                <span className="badge badge-secondary text-xs">VIEW ONLY</span>
                              )
                            ) : null}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ── TAB 4: FLEET DISPATCHER (TASK 4) ── */}
          {activeTab === 'dispatch' && (
            <div>
              <div className="card-glass mb-6">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                  <div>
                    <h3 className="text-base font-semibold flex items-center gap-2">
                      <Sliders size={18} className="text-cyan" /> Multi-Slave Fleet Command Dispatch
                    </h3>
                    <div className="text-xs text-dim">Broadcast Docker operations simultaneously across all or filtered nodes via asyncio.gather</div>
                  </div>
                  {!isOperator && (
                    <div className="badge badge-warn text-xs" style={{ padding: '0.4rem 0.8rem' }}>
                      READ-ONLY: Dispatch requires Operator or Admin role
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-3 gap-4 mb-4">
                  <div>
                    <label className="text-xs text-muted block mb-1">Target Nodes</label>
                    <select
                      className="input-field"
                      value={dispatchTarget}
                      onChange={(e) => setDispatchTarget(e.target.value)}
                    >
                      <option value="all">Broadcast: All Active Slaves + Local</option>
                      <option value="local">Master Host (local)</option>
                      {slaves.map(s => (
                        <option key={s.slave_id} value={s.slave_id}>{s.slave_id} ({s.ip})</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-xs text-muted block mb-1">Action Type</label>
                    <select
                      className="input-field"
                      value={dispatchAction}
                      onChange={(e) => setDispatchAction(e.target.value)}
                    >
                      <option value="log_check">log_check (Collect Health & Logs)</option>
                      <option value="restart">restart (Rolling Container Restart)</option>
                      <option value="exec">exec (Execute Shell Command)</option>
                      <option value="stop">stop (Graceful Shutdown)</option>
                      <option value="start">start (Spin Up Container)</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-xs text-muted block mb-1">Container Name</label>
                    <input
                      type="text"
                      className="input-field"
                      placeholder="e.g. dockermind-master"
                      value={dispatchContainer}
                      onChange={(e) => setDispatchContainer(e.target.value)}
                    />
                  </div>
                </div>

                {dispatchAction === 'exec' && (
                  <div className="mb-4">
                    <label className="text-xs text-muted block mb-1">Command to Execute</label>
                    <input
                      type="text"
                      className="input-field font-mono"
                      value={dispatchCommand}
                      onChange={(e) => setDispatchCommand(e.target.value)}
                    />
                  </div>
                )}

                <button
                  className="btn btn-primary"
                  onClick={handleFleetDispatch}
                  disabled={dispatching || !dispatchContainer || !isOperator}
                  title={!isOperator ? "Requires Operator or Admin role" : ""}
                >
                  <Send size={14} /> {dispatching ? 'Broadcasting Fleet Commands...' : 'Dispatch to Fleet Now'}
                </button>
              </div>

              {/* Execution Summary Cards */}
              {dispatchResult && (
                <div className="card-glass">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                    <div className="font-semibold text-base">Fleet Dispatch Execution Outcome</div>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <span className="badge badge-ok">{dispatchResult.successful} Successful</span>
                      {dispatchResult.failed > 0 && <span className="badge badge-error">{dispatchResult.failed} Failed</span>}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    {Object.entries(dispatchResult.nodes || {}).map(([nodeId, res]) => (
                      <div key={nodeId} className="card-glass" style={{ borderLeft: `4px solid ${res.success ? 'var(--emerald-400)' : 'var(--rose-400)'}` }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                          <span className="font-bold font-mono text-cyan">{nodeId}</span>
                          <span className={`badge ${res.success ? 'badge-ok' : 'badge-error'}`}>{res.success ? 'SUCCESS' : 'FAILED'}</span>
                        </div>
                        <div className="terminal-window" style={{ height: '140px' }}>
                          <div className="terminal-body font-mono text-xs" style={{ height: '100%', padding: '0.5rem' }}>
                            {res.output || res.error || JSON.stringify(res, null, 2)}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── TAB 4.5: AUTOMATED RUNBOOKS (Phase 3) ── */}
          {activeTab === 'runbooks' && (
            <div>
              <div className="card-glass mb-6">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                  <div>
                    <h3 className="text-base font-semibold flex items-center gap-2">
                      <ListOrdered size={18} className="text-cyan" /> Automated Remediation Runbooks (Phase 3)
                    </h3>
                    <div className="text-xs text-dim">Pre-flight verification, exponential retry backoff, and strict stop_on_failure execution policies</div>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    {isAdmin && (
                      <button className="btn btn-secondary btn-sm" onClick={() => setCreateRbModalOpen(true)}>
                        + Create Runbook
                      </button>
                    )}
                    <button className="btn btn-secondary btn-sm" onClick={openWebhookModal}>
                      <Radio size={14} className="text-violet" /> Webhook Alerting
                    </button>
                  </div>
                </div>

                {/* Runbooks Listing Grid */}
                <div className="grid grid-cols-3 gap-4 mb-6">
                  {runbooks.map((rb) => {
                    const isSelected = selectedRunbookId === rb.id;
                    const steps = typeof rb.steps === 'string' ? JSON.parse(rb.steps || '[]') : (rb.steps || []);
                    return (
                      <div
                        key={rb.id}
                        className={`card-glass cursor-pointer ${isSelected ? 'border-cyan' : ''}`}
                        style={{
                          padding: '1rem',
                          background: isSelected ? 'rgba(6, 182, 212, 0.08)' : 'rgba(15, 23, 42, 0.5)',
                          borderColor: isSelected ? 'var(--cyan-400)' : 'var(--border-subtle)',
                          transition: 'all 0.2s',
                        }}
                        onClick={() => setSelectedRunbookId(rb.id)}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                          <span className="font-semibold text-sm text-cyan">{rb.name}</span>
                          <span className="badge badge-secondary text-xs">{rb.trigger || 'manual'}</span>
                        </div>
                        <div className="text-xs text-muted mb-3" style={{ minHeight: '32px' }}>
                          {rb.description || 'No description provided.'}
                        </div>

                        {/* Policy Badges */}
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '0.75rem' }}>
                          <span className={`badge ${rb.stop_on_failure !== 0 ? 'badge-warn' : 'badge-secondary'}`} style={{ fontSize: '0.65rem' }}>
                            {rb.stop_on_failure !== 0 ? 'STOP ON FAILURE: YES' : 'STOP ON FAILURE: NO'}
                          </span>
                          <span className="badge badge-ok" style={{ fontSize: '0.65rem' }}>
                            RETRIES: {rb.retry_count !== undefined ? rb.retry_count : 1}
                          </span>
                          <span className="badge badge-secondary" style={{ fontSize: '0.65rem' }}>
                            {steps.length} STEPS
                          </span>
                        </div>

                        <div className="text-xs text-dim font-mono" style={{ fontSize: '0.7rem' }}>
                          Runs: {rb.run_count || 0} • Last: {rb.last_run ? new Date(rb.last_run * 1000).toLocaleTimeString() : 'Never'}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Selected Runbook Execution Console */}
                {(() => {
                  const currentRb = runbooks.find(r => r.id === selectedRunbookId);
                  if (!currentRb) return null;
                  const currentSteps = typeof currentRb.steps === 'string' ? JSON.parse(currentRb.steps || '[]') : (currentRb.steps || []);

                  return (
                    <div className="p-4 rounded" style={{ background: 'rgba(15,23,42,0.7)', border: '1px solid var(--border-subtle)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                        <div>
                          <div className="font-bold text-sm text-cyan flex items-center gap-2">
                            <span>Target Execution:</span> <span className="text-slate-200">{currentRb.name}</span>
                          </div>
                          <div className="text-xs text-dim">{currentRb.description}</div>
                        </div>
                        {!isOperator && (
                          <span className="badge badge-warn text-xs">Read-Only: Operator role required to execute</span>
                        )}
                      </div>

                      {/* Step Pipeline Visualization */}
                      <div className="mb-4">
                        <label className="text-xs text-muted block mb-2">Step Execution Pipeline ({currentSteps.length} steps):</label>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', overflowX: 'auto', paddingBottom: '0.5rem' }}>
                          {currentSteps.map((s, idx) => (
                            <React.Fragment key={idx}>
                              <div className="p-2 rounded text-xs" style={{ background: 'rgba(30,41,59,0.8)', border: '1px solid #334155', minWidth: '160px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                                  <span className="font-mono text-cyan font-bold">Step {idx + 1}</span>
                                  <span className="badge badge-secondary text-xs">{s.type}</span>
                                </div>
                                <div className="text-slate-300 font-medium truncate">{s.description || s.type}</div>
                                {s.optional && <div className="text-dim text-xs mt-1">Optional step</div>}
                              </div>
                              {idx < currentSteps.length - 1 && <ChevronRight size={16} className="text-dim" />}
                            </React.Fragment>
                          ))}
                        </div>
                      </div>

                      {/* Execution Targets & Policy Overrides */}
                      <div className="grid grid-cols-4 gap-4 mb-4">
                        <div>
                          <label className="text-xs text-muted block mb-1">Target Node</label>
                          <select
                            className="input-field"
                            value={rbTargetSlave}
                            onChange={(e) => setRbTargetSlave(e.target.value)}
                          >
                            <option value="local">Master Host (local)</option>
                            {slaves.map(s => (
                              <option key={s.slave_id} value={s.slave_id}>{s.slave_id} ({s.ip})</option>
                            ))}
                          </select>
                        </div>

                        <div>
                          <label className="text-xs text-muted block mb-1">Target Container</label>
                          <select
                            className="input-field"
                            value={rbTargetContainer}
                            onChange={(e) => setRbTargetContainer(e.target.value)}
                          >
                            {containers.map(c => (
                              <option key={c.name} value={c.name}>{c.name} ({c.status})</option>
                            ))}
                          </select>
                        </div>

                        <div>
                          <label className="text-xs text-muted block mb-1">Stop on Failure</label>
                          <select
                            className="input-field"
                            value={rbStopOnFailure ? 'yes' : 'no'}
                            onChange={(e) => setRbStopOnFailure(e.target.value === 'yes')}
                          >
                            <option value="yes">Enabled (Halt immediately on step error)</option>
                            <option value="no">Disabled (Continue through remaining steps)</option>
                          </select>
                        </div>

                        <div>
                          <label className="text-xs text-muted block mb-1">Step Retry Count</label>
                          <select
                            className="input-field"
                            value={rbRetryCount}
                            onChange={(e) => setRbRetryCount(parseInt(e.target.value, 10))}
                          >
                            <option value="0">0 (Fail immediately, no retries)</option>
                            <option value="1">1 Retry (1.5s exponential backoff)</option>
                            <option value="2">2 Retries (1.5s, 3.0s backoff)</option>
                            <option value="3">3 Retries (1.5s, 3.0s, 4.5s backoff)</option>
                          </select>
                        </div>
                      </div>

                      <button
                        className="btn btn-primary"
                        disabled={rbExecuting || !isOperator}
                        onClick={() => handleExecuteRunbook(currentRb.id)}
                      >
                        <Play size={14} /> {rbExecuting ? 'Executing Runbook Pipeline...' : `Execute ${currentRb.name} Now`}
                      </button>
                    </div>
                  );
                })()}
              </div>

              {/* Execution Outcome & Step Trace */}
              {rbExecutionResult && (
                <div className="card-glass">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                    <div>
                      <div className="font-semibold text-base flex items-center gap-2">
                        {rbExecutionResult.success ? (
                          <CheckCircle2 size={18} className="text-emerald" />
                        ) : (
                          <XCircle size={18} className="text-rose" />
                        )}
                        <span>Runbook Execution: {rbExecutionResult.runbook_name}</span>
                      </div>
                      <div className="text-xs text-dim">
                        Target: <span className="text-cyan font-mono">{rbExecutionResult.container}</span> on node <span className="font-mono">{rbExecutionResult.slave_id}</span>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      {rbExecutionResult.stopped_on_failure && (
                        <span className="badge badge-warn text-xs">STOPPED ON FAILURE</span>
                      )}
                      <span className={`badge ${rbExecutionResult.success ? 'badge-ok' : 'badge-crit'}`}>
                        {rbExecutionResult.success ? 'PIPELINE PASSED' : 'PIPELINE FAILED'}
                      </span>
                    </div>
                  </div>

                  {rbExecutionResult.stopped_on_failure && (
                    <div className="alert-crit p-3 rounded mb-4" style={{ fontSize: '0.8rem' }}>
                      ⚠️ <strong>Stop on Failure Policy Enforced:</strong> Step execution was halted immediately upon step failure to prevent cascading cluster damage. Subsequent steps were safely aborted.
                    </div>
                  )}

                  <div className="grid grid-cols-1 gap-3">
                    {rbExecutionResult.steps?.map((stepItem) => (
                      <div
                        key={stepItem.step}
                        className="card-glass"
                        style={{
                          borderLeft: `4px solid ${stepItem.success ? 'var(--emerald-400)' : 'var(--rose-400)'}`,
                          padding: '0.85rem 1rem',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                          <div className="font-mono text-sm font-semibold flex items-center gap-2">
                            <span>Step {stepItem.step}:</span>
                            <span className="text-cyan">{stepItem.description}</span>
                            <span className="badge badge-secondary text-xs">{stepItem.type}</span>
                          </div>
                          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                            <span className="text-xs text-dim font-mono">Attempts: {stepItem.attempts}</span>
                            <span className={`badge ${stepItem.success ? 'badge-ok' : 'badge-error'}`}>
                              {stepItem.success ? 'SUCCESS' : 'FAILED'}
                            </span>
                          </div>
                        </div>

                        <div className="terminal-window" style={{ height: '70px' }}>
                          <div className="terminal-body font-mono text-xs" style={{ padding: '0.4rem 0.6rem' }}>
                            {JSON.stringify(stepItem.result, null, 2)}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── TAB 5: AUDIT & JOBS ── */}
          {activeTab === 'audit' && (
            <div>
              <div className="card-glass mb-6">
                <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
                  <FileText size={18} className="text-cyan" /> Immutable Audit Trail (SQLite WAL)
                </h3>
                <div className="table-container">
                  <table>
                    <thead>
                      <tr>
                        <th>Timestamp</th>
                        <th>User / Actor</th>
                        <th>Action</th>
                        <th>Target Container / Node</th>
                        <th>Execution Result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditLogs.map((log) => (
                        <tr key={log.id}>
                          <td className="text-xs font-mono text-dim">
                            {new Date(log.ts * 1000).toLocaleString()}
                          </td>
                          <td className="font-mono text-xs text-cyan">{log.user}</td>
                          <td>
                            <span className="badge badge-cyan">{log.action}</span>
                          </td>
                          <td className="font-mono text-xs">{log.target || log.container || 'cluster'}</td>
                          <td className="text-xs font-mono text-muted" style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {log.result}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Scheduled Jobs */}
              <div className="card-glass">
                <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
                  <Clock size={18} className="text-cyan" /> Background Maintenance & Scheduled Jobs
                </h3>
                <div className="table-container">
                  <table>
                    <thead>
                      <tr>
                        <th>Job ID</th>
                        <th>Name</th>
                        <th>Action</th>
                        <th>Target Node</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobs.map((j) => (
                        <tr key={j.id}>
                          <td className="font-mono text-xs text-dim">{j.id}</td>
                          <td className="font-medium text-sm">{j.name}</td>
                          <td><span className="badge badge-cyan">{j.type}</span></td>
                          <td className="font-mono text-xs">{j.slave_id} ({j.container})</td>
                          <td>
                            <span className={`badge ${j.status === 'done' ? 'badge-ok' : j.status === 'failed' ? 'badge-error' : 'badge-warn'}`}>
                              {j.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ── TAB 6: AI DEVOPS ASSISTANT (CHAT) ── */}
          {activeTab === 'chat' && (
            <div style={{ maxWidth: '900px', margin: '0 auto' }}>
              <div className="card-glass" style={{ height: '620px', display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', paddingBottom: '1rem', borderBottom: '1px solid var(--border-subtle)' }}>
                  <Sparkles size={20} className="text-violet" />
                  <div>
                    <div className="font-bold text-base">DockerMind AI DevOps SRE Assistant</div>
                    <div className="text-xs text-dim">Powered by Google Gemini 2.5 Flash & OpenRouter</div>
                  </div>
                </div>

                {/* Message Flow */}
                <div style={{ flex: 1, overflowY: 'auto', padding: '1rem 0', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  {chatMessages.map((msg, i) => (
                    <div
                      key={i}
                      style={{
                        alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                        maxWidth: '80%',
                        background: msg.role === 'user' ? 'linear-gradient(135deg, #0284c7, #0ea5e9)' : '#1e293b',
                        padding: '0.85rem 1.15rem',
                        borderRadius: '12px',
                        fontSize: '0.875rem',
                        lineHeight: '1.6',
                        border: msg.role === 'user' ? 'none' : '1px solid #334155',
                        boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
                      }}
                    >
                      <div className="text-xs font-semibold mb-1" style={{ color: msg.role === 'user' ? '#e0f2fe' : 'var(--violet-400)' }}>
                        {msg.role === 'user' ? 'You (DevOps Operator)' : 'DockerMind AI Assistant'}
                      </div>
                      <div style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</div>
                    </div>
                  ))}
                  {chatLoading && (
                    <div style={{ alignSelf: 'flex-start', background: '#1e293b', padding: '0.75rem 1.25rem', borderRadius: '12px', fontSize: '0.85rem' }}>
                      <span className="text-violet flex items-center gap-2">
                        <Sparkles size={14} className="animate-spin" /> Thinking...
                      </span>
                    </div>
                  )}
                </div>

                {/* Suggested Prompts */}
                <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem', overflowX: 'auto', paddingBottom: '0.25rem' }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    style={{ fontSize: '0.75rem', whiteSpace: 'nowrap' }}
                    onClick={() => setChatInput('What causes a container to exit with code 137, and how to debug it?')}
                  >
                    Diagnose Exit 137 OOM
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    style={{ fontSize: '0.75rem', whiteSpace: 'nowrap' }}
                    onClick={() => setChatInput('How does DockerMind exponential backoff prevent crash-loop thrashing?')}
                  >
                    Explain Exponential Backoff
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    style={{ fontSize: '0.75rem', whiteSpace: 'nowrap' }}
                    onClick={() => setChatInput('How to inspect memory leaks in Docker containers?')}
                  >
                    Memory Leak Checklist
                  </button>
                </div>

                {/* Input Bar */}
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="Ask DockerMind assistant anything about your cluster or containers..."
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && sendChatMessage()}
                  />
                  <button className="btn btn-ai" onClick={sendChatMessage} disabled={chatLoading}>
                    <Send size={16} />
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* ── Fleet Dispatch Modal ── */}
      {dispatchModalOpen && (
        <div className="modal-overlay" onClick={() => setDispatchModalOpen(false)}>
          <div className="modal-content card-glass" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <h3 className="text-base font-semibold flex items-center gap-2">
                <Sliders size={18} className="text-cyan" /> Multi-Slave Fleet Dispatch
              </h3>
              <button className="btn btn-secondary btn-sm" onClick={() => setDispatchModalOpen(false)}>✕</button>
            </div>

            <div className="mb-4">
              <label className="text-xs text-muted block mb-1">Target Nodes</label>
              <select className="input-field" value={dispatchTarget} onChange={(e) => setDispatchTarget(e.target.value)}>
                <option value="all">Broadcast to All Online Slaves + Local</option>
                <option value="local">Local Master Host Only</option>
                {slaves.map(s => (
                  <option key={s.slave_id} value={s.slave_id}>{s.slave_id} ({s.ip})</option>
                ))}
              </select>
            </div>

            <div className="mb-4">
              <label className="text-xs text-muted block mb-1">Action Type</label>
              <select className="input-field" value={dispatchAction} onChange={(e) => setDispatchAction(e.target.value)}>
                <option value="log_check">log_check (Health Probe & Log Sample)</option>
                <option value="restart">restart (Rolling Restart)</option>
                <option value="stop">stop (Graceful Stop)</option>
                <option value="start">start (Start Container)</option>
                <option value="exec">exec (Run Shell Command)</option>
              </select>
            </div>

            <div className="mb-4">
              <label className="text-xs text-muted block mb-1">Target Container Name</label>
              <input
                type="text"
                className="input-field"
                placeholder="e.g. dockermind-master"
                value={dispatchContainer}
                onChange={(e) => setDispatchContainer(e.target.value)}
              />
            </div>

            {dispatchAction === 'exec' && (
              <div className="mb-4">
                <label className="text-xs text-muted block mb-1">Command String</label>
                <input
                  type="text"
                  className="input-field font-mono"
                  value={dispatchCommand}
                  onChange={(e) => setDispatchCommand(e.target.value)}
                />
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1.5rem' }}>
              <button className="btn btn-secondary" onClick={() => setDispatchModalOpen(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={() => { handleFleetDispatch(); setDispatchModalOpen(false); }}>
                Confirm & Dispatch
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Exec Modal ── */}
      {execModalOpen && (
        <div className="modal-overlay" onClick={() => setExecModalOpen(false)}>
          <div className="modal-content card-glass" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <h3 className="text-base font-semibold flex items-center gap-2">
                <Terminal size={18} className="text-cyan" /> Execute Command in {execTargetContainer}
              </h3>
              <button className="btn btn-secondary btn-sm" onClick={() => setExecModalOpen(false)}>✕</button>
            </div>

            <div className="mb-4">
              <label className="text-xs text-muted block mb-1">Shell Command (sh/bash)</label>
              <input
                type="text"
                className="input-field font-mono"
                value={execCmd}
                onChange={(e) => setExecCmd(e.target.value)}
              />
            </div>

            <button className="btn btn-primary mb-4" onClick={handleExec} disabled={executing}>
              {executing ? 'Executing...' : 'Run Command'}
            </button>

            {execResult && (
              <div className="terminal-window" style={{ height: '160px' }}>
                <div className="terminal-body font-mono text-xs">
                  {execResult.output || execResult.error || 'No output.'}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── AI Diagnosis & Remediation Modal ── */}
      {healModalOpen && (
        <div className="modal-overlay" onClick={() => !healExecuting && setHealModalOpen(false)}>
          <div className="modal-content card-glass" style={{ maxWidth: '640px', width: '92%' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <h3 className="text-base font-semibold flex items-center gap-2">
                <Zap size={18} className="text-violet" /> AI Diagnosis & Remediation
              </h3>
              <button className="btn btn-secondary btn-sm" disabled={healExecuting} onClick={() => setHealModalOpen(false)}>✕</button>
            </div>

            <div className="mb-3 p-2 rounded" style={{ background: 'rgba(15,23,42,0.7)', border: '1px solid #334155', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <span className="text-xs text-muted">Target Container: </span>
                <span className="font-mono text-cyan font-bold">{healTargetContainer}</span>
              </div>
              <div>
                <span className="text-xs text-muted">Node: </span>
                <span className="font-mono text-xs">{healTargetSlave}</span>
              </div>
            </div>

            {healLoading ? (
              <div style={{ textAlign: 'center', padding: '2.5rem 1rem' }}>
                <Sparkles size={32} className="animate-spin text-violet mb-3" style={{ margin: '0 auto' }} />
                <div className="text-sm font-semibold text-slate-200 mb-1">DockerMind AI Analyzing Container Logs...</div>
                <div className="text-xs text-muted">Evaluating exit codes, error signatures, memory thresholds, and backoff history.</div>
              </div>
            ) : (
              <div>
                {/* Status Badges */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem', marginBottom: '1rem' }}>
                  <div className="p-2 rounded" style={{ background: 'rgba(30,41,59,0.5)', border: '1px solid #334155', textAlign: 'center' }}>
                    <div className="text-xs text-muted mb-1">Severity</div>
                    <span className={`badge ${
                      healDiagnosis?.severity === 'ok' ? 'badge-ok' :
                      healDiagnosis?.severity === 'critical' ? 'badge-crit' : 'badge-warn'
                    }`}>
                      {(healDiagnosis?.severity || 'WARN').toUpperCase()}
                    </span>
                  </div>
                  <div className="p-2 rounded" style={{ background: 'rgba(30,41,59,0.5)', border: '1px solid #334155', textAlign: 'center' }}>
                    <div className="text-xs text-muted mb-1">AI Recommendation</div>
                    <span className="font-mono text-xs text-violet font-semibold">
                      {healDiagnosis?.heal_action || 'none'}
                    </span>
                  </div>
                  <div className="p-2 rounded" style={{ background: 'rgba(30,41,59,0.5)', border: '1px solid #334155', textAlign: 'center' }}>
                    <div className="text-xs text-muted mb-1">Safe to Auto-Heal</div>
                    <span className={`badge ${healDiagnosis?.auto_heal ? 'badge-ok' : 'badge-warn'}`}>
                      {healDiagnosis?.auto_heal ? 'YES' : 'MANUAL REVIEW'}
                    </span>
                  </div>
                </div>

                {/* Root Cause Card */}
                <div className="p-3 rounded mb-3" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #334155' }}>
                  <div className="text-xs text-muted mb-1 font-semibold flex items-center gap-1">
                    <Activity size={13} className="text-cyan" /> ROOT CAUSE DIAGNOSIS
                  </div>
                  <div className="text-sm text-slate-200" style={{ lineHeight: 1.5 }}>
                    {healDiagnosis?.root_cause || 'No active crash or error found in container logs.'}
                  </div>
                </div>

                {/* Fix Card */}
                <div className="p-3 rounded mb-3" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #334155' }}>
                  <div className="text-xs text-muted mb-1 font-semibold flex items-center gap-1">
                    <CheckCircle2 size={13} className="text-emerald" /> RECOMMENDED RESOLUTION
                  </div>
                  <div className="text-sm text-slate-200" style={{ lineHeight: 1.5 }}>
                    {healDiagnosis?.fix || 'Inspect application configuration.'}
                  </div>
                </div>

                {/* Analyzed Logs Snippet Accordion */}
                {healLogSnippet && (
                  <details style={{ marginBottom: '1.25rem', background: '#0b1120', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid #1e293b' }}>
                    <summary className="text-xs font-mono text-muted cursor-pointer hover:text-cyan">
                      View Recent Analyzed Logs Tail
                    </summary>
                    <pre className="mt-2 text-xs font-mono text-slate-300" style={{ maxHeight: '120px', overflowY: 'auto', whiteSpace: 'pre-wrap' }}>
                      {healLogSnippet}
                    </pre>
                  </details>
                )}

                {/* Action Buttons */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.6rem', marginTop: '1.25rem', flexWrap: 'wrap' }}>
                  <button className="btn btn-secondary btn-sm" disabled={healExecuting} onClick={() => setHealModalOpen(false)}>
                    Close
                  </button>

                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={healExecuting}
                    onClick={handleForceRestartFromModal}
                    title="Bypass AI recommendation and restart container directly"
                  >
                    <RefreshCw size={13} /> Force Restart Container
                  </button>

                  {healDiagnosis?.heal_action && healDiagnosis.heal_action !== 'none' ? (
                    <button
                      className="btn btn-ai btn-sm"
                      disabled={healExecuting}
                      onClick={() => handleExecuteHealAction(healDiagnosis.heal_action)}
                    >
                      <Zap size={13} /> {healExecuting ? 'Executing...' : `Apply AI Fix (${healDiagnosis.heal_action})`}
                    </button>
                  ) : (
                    <button
                      className="btn btn-ai btn-sm"
                      style={{ opacity: 0.85 }}
                      onClick={() => handleExecuteHealAction('restart')}
                      disabled={healExecuting}
                    >
                      <Zap size={13} /> {healExecuting ? 'Executing...' : 'Trigger AI Auto-Heal (Restart)'}
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Real-time Notification Toasts ── */}
      <div style={{ position: 'fixed', bottom: '1.5rem', right: '1.5rem', zIndex: 9999, display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
        {toasts.map((t) => (
          <div
            key={t.id}
            className="card-glass"
            style={{
              width: '320px',
              padding: '0.85rem 1rem',
              borderLeft: `4px solid ${
                t.type === 'crit' || t.type === 'error' ? 'var(--rose-400)' :
                t.type === 'warn' ? 'var(--amber-400)' :
                t.type === 'ai' ? 'var(--violet-400)' : 'var(--emerald-400)'
              }`,
              boxShadow: '0 10px 25px rgba(0,0,0,0.6)',
              animation: 'slide-in 0.3s ease',
            }}
          >
            <div className="font-semibold text-xs flex items-center gap-1.5" style={{ color: 'var(--text-main)' }}>
              {t.type === 'ok' ? <CheckCircle2 size={14} className="text-emerald" /> :
               t.type === 'crit' || t.type === 'error' ? <XCircle size={14} className="text-rose" /> :
               t.type === 'ai' ? <Sparkles size={14} className="text-violet" /> :
               <AlertTriangle size={14} className="text-amber" />}
              {t.title}
            </div>
            <div className="text-xs text-muted mt-1" style={{ wordBreak: 'break-word' }}>{t.msg}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
