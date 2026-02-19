/**
 * api.js — Centralised API Client for the Smart City IDS Dashboard
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Replaces scattered fetch() calls with a single module that handles:
 *   1. JWT token injection from the Store
 *   2. Automatic 401 detection (triggers logout)
 *   3. Consistent JSON error handling (returns null on failure)
 *   4. Named methods for every API endpoint used by the dashboard
 *
 * Design decisions:
 *   - API_BASE is empty string ('') because the dashboard is served
 *     from the same origin as the API (FastAPI serves /ui).
 *   - Two helpers: `request()` (with JWT) and `requestNoAuth()` (public).
 *   - All methods return Promises that resolve to JSON or null.
 */

import { store } from './state.js';

const API_BASE = '';

// ── Internal Helpers ─────────────────────────────────────────────────────

/**
 * Authenticated fetch — injects Bearer token from Store.
 * @param {string} path   — API path (e.g., '/api/governance/status')
 * @param {Object} [opts] — extra fetch options (method, body, headers)
 * @returns {Promise<Object|null>}
 */
async function request(path, opts = {}) {
  const token = store.getState().auth.token;
  const headers = {
    'Authorization': `Bearer ${token}`,
    ...opts.headers,
  };
  try {
    const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
    if (res.status === 401) return { _error: true, _status: 401, detail: 'Session expired — please refresh' };
    if (res.status === 502) {
      const body = await res.json().catch(() => ({}));
      return { _error: true, _status: 502, detail: body.detail || 'Engine unavailable' };
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return { _error: true, _status: res.status, detail: body.detail || `HTTP ${res.status}` };
    }
    return res.json();
  } catch {
    return null;
  }
}

/**
 * Public fetch — no auth header (for /health, /api/metrics, etc.).
 * @param {string} path — API path
 * @returns {Promise<Object|null>}
 */
async function requestNoAuth(path, opts = {}) {
  try {
    const res = await fetch(`${API_BASE}${path}`, opts);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return { _error: true, _status: res.status, detail: body.detail || `HTTP ${res.status}` };
    }
    return res.json();
  } catch {
    return null;
  }
}

// ── Public API Object ────────────────────────────────────────────────────

/**
 * Structured API facade.  Each method maps to one backend endpoint.
 * Grouped by domain to match the tab structure.
 */
export const api = {
  // ── Auth ────────────────────────────────────────────────────────────
  login: (username, password) =>
    requestNoAuth('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }).catch(() => null),

  // ── Overview / Core (public endpoints) ──────────────────────────────
  getHealth:           () => requestNoAuth('/health'),
  getMetrics:          () => requestNoAuth('/api/metrics'),
  getCircuitBreaker:   () => requestNoAuth('/api/circuit-breaker/status'),
  getSafety:           () => requestNoAuth('/api/safety'),
  getProductionStatus: () => requestNoAuth('/api/production-status'),
  getDedupStats:       () => requestNoAuth('/api/deduplicator-stats'),
  getAlerts:           (limit = 30) => requestNoAuth(`/api/alerts?limit=${limit}`),
  getPipelineOverview: () => requestNoAuth('/api/pipeline-overview'),
  getLLMDiagnostics:   () => requestNoAuth('/api/llm/diagnostics'),
  getLLMStatsExport:   () => requestNoAuth('/api/llm-stats/export'),
  resetCircuitBreakers:() => requestNoAuth('/api/circuit-breaker/reset'),

  // ── Alerts (query with optional filter) ─────────────────────────────
  getAlertsFiltered: (limit, source) => {
    let url = `/api/alerts?limit=${limit}`;
    if (source) url += `&source=${source}`;
    return requestNoAuth(url);
  },

  // ── IoT ─────────────────────────────────────────────────────────────
  getIoTDevices:   () => requestNoAuth('/api/iot/devices'),
  getIoTTelemetry: () => requestNoAuth('/api/iot/telemetry'),
  getIoTEvents:    (limit = 30) => requestNoAuth(`/api/iot/events?limit=${limit}`),

  // ── Governance (requires auth) ──────────────────────────────────────
  getGovernanceStatus: () => request('/api/governance/status'),
  getOperatorDashboard: () => request('/api/operator/dashboard'),
  getGovernancePending: () => request('/api/governance/pending'),
  getGovernanceHistory: (limit = 20) => request(`/api/governance/history?limit=${limit}`),
  setGovernanceMode: (mode) =>
    request(`/api/governance/mode?mode=${mode}`, { method: 'POST' }),
  approveAction: (id, comment = 'Approved via dashboard') =>
    request(`/api/governance/approve/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analyst_comment: comment }),
    }),
  rejectAction: (id, comment = 'Rejected via dashboard') =>
    request(`/api/governance/reject/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analyst_comment: comment }),
    }),

  // ── Attack Injection ────────────────────────────────────────────────
  injectAlert: (payload) =>
    fetch(`${API_BASE}/api/alerts/internal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(r => r.json()),

  // ── Re-analyze (requires auth) ─────────────────────────────────────
  reanalyzeAlert: (alertId, engine) => {
    let url = `/api/alerts/${alertId}/reanalyze`;
    if (engine) url += `?engine=${engine}`;
    return request(url, { method: 'POST' });
  },

  // ── LLM Feedback (operator accuracy feedback) ──────────────────────
  submitFeedback: (analysisId, wasAccurate, comment = '') =>
    request('/api/llm/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        analysis_id: String(analysisId),
        was_accurate: wasAccurate,
        comment,
      }),
    }),
  getFeedbackStats: () => requestNoAuth('/api/llm/feedback/stats'),
  // ── IoT Fleet Scaling ──────────────────────────────────────────────
  getIoTScale:  () => requestNoAuth('/api/iot/scale'),
  setIoTScale:  (replicas, service) => {
    let url = `/api/iot/scale?replicas=${replicas}`;
    if (service) url += `&service=${service}`;
    return requestNoAuth(url, { method: 'POST' });
  },

  // ── Chaos Mode ─────────────────────────────────────────────────────
  startChaos:   (mode = 'quick') => requestNoAuth(`/api/demo/chaos?mode=${mode}`, { method: 'POST' }),
  getChaosStatus: () => requestNoAuth('/api/demo/chaos/status'),};

/**
 * Fetch all overview data in parallel — used by refreshAll().
 * Returns an object with named results for easy destructuring.
 *
 * Optimisation vs. old code: tabs that aren't visible get their
 * data lazy-loaded when the user switches to them, instead of
 * hammering all endpoints every 10 seconds.
 */
export async function fetchOverviewBundle() {
  const [health, metrics, cb, safety, prod, gov, dedup, alerts, dashboard, llmDiag, pipeline] =
    await Promise.all([
      api.getHealth(),
      api.getMetrics(),
      api.getCircuitBreaker(),
      api.getSafety(),
      api.getProductionStatus(),
      api.getGovernanceStatus(),
      api.getDedupStats(),
      api.getAlerts(30),
      api.getOperatorDashboard(),
      api.getLLMDiagnostics(),
      api.getPipelineOverview(),
    ]);
  return [health, metrics, cb, safety, prod, gov, dedup, alerts, dashboard, llmDiag, pipeline];
}
