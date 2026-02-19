/**
 * overview.js — Overview Tab Rendering Module
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Renders the main dashboard overview tab:
 *   - 6 stat cards (Total Alerts, Critical, IoT Devices, LLM Engines, etc.)
 *   - 5-stage pipeline overview (Ingestion → Dedup → LLM → Governance → Action)
 *   - Alert fatigue reduction metrics
 *   - Live alert feed (recent 20 alerts)
 *   - LLM provider sidebar (operational status)
 *   - System health sidebar (K8s, DB, Falco, Suricata)
 *
 * All functions receive pre-fetched data — they do NOT call the API.
 * Data is passed in from app.js after the parallel fetchOverviewBundle().
 */

import { ALL_PROVIDERS } from '../state.js';
import { esc, formatDuration, shortTime, sevBadge, countCB } from '../utils.js';

// ── Stat Cards ───────────────────────────────────────────────────────────

/**
 * Render the 6 top-level stat cards on the Overview tab.
 */
export function renderOverview(m, h, cb, safety, prod, gov, llmFromHealth, llmDiag) {
  if (!m) return;
  const uptime = m.uptime_seconds ? formatDuration(m.uptime_seconds) : '--';
  const smry = (llmDiag && llmDiag.summary) ? llmDiag.summary : {};

  let llmSub = '';
  if (smry.operational || smry.error || smry.cooldown) {
    const parts = [];
    if (smry.operational) parts.push(smry.operational + ' healthy');
    if (smry.error)       parts.push(smry.error + ' error');
    if (smry.cooldown)    parts.push(smry.cooldown + ' cooldown');
    llmSub = parts.join(', ');
  } else {
    llmSub = (llmFromHealth && llmFromHealth.providers)
      ? llmFromHealth.providers.join(', ')
      : 'none configured';
  }

  // Build smarter subtitles
  const totalAlerts = m.total_alerts || 0;
  const critAlerts = m.critical_alerts || 0;
  const critPct = totalAlerts > 0 ? Math.round((critAlerts / totalAlerts) * 100) : 0;
  const critSub = totalAlerts > 0
    ? `Severity 8-10 (${critPct}% of total)`
    : 'Severity 8-10 — no alerts yet';
  const iotCount = m.iot_devices_active || 0;
  const iotSub = iotCount > 0
    ? `${iotCount} pod(s) running in K8s`
    : 'Scanning cluster for IoT pods…';
  const dedupPct = m.alert_reduction_percentage;
  const dedupRaw = m.raw_alerts || m.total_alerts || 0;
  let dedupSub;
  if (dedupRaw === 0) {
    dedupSub = 'No alerts processed yet';
  } else if (dedupPct === 100) {
    dedupSub = 'All duplicates suppressed';
  } else if (dedupPct === 0) {
    dedupSub = 'No duplicates detected';
  } else {
    dedupSub = `${dedupPct}% duplicate alerts suppressed`;
  }

  document.getElementById('overviewStats').innerHTML =
    `<div class="stat-card blue"><div class="stat-label">Total Alerts</div><div class="stat-value">${totalAlerts}</div><div class="stat-sub">Ingested via Falco / Suricata</div></div>` +
    `<div class="stat-card red"><div class="stat-label">Critical Alerts</div><div class="stat-value">${critAlerts}</div><div class="stat-sub">${critSub}</div></div>` +
    `<div class="stat-card green"><div class="stat-label">IoT Devices</div><div class="stat-value">${iotCount}</div><div class="stat-sub">${iotSub}</div></div>` +
    `<div class="stat-card ${(smry.error > 0 || smry.cooldown > 0) ? 'red' : 'purple'}"><div class="stat-label">LLM Engines</div><div class="stat-value">${smry.operational || (h && h.llm_provider_count) || countCB(cb)}/${ALL_PROVIDERS.length}</div><div class="stat-sub">${llmSub}</div></div>` +
    `<div class="stat-card yellow"><div class="stat-label">Dedup Savings</div><div class="stat-value">${dedupPct != null ? dedupPct : 0}%</div><div class="stat-sub">${dedupSub}</div></div>` +
    `<div class="stat-card orange"><div class="stat-label">Uptime</div><div class="stat-value">${uptime}</div><div class="stat-sub">IDS API process uptime</div></div>`;
}

// ── Pipeline Overview ────────────────────────────────────────────────────

/**
 * Render the 5-stage pipeline and alert fatigue reduction card.
 */
export function renderPipelineOverview(data) {
  const pipeEl = document.getElementById('pipelineOverview');
  const fatigueEl = document.getElementById('alertFatigue');
  if (!data || !data.stages) {
    pipeEl.innerHTML = '';
    fatigueEl.innerHTML = '<span style="color:var(--text3)">Pipeline metrics unavailable</span>';
    return;
  }

  let html = '';
  data.stages.forEach(s => {
    const dot = s.status === 'green' ? 'dot-green' : s.status === 'yellow' ? 'dot-yellow' : 'dot-red';
    html += `<div class="pipeline-stage">` +
      `<div class="name"><span class="dot ${dot}"></span>${esc(s.label)}</div>` +
      `<div class="rate">${s.rate_per_minute || 0}/m</div>` +
      `<div class="meta">p95: ${s.p95_latency_ms || 0} ms</div>` +
      (s.dedup_hit_rate_percent !== undefined ? `<div class="meta">Dedup: ${s.dedup_hit_rate_percent}%</div>` : '') +
      `</div>`;
  });
  pipeEl.innerHTML = html;

  const f = data.alert_fatigue || {};
  const hasData = (f.raw_total || 0) > 0;
  if (!hasData) {
    fatigueEl.innerHTML =
      `<div style="color:var(--text3);font-size:13px;text-align:center;padding:8px">` +
      `No alerts processed in this session yet. Send alerts or run an attack simulation to see fatigue metrics.` +
      `</div>`;
  } else {
    fatigueEl.innerHTML =
      `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;font-size:13px">` +
      `<div><span style="color:var(--text3)">Raw Alerts</span><br><strong>${f.raw_total}</strong></div>` +
      `<div><span style="color:var(--text3)">After Dedup</span><br><strong>${f.after_dedup_total || 0}</strong></div>` +
      `<div><span style="color:var(--text3)">Human Review</span><br><strong>${f.human_review_required_total || 0}</strong></div>` +
      `<div><span style="color:var(--text3)">Auto-Handled</span><br><strong>${f.auto_handled_total || 0}</strong></div>` +
      `<div><span style="color:var(--text3)">Reduction</span><br><strong>${f.reduction_percent || 0}%</strong></div>` +
      `</div>`;
  }
}

// ── Live Alert Feed ──────────────────────────────────────────────────────

/**
 * Render the recent-alerts feed in the overview sidebar.
 */
export function renderAlertFeed(data) {
  if (!data || !data.alerts) return;
  const el = document.getElementById('alertFeed');
  document.getElementById('alertCountBadge').textContent = data.total || 0;

  if (!data.alerts.length) {
    el.innerHTML = '<div style="padding:20px;color:var(--text3);text-align:center">No alerts yet - run an attack simulation!</div>';
    return;
  }

  let html = '';
  data.alerts.slice(0, 20).forEach(a => {
    const an = a.analysis || {};
    const conf = an.confidence || an.confidence_score || 0;
    const confPct = typeof conf === 'number' ? (conf <= 1 ? Math.round(conf * 100) : Math.round(conf)) : 0;
    const confClass = confPct >= 80 ? 'conf-high' : confPct >= 50 ? 'conf-medium' : 'conf-low';
    const engineId = an.analysis_engine || an.engine || '';
    const mitre = an.mitre_technique || '';

    const sevLabel = a.severity >= 8 ? 'CRIT' : a.severity >= 6 ? 'HIGH' : a.severity >= 4 ? 'MED' : 'LOW';
    html += `<div class="feed-item">` +
      `<span class="feed-time">${shortTime(a.timestamp)}</span>` +
      `<span class="feed-source"><span class="badge ${a.source === 'falco' ? 'badge-info' : 'badge-purple'}">${esc(a.source || 'unknown')}</span></span>` +
      `<span class="feed-msg"><strong>${esc(a.rule || '')}</strong> - ${esc(a.summary || a.output || '')}` +
        (engineId ? ` <span class="ai-badge">&#x1F916; ${esc(engineId)}</span>` : '') +
        (confPct > 0 ? ` <span class="conf-badge ${confClass}">${confPct}%</span>` : '') +
        (mitre ? ` <span style="font-size:9px;color:var(--red);font-weight:600">${esc(mitre)}</span>` : '') +
      `</span>` +
      (a.severity ? `<span class="badge ${sevBadge(a.severity)}" title="Severity ${a.severity}/10 — ${sevLabel}">${a.severity} ${sevLabel}</span>` : '') +
      `</div>`;
  });
  el.innerHTML = html;
}

// ── LLM Provider Sidebar ─────────────────────────────────────────────────

/**
 * Render compact LLM provider status in the overview sidebar.
 */
export function renderLLMOverview(llm, cb, llmDiag) {
  const el = document.getElementById('llmOverview');
  const engines = (cb && cb.engines) ? cb.engines : {};
  const configured = (llm && llm.providers) ? llm.providers : [];
  const diags = (llmDiag && llmDiag.providers) ? llmDiag.providers : {};

  let html = '';
  ALL_PROVIDERS.forEach(p => {
    const info = engines[p.id];
    const d = diags[p.id] || {};
    const isConfigured = configured.indexOf(p.id) !== -1 || !!info || d.configured;
    const ds = d.status || 'unknown';

    const stateText = ds === 'operational' ? (d.successes > 0 ? 'Healthy' : 'Ready') :
      ds === 'not_configured' ? 'No API Key' :
      ds === 'cooldown' ? 'Cooldown' :
      ds === 'error' ? 'Error' :
      ds === 'circuit_open' ? 'Circuit Open' :
      !isConfigured ? 'Not Configured' : 'Ready';

    const dotClass = ds === 'operational' ? 'dot-green' :
      ds === 'not_configured' ? 'dot-yellow' :
      (ds === 'cooldown' || ds === 'recovering') ? 'dot-yellow' :
      (ds === 'error' || ds === 'circuit_open') ? 'dot-red' :
      !isConfigured ? 'dot-yellow' : 'dot-green';

    const stats = info
      ? ((info.successes || 0) === 0 && (info.failures || 0) === 0
          ? ' | idle'
          : ` | ${info.successes || 0} ok / ${info.failures || 0} fail`)
      : '';
    const reason = (d.reason && ds !== 'operational' && ds !== 'not_configured')
      ? ` <span style="font-size:10px;color:var(--text3);display:block;margin-top:1px">${esc(d.reason.substring(0, 60))}</span>` : '';

    html += `<div class="provider-card" style="margin-bottom:8px;${isConfigured ? '' : 'opacity:.55'}">` +
      `<div class="provider-icon" style="${isConfigured ? 'color:' + p.color : 'color:var(--text3)'}">${p.icon}</div>` +
      `<div class="provider-info">` +
      `<div class="provider-name">${p.name}</div>` +
      `<div class="provider-detail"><span class="dot ${dotClass}"></span>${stateText}${stats}</div>` +
      reason +
      `</div></div>`;
  });
  el.innerHTML = html;
}

// ── System Health Sidebar ────────────────────────────────────────────────

/**
 * Render system component health in the overview sidebar.
 */
export function renderSystemHealth(h, prod) {
  const el = document.getElementById('systemHealth');
  if (!h) { el.innerHTML = '<div style="color:var(--text3)">Connecting...</div>'; return; }
  const c = h.components || {};
  const rl = (prod && prod.rate_limiter) ? prod.rate_limiter : {};

  el.innerHTML =
    `<div style="display:grid;gap:8px;font-size:13px">` +
    `<div><span class="dot ${c.kubernetes === 'connected' ? 'dot-green' : 'dot-red'}"></span>Kubernetes: ${c.kubernetes || 'unknown'}</div>` +
    `<div><span class="dot ${c.database === 'memory-fallback' ? 'dot-yellow' : 'dot-green'}"></span>Database: ${c.database || 'unknown'}${c.database === 'memory-fallback' ? ' <span style="font-size:10px;color:var(--text3)">(PostgreSQL unavailable — using in-memory store, data lost on restart)</span>' : ' <span style="font-size:10px;color:var(--text3)">(persistent, 8 tables)</span>'}</div>` +
    `<div><span class="dot ${c.falco === 'enabled' ? 'dot-green' : 'dot-red'}"></span>Falco: ${c.falco || 'unknown'}</div>` +
    `<div><span class="dot ${c.suricata === 'enabled' ? 'dot-green' : 'dot-red'}"></span>Suricata: ${c.suricata || 'unknown'}</div>` +
    `<div style="margin-top:4px;color:var(--text3);font-size:11px">Rate limit: ${rl.total_requests || 0} req (${rl.rejected_requests || 0} rejected)</div>` +
    `</div>`;
}
