/**
 * app.js — Application Entry Point
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Wires up authentication, tab switching, polling orchestration, and
 * connects all feature modules.
 *
 * Polling optimisation (addressing feedback — reduced HTTP traffic):
 *   The original dashboard fired 11 API calls every 10 seconds regardless
 *   of which tab was visible.  This version uses *lazy tab loading*:
 *     – Overview-related data (health, metrics, pipeline, etc.) is always
 *       fetched because the overview stays visible via the top bar.
 *     – Tab-specific data (K8s roster, IoT telemetry, LLM stats, etc.)
 *       is only fetched when that tab is active.
 *     – Polling interval increased from 10s → 15s (demo still feels live
 *       thanks to SSE for real-time alerts).
 *
 * ES6 module — loaded via <script type="module"> so all imports are scoped
 * and no globals leak.  Window bindings are only created where inline
 * onclick handlers (in innerHTML-generated HTML) require them.
 */

import { store, ALL_PROVIDERS } from './state.js';
import { api, fetchOverviewBundle } from './api.js';
import { formatDuration, countCB, esc } from './utils.js';

// ── Feature modules ──────────────────────────────────────────────────────
import {
  renderOverview,
  renderPipelineOverview,
  renderAlertFeed,
  renderLLMOverview,
  renderSystemHealth,
} from './modules/overview.js';
import {
  loadAlerts,
  connectLiveFeed,
  disconnectLiveFeed,
  toggleLiveFeed,
  clearLiveFeed,
} from './modules/alerts.js';
import { loadK8s } from './modules/kubernetes.js';
import {
  loadIoT,
  connectIoTStream,
  disconnectIoTStream,
  toggleIoTStream,
  clearIoTStream,
} from './modules/iot.js';
import { renderLLMTab, resetCircuitBreakers } from './modules/llm.js';
import { renderGovernanceTab } from './modules/governance.js';
import { renderAttackTab, clearAttackLog } from './modules/attacks.js';
import { renderThreatsTab, renderMetricsTab, initHunt } from './modules/threats.js';

// ══════════════════════════════════════════════════════════════════════════
// Module-level state
// ══════════════════════════════════════════════════════════════════════════

let refreshTimer = null;
let activeTab = 'overview';

// ══════════════════════════════════════════════════════════════════════════
// Authentication
// ══════════════════════════════════════════════════════════════════════════

function doLogin() {
  const u = document.getElementById('loginUser').value;
  const p = document.getElementById('loginPass').value;
  api.login(u, p)
    .then(d => {
      if (d && d.access_token) {
        store.setState({ auth: { token: d.access_token } });
        localStorage.setItem('ids_token', d.access_token);
        showDashboard();
      } else {
        const err = document.getElementById('loginError');
        err.textContent = (d && d.detail) || 'Login failed';
        err.style.display = 'block';
      }
    })
    .catch(() => {
      const err = document.getElementById('loginError');
      err.textContent = 'Connection error';
      err.style.display = 'block';
    });
}

function doLogout() {
  store.setState({ auth: { token: '' } });
  localStorage.removeItem('ids_token');
  clearInterval(refreshTimer);
  disconnectLiveFeed();
  disconnectIoTStream();
  document.getElementById('dashboard').style.display = 'none';
  document.getElementById('loginScreen').style.display = 'flex';
}

// ══════════════════════════════════════════════════════════════════════════
// Dashboard Bootstrap
// ══════════════════════════════════════════════════════════════════════════

function showDashboard() {
  document.getElementById('loginScreen').style.display = 'none';
  document.getElementById('dashboard').style.display = 'block';
  refreshAll();
  // 15-second polling (was 10s) — SSE provides instant alert updates
  refreshTimer = setInterval(refreshAll, 15000);
  connectLiveFeed(onNewSSEAlert);
  setTimeout(connectIoTStream, 1000);
}

/**
 * Callback fired when an SSE alert arrives.
 * Triggers a targeted overview refresh instead of full refreshAll.
 */
function onNewSSEAlert() {
  // Lightweight: only re-fetch overview metrics; not full tab data
  fetchOverviewBundle().then(([h, m, cb, safety, prod, gov, dedup, alerts, dash, llmDiag, pipeline]) => {
    const llmFromHealth = deriveLLM(h);
    renderOverview(m, h, cb, safety, prod, gov, llmFromHealth, llmDiag);
    renderPipelineOverview(pipeline);
    renderAlertFeed(alerts);
    updateTopBar(h, gov, llmFromHealth, llmDiag);
  });
}

// ══════════════════════════════════════════════════════════════════════════
// Refresh Orchestration  (lazy tab loading)
// ══════════════════════════════════════════════════════════════════════════

/**
 * Master refresh — always fetches overview bundle, then conditionally
 * refreshes data for the active tab only.
 */
function refreshAll() {
  fetchOverviewBundle().then(([h, m, cb, safety, prod, gov, dedup, alerts, dash, llmDiag, pipeline]) => {
    const llmFromHealth = deriveLLM(h);

    // ── Always: overview panels + top bar ──
    renderOverview(m, h, cb, safety, prod, gov, llmFromHealth, llmDiag);
    renderPipelineOverview(pipeline);
    renderAlertFeed(alerts);
    renderLLMOverview(llmFromHealth, cb, llmDiag);
    renderSystemHealth(h, prod);
    updateTopBar(h, gov, llmFromHealth, llmDiag);

    // ── Active tab only ──
    switch (activeTab) {
      case 'alerts':
        loadAlerts();
        break;
      case 'kubernetes':
        loadK8s();
        break;
      case 'iot':
        loadIoT();
        break;
      case 'llm':
        renderLLMTab(llmFromHealth, cb, dedup, llmDiag);
        break;
      case 'governance':
        renderGovernanceTab(gov, dash, refreshAll);
        break;
      case 'threats':
        renderThreatsTab(alerts);
        break;
      case 'metrics':
        renderMetricsTab(m, pipeline, llmDiag);
        break;
      case 'hunt':
        initHunt();
        break;
      case 'attacks':
        renderAttackTab();
        break;
      // overview: already rendered above
    }
  });
}

/**
 * Derive LLM info from /health response (no auth needed).
 */
function deriveLLM(h) {
  if (h && h.components && h.components.llm_providers) {
    const provNames = Object.keys(h.components.llm_providers);
    return { provider_count: h.llm_provider_count || provNames.length, providers: provNames };
  }
  return null;
}

// ══════════════════════════════════════════════════════════════════════════
// Tab Switching
// ══════════════════════════════════════════════════════════════════════════

function initTabSwitching() {
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(x => x.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      const tabId = b.dataset.tab;
      document.getElementById('tab-' + tabId).classList.add('active');
      activeTab = tabId;

      // Immediate data load for the newly-activated tab
      switch (tabId) {
        case 'alerts':     loadAlerts(); break;
        case 'kubernetes': loadK8s(); break;
        case 'iot':        loadIoT(); break;
        case 'llm':
        case 'governance':
        case 'threats':
        case 'metrics':
        case 'hunt':
        case 'attacks':
          // These tabs use data from refreshAll, so trigger it immediately
          refreshAll();
          break;
      }
    });
  });
}

// ══════════════════════════════════════════════════════════════════════════
// Top Bar Status Pills
// ══════════════════════════════════════════════════════════════════════════

function updateTopBar(h, gov, llm, llmDiag) {
  // Kubernetes cluster pill
  const cp = document.getElementById('clusterPill');
  if (h && h.components && h.components.kubernetes === 'connected') {
    cp.className = 'pill pill-ok';
    cp.textContent = 'K8s Connected';
  } else {
    cp.className = 'pill pill-err';
    cp.textContent = 'K8s Disconnected';
  }

  // LLM pill
  const lp = document.getElementById('llmPill');
  const pc = (h && h.llm_provider_count) ? h.llm_provider_count : ((llm && llm.provider_count) ? llm.provider_count : 0);
  const smry = (llmDiag && llmDiag.summary) ? llmDiag.summary : {};
  const errCount = (smry.error || 0) + (smry.cooldown || 0);
  if (pc > 0 && errCount === 0) {
    lp.className = 'pill pill-ok';
    lp.textContent = pc + '/' + ALL_PROVIDERS.length + ' LLM OK';
  } else if (pc > 0) {
    lp.className = 'pill pill-warn';
    lp.textContent = (smry.operational || pc) + '/' + ALL_PROVIDERS.length + ' LLM (' + errCount + ' issue' + (errCount > 1 ? 's' : '') + ')';
  } else {
    lp.className = 'pill pill-err';
    lp.textContent = 'No LLM';
  }

  // Governance mode pill
  const gp = document.getElementById('govPill');
  if (gov) {
    const m = gov.mode || 'assisted';
    gp.textContent = m.charAt(0).toUpperCase() + m.slice(1);
    gp.className = 'pill ' + (m === 'autopilot' ? 'pill-warn' : 'pill-ok');
  }

  // Uptime
  if (h && h.uptime_seconds) {
    document.getElementById('uptimeLabel').textContent = 'Uptime: ' + formatDuration(h.uptime_seconds);
  }
}

// ══════════════════════════════════════════════════════════════════════════
// Global Bindings  (for inline onclick in HTML / innerHTML)
// ══════════════════════════════════════════════════════════════════════════

window._refreshAll = refreshAll;
window.doLogin = doLogin;
window.doLogout = doLogout;
window.toggleLiveFeed = toggleLiveFeed;
window.clearLiveFeed = clearLiveFeed;
window.toggleIoTStream = toggleIoTStream;
window.clearIoTStream = clearIoTStream;
window.resetCircuitBreakers = () => resetCircuitBreakers(refreshAll);
window.clearAttackLog = clearAttackLog;
window.loadAlerts = loadAlerts;
window.loadK8s = loadK8s;
window.loadIoT = loadIoT;

/**
 * Dark/Light theme toggle.
 * Persists in localStorage so it survives page reloads.
 */
function toggleTheme() {
  const html = document.documentElement;
  const isLight = html.classList.toggle('light');
  localStorage.setItem('ids_theme', isLight ? 'light' : 'dark');
  const btn = document.getElementById('themeToggleBtn');
  if (btn) btn.innerHTML = isLight ? '&#x2600;&#xFE0F;' : '&#x1F319;';
}
window.toggleTheme = toggleTheme;

// Restore saved theme on load
const savedTheme = localStorage.getItem('ids_theme');
if (savedTheme === 'light') {
  document.documentElement.classList.add('light');
  const btn = document.getElementById('themeToggleBtn');
  if (btn) btn.innerHTML = '&#x2600;&#xFE0F;';
}

// Alert source filter change handler
const alertSourceFilter = document.getElementById('alertSourceFilter');
if (alertSourceFilter) {
  alertSourceFilter.addEventListener('change', loadAlerts);
}
const incidentSearch = document.getElementById('incidentSearch');
if (incidentSearch) incidentSearch.addEventListener('input', loadAlerts);
const incidentSort = document.getElementById('incidentSort');
if (incidentSort) incidentSort.addEventListener('change', loadAlerts);
const incidentPageSize = document.getElementById('incidentPageSize');
if (incidentPageSize) incidentPageSize.addEventListener('change', loadAlerts);

// ══════════════════════════════════════════════════════════════════════════
// Init
// ══════════════════════════════════════════════════════════════════════════

initTabSwitching();

// Check if already logged in
const savedToken = localStorage.getItem('ids_token');
if (savedToken) {
  store.setState({ auth: { token: savedToken } });
  showDashboard();
} else {
  document.getElementById('loginScreen').style.display = 'flex';
}
