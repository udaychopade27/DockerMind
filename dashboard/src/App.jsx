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

  // Initialize Data
  const refreshAll = async () => {
    const slavesData = await apiFetch('/slaves');
    if (slavesData?.slaves) setSlaves(slavesData.slaves);

    const containersData = await apiFetch('/containers');
    if (containersData?.containers) setContainers(containersData.containers);

    const alertsData = await apiFetch('/alerts');
    if (alertsData?.alerts) setAlerts(alertsData.alerts);

    const crashData = await apiFetch('/slaves/crash-loops');
    if (crashData?.crash_loops) setCrashLoops(crashData.crash_loops);

    const auditData = await apiFetch('/jobs/audit/log?limit=25');
    if (auditData?.audit_log) setAuditLogs(auditData.audit_log);

    const jobsData = await apiFetch('/jobs');
    if (jobsData?.jobs) setJobs(jobsData.jobs);

    const meData = await apiFetch('/auth/me');
    if (meData?.username) setCurrentUser(meData);
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

  // WebSocket Live Stream Connection
  useEffect(() => {
    if (!token) return;
    let ws = null;
    let pingInterval = null;

    const connectWS = () => {
      try {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
          setWsConnected(true);
          pingInterval = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send('ping');
              setLastPing(new Date().toLocaleTimeString());
            }
          }, 15000);
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.event === 'init') {
              if (data.slaves) setSlaves(data.slaves);
              if (data.containers) setContainers(data.containers);
            } else if (data.event === 'stats_update' && data.stats) {
              setStatsMap(prev => {
                const updated = { ...prev };
                data.stats.forEach(s => {
                  updated[s.name] = s;
                });
                return updated;
              });
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
            }
          } catch (e) {
            console.error('WS Parse error:', e);
          }
        };

        ws.onclose = () => {
          setWsConnected(false);
          clearInterval(pingInterval);
          setTimeout(connectWS, 4000);
        };

        ws.onerror = () => {
          setWsConnected(false);
        };
      } catch (err) {
        setWsConnected(false);
      }
    };

    connectWS();

    return () => {
      if (ws) ws.close();
      clearInterval(pingInterval);
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

              {/* Slaves Node Cards */}
              <div className="mb-6">
                <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
                  <Server size={18} className="text-cyan" /> Registered Host Nodes
                </h3>
                <div className="grid grid-cols-2 gap-4">
                  <div className="card-glass" style={{ borderLeft: '4px solid var(--emerald-400)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div className="font-semibold text-base">master (local)</div>
                        <div className="text-xs text-dim font-mono">127.0.0.1:8000 • Master Controller</div>
                      </div>
                      <span className="badge badge-ok">HEALTHY</span>
                    </div>
                  </div>

                  {slaves.map((slave) => {
                    const isOnline = slave.is_online || slave.status === 'online';
                    const tagList = Array.isArray(slave.tags) ? slave.tags.join(', ') : (slave.tags || 'worker');
                    return (
                      <div key={slave.slave_id} className="card-glass" style={{ borderLeft: `4px solid ${isOnline ? 'var(--cyan-400)' : 'var(--rose-400)'}` }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <div className="font-semibold text-base">{slave.slave_id}</div>
                            <div className="text-xs text-dim font-mono">{slave.ip || slave.address || 'localhost'}:{slave.port || 8080} • Containers: {slave.container_count ?? 0} • Tags: {tagList}</div>
                          </div>
                          <span className={`badge ${isOnline ? 'badge-ok' : 'badge-error'}`}>
                            {isOnline ? 'ONLINE' : 'OFFLINE'}
                          </span>
                        </div>
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
                      {containers.map((c) => {
                        const stats = statsMap[c.name] || {};
                        const cpu = stats.cpu_pct || 0;
                        const memPct = stats.mem_pct || 0;
                        const memUsed = stats.mem_used_mb || 0;
                        const memLimit = stats.mem_limit_mb || 0;
                        const isRunning = c.status === 'running' || c.status?.toLowerCase().includes('up');

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
                            <td style={{ width: '160px' }}>
                              <div className="text-xs font-mono">{cpu.toFixed(1)}%</div>
                              <div className="progress-bar-bg">
                                <div className={`progress-bar-fill ${cpu > 80 ? 'fill-rose' : 'fill-emerald'}`} style={{ width: `${Math.min(100, cpu)}%` }} />
                              </div>
                            </td>
                            <td style={{ width: '200px' }}>
                              <div className="text-xs font-mono flex justify-between">
                                <span>{memPct.toFixed(1)}%</span>
                                <span className="text-dim">{memUsed > 0 ? `${memUsed.toFixed(0)}MB / ${memLimit.toFixed(0)}MB` : '—'}</span>
                              </div>
                              <div className="progress-bar-bg">
                                <div
                                  className={`progress-bar-fill ${memPct > 90 ? 'fill-rose' : memPct > 80 ? 'fill-amber' : 'fill-emerald'}`}
                                  style={{ width: `${Math.min(100, memPct)}%` }}
                                />
                              </div>
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
                <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
                  <RefreshCw size={18} className="text-amber" /> Active Crash Loops & Circuit Breakers (Task 2 & 3)
                </h3>

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
