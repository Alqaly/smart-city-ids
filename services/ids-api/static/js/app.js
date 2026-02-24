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
import { $, formatDuration, countCB, esc } from './utils.js';

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
  const uEl = $('loginUser'), pEl = $('loginPass');
  if (!uEl || !pEl) return;
  const u = (uEl.value || '').trim();
  const p = (pEl.value || '').trim();
  const err = $('loginError');
  if (!u || !p) {
    if (err) { err.textContent = 'Please enter username and password'; err.style.display = 'block'; }
    return;
  }
  api.login(u, p)
    .then(d => {
      if (d && d.access_token) {
        store.setState({ auth: { token: d.access_token } });
        localStorage.setItem('ids_token', d.access_token);
        showDashboard();
      } else {
        if (err) { err.textContent = (d && d.detail) || 'Login failed'; err.style.display = 'block'; }
      }
    })
    .catch(() => {
      if (err) { err.textContent = 'Connection error'; err.style.display = 'block'; }
    });
}

function doLogout() {
  store.setState({ auth: { token: '' } });
  localStorage.removeItem('ids_token');
  clearInterval(refreshTimer);
  disconnectLiveFeed();
  disconnectIoTStream();
  const dash = $('dashboard'); if (dash) dash.style.display = 'none';
  const ls = $('loginScreen'); if (ls) ls.style.display = 'flex';
}

// ══════════════════════════════════════════════════════════════════════════
// Dashboard Bootstrap
// ══════════════════════════════════════════════════════════════════════════

function showDashboard() {
  const ls = $('loginScreen'); if (ls) ls.style.display = 'none';
  const dash = $('dashboard'); if (dash) dash.style.display = 'block';
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
  fetchOverviewBundle().then(([h, m, cb, safety, prod, gov, dedup, alerts, dash, llmDiag, pipeline, rateLimiter]) => {
    const llmFromHealth = deriveLLM(h);
    renderOverview(m, h, cb, safety, prod, gov, llmFromHealth, llmDiag, dedup, rateLimiter, pipeline);
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
  fetchOverviewBundle().then(([h, m, cb, safety, prod, gov, dedup, alerts, dash, llmDiag, pipeline, rateLimiter]) => {
    const llmFromHealth = deriveLLM(h);

    // ── Always: overview panels + top bar ──
    renderOverview(m, h, cb, safety, prod, gov, llmFromHealth, llmDiag, dedup, rateLimiter, pipeline);
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
        loadIoTScale();
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

// Expose refresh function so LLM provider buttons can trigger a refresh
window._llmRefresh = refreshAll;

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
      const tabPanel = $('tab-' + tabId); if (tabPanel) tabPanel.classList.add('active');
      activeTab = tabId;

      // Immediate data load for the newly-activated tab
      switch (tabId) {
        case 'alerts':     loadAlerts(); break;
        case 'kubernetes': loadK8s(); break;
        case 'iot':        loadIoT(); loadIoTScale(); break;
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
  const cp = $('clusterPill');
  if (cp) {
    if (h && h.components && h.components.kubernetes === 'connected') {
      cp.className = 'pill pill-ok';
      cp.textContent = 'K8s Connected';
    } else {
      cp.className = 'pill pill-err';
      cp.textContent = 'K8s Disconnected';
    }
  }

  // LLM pill
  const lp = $('llmPill');
  if (lp) {
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
  }

  // Governance mode pill
  const gp = $('govPill');
  if (gp && gov) {
    const m = gov.mode || 'assisted';
    gp.textContent = m.charAt(0).toUpperCase() + m.slice(1);
    gp.className = 'pill ' + (m === 'autopilot' ? 'pill-warn' : 'pill-ok');
  }

  // Uptime
  if (h && h.uptime_seconds) {
    const ut = $('uptimeLabel'); if (ut) ut.textContent = 'Uptime: ' + formatDuration(h.uptime_seconds);
  }
}

// ══════════════════════════════════════════════════════════════════════════
// Global Bindings  (for inline onclick in HTML / innerHTML)
// ══════════════════════════════════════════════════════════════════════════

window._refreshAll = refreshAll;
window._showDashboard = showDashboard;
// Inline script already defines a robust doLogin w/ spinner — only set fallback
if (!window.doLogin) window.doLogin = doLogin;
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

// ══════════════════════════════════════════════════════════════════════════
// Audio Alerts — plays beep + speech synthesis for critical (sev >= 8)
// ══════════════════════════════════════════════════════════════════════════

let audioAlertsEnabled = localStorage.getItem('ids_audio') === 'true';

function updateAudioBtn() {
  const btn = $('audioToggleBtn');
  if (btn) btn.innerHTML = audioAlertsEnabled ? '&#x1F50A;' : '&#x1F507;';
}

function toggleAudioAlerts() {
  audioAlertsEnabled = !audioAlertsEnabled;
  localStorage.setItem('ids_audio', audioAlertsEnabled);
  updateAudioBtn();
}
window.toggleAudioAlerts = toggleAudioAlerts;
updateAudioBtn();

/**
 * Play a short alert beep using the Web Audio API.
 */
function playAlertBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = 880;
    osc.type = 'square';
    gain.gain.value = 0.15;
    osc.start();
    osc.stop(ctx.currentTime + 0.15);
    setTimeout(() => {
      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.frequency.value = 1200;
      osc2.type = 'square';
      gain2.gain.value = 0.15;
      osc2.start();
      osc2.stop(ctx.currentTime + 0.2);
    }, 200);
  } catch { /* Audio not available */ }
}

/**
 * Speak an alert using the Web Speech API.
 */
function speakAlert(severity, threatType, container) {
  try {
    if (!window.speechSynthesis) return;
    const msg = new SpeechSynthesisUtterance();
    msg.text = `Critical alert. Severity ${severity}. ${threatType || 'Unknown threat'} detected on ${container || 'IoT device'}.`;
    msg.rate = 1.1;
    msg.volume = 0.8;
    window.speechSynthesis.speak(msg);
  } catch { /* Speech not available */ }
}

/**
 * Called by the SSE handler when a new alert arrives.
 * Plays audio if the alert is critical and audio is enabled.
 */
function handleAudioAlert(alertData) {
  if (!audioAlertsEnabled) return;
  const sev = alertData.severity || 0;
  if (sev >= 8) {
    playAlertBeep();
    speakAlert(sev, alertData.threat_type, alertData.container_name);
    // Pulse the topbar
    const topbar = document.querySelector('.topbar');
    if (topbar) {
      topbar.classList.add('alert-pulse');
      setTimeout(() => topbar.classList.remove('alert-pulse'), 3000);
    }
  }
}

// Expose for SSE handler in alerts.js
window._handleAudioAlert = handleAudioAlert;

// ══════════════════════════════════════════════════════════════════════════
// IoT Fleet Scaling (UI control)
// ══════════════════════════════════════════════════════════════════════════

function scaleAllIoT() {
  const slider = $('iotScaleSlider');
  const statusEl = $('iotScaleStatus');
  const replicas = parseInt(slider?.value || '3', 10);
  if (statusEl) statusEl.innerHTML = '<span style="color:var(--yellow)">Scaling to ' + replicas + ' replicas...</span>';

  api.setIoTScale(replicas).then(res => {
    if (!res || res.error) {
      if (statusEl) statusEl.innerHTML = '<span style="color:var(--red)">Error: ' + (res?.error || 'Failed') + '</span>';
      return;
    }
    if (statusEl) statusEl.innerHTML = '<span style="color:var(--green)">All services scaled to ' + replicas + ' replicas</span>';
    setTimeout(loadIoTScale, 2000);
    setTimeout(loadIoT, 3000);
  }).catch(() => {
    if (statusEl) statusEl.innerHTML = '<span style="color:var(--red)">Network error</span>';
  });
}
window._scaleAllIoT = scaleAllIoT;

function loadIoTScale() {
  api.getIoTScale().then(res => {
    if (!res || !res.services) return;
    const el = $('iotScaleDetail');
    if (!el) return;
    let html = '';
    const services = res.services;
    for (const [svc, info] of Object.entries(services)) {
      const ready = info.ready || 0;
      const total = info.replicas || 0;
      const color = ready === total ? 'var(--green)' : ready > 0 ? 'var(--yellow)' : 'var(--red)';
      html += '<div style="background:var(--bg);border-radius:6px;padding:8px 12px;border:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">' +
        '<span style="font-size:12px;color:var(--text2)">' + svc + '</span>' +
        '<span style="font-weight:700;color:' + color + '">' + ready + '/' + total + '</span></div>';
    }
    el.innerHTML = html;
    // Update slider to match
    const slider = $('iotScaleSlider');
    const valEl = $('iotScaleValue');
    const firstSvc = Object.values(services)[0];
    if (firstSvc && slider) {
      slider.value = firstSvc.replicas;
      if (valEl) valEl.textContent = firstSvc.replicas;
    }
  });
}

// ══════════════════════════════════════════════════════════════════════════
// Chaos Mode (trigger attack pipeline from dashboard)
// ══════════════════════════════════════════════════════════════════════════

function startChaos(mode) {
  const log = $('attackLog');
  if (log) log.textContent += '\n[' + new Date().toLocaleTimeString() + '] \uD83D\uDD25 CHAOS MODE (' + mode + ') — triggering attack-iot-pipeline.sh...\n';

  api.startChaos(mode).then(res => {
    if (!res) { if (log) log.textContent += '[' + new Date().toLocaleTimeString() + '] \u274C Network error\n'; return; }
    if (res.error) { if (log) log.textContent += '[' + new Date().toLocaleTimeString() + '] \u274C ' + res.error + '\n'; return; }
    if (log) log.textContent += '[' + new Date().toLocaleTimeString() + '] \u2705 Chaos started — run_id: ' + res.run_id + ' (pid ' + res.pid + ')\n';
    if (log) log.textContent += '[' + new Date().toLocaleTimeString() + '] Watch the Live Pipeline Feed for real-time alert processing\n\n';
    if (log) log.scrollTop = log.scrollHeight;
  }).catch(e => {
    if (log) log.textContent += '[' + new Date().toLocaleTimeString() + '] \u274C ' + e.message + '\n';
  });
}
window._startChaos = startChaos;

/**
 * Dark/Light theme toggle.
 * Persists in localStorage so it survives page reloads.
 */
function toggleTheme() {
  const html = document.documentElement;
  const isLight = html.classList.toggle('light');
  localStorage.setItem('ids_theme', isLight ? 'light' : 'dark');
  const btn = $('themeToggleBtn');
  if (btn) btn.innerHTML = isLight ? '&#x2600;&#xFE0F;' : '&#x1F319;';
}
window.toggleTheme = toggleTheme;

// Restore saved theme on load
const savedTheme = localStorage.getItem('ids_theme');
if (savedTheme === 'light') {
  document.documentElement.classList.add('light');
  const btn = $('themeToggleBtn');
  if (btn) btn.innerHTML = '&#x2600;&#xFE0F;';
}

// Alert source filter change handler
const alertSourceFilter = $('alertSourceFilter');
if (alertSourceFilter) {
  alertSourceFilter.addEventListener('change', loadAlerts);
}
const incidentSearch = $('incidentSearch');
if (incidentSearch) incidentSearch.addEventListener('input', loadAlerts);
const incidentSort = $('incidentSort');
if (incidentSort) incidentSort.addEventListener('change', loadAlerts);
const incidentPageSize = $('incidentPageSize');
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
  const ls = $('loginScreen'); if (ls) ls.style.display = 'flex';
}
