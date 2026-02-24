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
import { $, esc, formatDuration, shortTime, sevBadge, countCB } from '../utils.js';

// ── Alert Clarity Helpers ────────────────────────────────────────────────

function alertSignatureId(a) {
  const f = (a && a.output_fields) ? a.output_fields : {};
  return a?.sid || a?.signature_id || f.sid || f.signature_id || '';
}

function ruleHelpMeta(a) {
  const source = String(a?.source || '').toLowerCase();
  const rule = String(a?.rule || '');
  const ns = String(a?.namespace || a?.k8s_ns || a?.k8s_namespace || a?.output_fields?.['k8s.ns.name'] || '').toLowerCase();
  const container = String(a?.container_name || a?.container || a?.output_fields?.['container.name'] || '').toLowerCase();
  const isMonitoring = ns === 'monitoring' || ns === 'falco-system' || container.includes('grafana') || container.includes('prometheus');

  if (source === 'suricata' && rule === 'SMARTCITY HTTP flood') {
    return {
      what: 'High-volume HTTP request burst detected from one source (DoS/flood pattern).',
      tone: 'warn',
    };
  }
  if (source === 'suricata' && /SQLi|UNION SELECT|DROP TABLE|OR 1=1/i.test(rule)) {
    return {
      what: 'SQL injection signature matched in inbound HTTP traffic.',
      tone: 'warn',
    };
  }
  if (source === 'falco' && /Sensitive File Read/i.test(rule) && isMonitoring) {
    return {
      what: 'Monitoring stack file access (often expected during startup/cert checks). Review path + timing before escalating.',
      tone: 'muted',
    };
  }
  if (source === 'falco' && /Shell in Container|Terminal shell/i.test(rule)) {
    return {
      what: 'Interactive shell executed inside a container. Usually unexpected outside maintenance.',
      tone: 'warn',
    };
  }
  if (source === 'falco' && /Crypto|Mining/i.test(rule)) {
    return {
      what: 'Runtime behavior matches crypto-mining process indicators.',
      tone: 'warn',
    };
  }
  return null;
}

// ── Stat Cards ───────────────────────────────────────────────────────────

/**
 * Render the 6 top-level stat cards on the Overview tab.
 */
export function renderOverview(m, h, cb, safety, prod, gov, llmFromHealth, llmDiag, dedup, rateLimiter, pipeline) {
  if (!m) return;
  const statsEl = $('overviewStats');
  if (!statsEl) return;
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
  const dedupHitPct = (typeof dedup?.hit_rate_percent === 'number')
    ? dedup.hit_rate_percent
    : (pipeline?.stages?.find?.(s => s.id === 'ingest')?.dedup_hit_rate_percent);
  const costSaved = (dedup?.cost_saved_usd != null && !Number.isNaN(Number(dedup.cost_saved_usd)))
    ? Number(dedup.cost_saved_usd)
    : null;
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
  if (costSaved != null) {
    dedupSub += ` · est. LLM savings ~$${costSaved.toFixed(2)}`;
  } else if (dedupHitPct != null) {
    dedupSub += ` · cache hit-rate ${Number(dedupHitPct).toFixed(1)}%`;
  }
  const dedupValue = (dedupPct != null && Number.isFinite(Number(dedupPct)))
    ? `${Number(dedupPct).toFixed(0)}%`
    : (dedupHitPct != null ? `${Number(dedupHitPct).toFixed(1)}%` : '—');

  // /api/rate-limiter/status returns { config, stats, status }.
  const rlStats = (rateLimiter && rateLimiter.stats) ? rateLimiter.stats : (rateLimiter || {});
  const rlCfg = (rateLimiter && rateLimiter.config) ? rateLimiter.config : {};
  const rlReceived = Number(rlStats.total_received ?? 0);
  const rlThrottled = Number(rlStats.total_throttled ?? 0);
  const rlProcessed = Number(rlStats.total_processed ?? 0);
  const rlPct = Number(rlStats.throttle_rate_percent ?? (rlReceived > 0 ? ((rlThrottled / rlReceived) * 100) : 0));
  const rlWindow = Number(rlCfg.window_seconds ?? 60);
  const floodColor = rlPct >= 80 ? 'var(--red)' : rlPct >= 40 ? 'var(--yellow)' : 'var(--green)';
  const floodSub = rlReceived > 0
    ? `${rlProcessed}/${rlReceived} alerts kept in ${rlWindow}s · ${rlPct.toFixed(1)}% throttled`
    : 'No duplicate flood suppression activity yet';

  statsEl.innerHTML =
    `<div class="stat-card blue"><div class="stat-label">Total Alerts</div><div class="stat-value">${totalAlerts}</div><div class="stat-sub">Ingested via Falco / Suricata</div></div>` +
    `<div class="stat-card red"><div class="stat-label">Critical Alerts</div><div class="stat-value">${critAlerts}</div><div class="stat-sub">${critSub}</div></div>` +
    `<div class="stat-card green"><div class="stat-label">IoT Devices</div><div class="stat-value">${iotCount}</div><div class="stat-sub">${iotSub}</div></div>` +
    `<div class="stat-card ${(smry.error > 0 || smry.cooldown > 0) ? 'red' : 'purple'}"><div class="stat-label">LLM Engines</div><div class="stat-value">${smry.operational || (h && h.llm_provider_count) || countCB(cb)}/${ALL_PROVIDERS.length}</div><div class="stat-sub">${llmSub}</div></div>` +
    `<div class="stat-card yellow"><div class="stat-label">Dedup + LLM Savings</div><div class="stat-value">${dedupValue}</div><div class="stat-sub">${esc(dedupSub)}</div></div>` +
    `<div class="stat-card orange"><div class="stat-label">Flood Suppression</div><div class="stat-value" style="color:${floodColor}">${rlThrottled}</div><div class="stat-sub">${esc(floodSub)}</div></div>` +
    `<div class="stat-card orange"><div class="stat-label">Uptime</div><div class="stat-value">${uptime}</div><div class="stat-sub">IDS API process uptime</div></div>`;
}

// ── Pipeline Overview ────────────────────────────────────────────────────

/**
 * Render the 5-stage pipeline and alert fatigue reduction card.
 */
export function renderPipelineOverview(data) {
  const pipeEl = $('pipelineOverview');
  const fatigueEl = $('alertFatigue');
  if (!pipeEl || !fatigueEl) return;
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
  const el = $('alertFeed');
  if (!el) return;
  const badgeEl = $('alertCountBadge');
  if (badgeEl) badgeEl.textContent = data.total || 0;

  if (!data.alerts.length) {
    el.innerHTML = '<div style="padding:20px;color:var(--text3);text-align:center">No alerts yet - run an attack simulation!</div>';
    return;
  }

  let html = '';
  data.alerts.slice(0, 20).forEach(a => {
    const an = a.analysis || {};
    const guide = ruleHelpMeta(a);
    const conf = an.confidence || an.confidence_score || 0;
    const confPct = typeof conf === 'number' ? (conf <= 1 ? Math.round(conf * 100) : Math.round(conf)) : 0;
    const confClass = confPct >= 80 ? 'conf-high' : confPct >= 50 ? 'conf-medium' : 'conf-low';
    const engineId = an.analysis_engine || an.engine || '';
    const mitre = an.mitre_technique || '';
    const sid = alertSignatureId(a);
    const whereParts = [
      a.namespace || a.k8s_ns || a.k8s_namespace || a.output_fields?.['k8s.ns.name'],
      a.pod_name || a.k8s_pod || a.output_fields?.['k8s.pod.name'],
      a.container_name || a.container || a.output_fields?.['container.name'],
    ].filter(Boolean);

    const sevLabel = a.severity >= 8 ? 'CRIT' : a.severity >= 6 ? 'HIGH' : a.severity >= 4 ? 'MED' : 'LOW';
    html += `<div class="feed-item">` +
      `<span class="feed-time">${shortTime(a.timestamp)}</span>` +
      `<span class="feed-source"><span class="badge ${a.source === 'falco' ? 'badge-info' : 'badge-purple'}">${esc(a.source || 'unknown')}</span></span>` +
      `<span class="feed-msg"><strong>${esc(a.rule || '')}</strong> - ${esc(a.summary || a.output || '')}` +
        (guide?.tone === 'muted' ? ` <span style="display:inline-block;padding:1px 6px;border-radius:999px;background:rgba(148,163,184,.12);color:var(--text3);font-size:10px;font-weight:600">Likely Platform Noise</span>` : '') +
        (engineId ? ` <span class="ai-badge">&#x1F916; ${esc(engineId)}</span>` : '') +
        (confPct > 0 ? ` <span class="conf-badge ${confClass}">${confPct}%</span>` : '') +
        (mitre ? ` <span style="font-size:9px;color:var(--red);font-weight:600">${esc(mitre)}</span>` : '') +
        (sid ? `<br><span style="font-size:10px;color:var(--text3)">Suricata SID ${esc(String(sid))}</span>` : '') +
        (whereParts.length ? `<br><span style="font-size:10px;color:var(--text3)">Where: ${esc(whereParts.join(' / '))}</span>` : '') +
        (guide?.what ? `<br><span style="font-size:10px;color:${guide.tone === 'muted' ? 'var(--text3)' : 'var(--yellow)'}">${esc(guide.what)}</span>` : '') +
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
  const el = $('llmOverview');
  if (!el) return;
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
  const el = $('systemHealth');
  if (!el) return;
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
