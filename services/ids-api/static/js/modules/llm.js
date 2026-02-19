/**
 * llm.js — LLM Providers Tab
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Renders:
 *   • Summary stat cards (total, operational, errors, cost saved)
 *   • Per-engine latency bar chart (p50/p95 CSS bars)
 *   • Per-engine cost bar chart
 *   • Token usage table
 *   • Provider detail cards (status, diagnostics, progress bars)
 *   • Circuit breaker + deduplication detail panels
 */

import { ALL_PROVIDERS } from '../state.js';
import { api } from '../api.js';
import { esc } from '../utils.js';

// Bar chart colour palette per engine
const BAR_COLORS = {
  xai: '#a78bfa', openai: '#34d399', anthropic: '#f97316',
  gemini: '#60a5fa', kimi: '#f472b6', local: '#94a3b8',
};

/**
 * Render the full LLM tab.
 * @param {Object} llm — /health LLM section
 * @param {Object} cb  — circuit breaker status
 * @param {Object} dedup — deduplicator stats
 * @param {Object} llmDiag — /api/llm/diagnostics response
 */
export function renderLLMTab(llm, cb, dedup, llmDiag) {
  const configCount = (llm && llm.provider_count) ? llm.provider_count : 0;
  const configured = (llm && llm.providers) ? llm.providers : [];
  const engines = (cb && cb.engines) ? cb.engines : {};
  const diags = (llmDiag && llmDiag.providers) ? llmDiag.providers : {};
  const smry = (llmDiag && llmDiag.summary) ? llmDiag.summary : {};

  // ── Summary cards ──────────────────────────────────────────────────
  document.getElementById('llmStats').innerHTML =
    '<div class="stat-card purple"><div class="stat-label">Total Providers</div><div class="stat-value">' + ALL_PROVIDERS.length + '</div><div class="stat-sub">' + ALL_PROVIDERS.map(p => p.id).join(', ') + '</div></div>' +
    '<div class="stat-card green"><div class="stat-label">Operational</div><div class="stat-value">' + (smry.operational || 0) + '/' + ALL_PROVIDERS.length + '</div><div class="stat-sub">Configured: ' + configCount + '</div></div>' +
    '<div class="stat-card red"><div class="stat-label">Errors / Cooldown</div><div class="stat-value">' + ((smry.error || 0) + (smry.cooldown || 0)) + '</div><div class="stat-sub">' + (smry.error || 0) + ' errors, ' + (smry.cooldown || 0) + ' in cooldown</div></div>' +
    '<div class="stat-card blue"><div class="stat-label">Avg Latency</div><div class="stat-value" id="llmAvgLatVal">--</div><div class="stat-sub" id="llmAvgLatSub">Primary engine response time</div></div>';

  // ── Latency/cost charts (async — need stats export) ────────────────
  api.getLLMStatsExport().then(stats => {
    if (!stats || !stats.engines) return;
    const eng = stats.engines;
    const names = Object.keys(eng);
    renderLatencyChart(eng, names);
    renderCostChart(eng, names);
    renderTokenTable(eng, names);

    // Update Avg Latency card with primary engine data
    const primary = names.find(n => eng[n].total_requests > 0);
    if (primary) {
      const avg = eng[primary].avg_latency_s || 0;
      document.getElementById('llmAvgLatVal').textContent = avg.toFixed(2) + 's';
      document.getElementById('llmAvgLatSub').textContent = primary + ' (' + eng[primary].total_requests + ' requests)';
    }
  });

  // ── Provider cards ─────────────────────────────────────────────────
  renderProviderCards(configured, engines, diags);
  // ── Circuit breaker detail ─────────────────────────────────────────
  renderCircuitBreakerDetail(cb, configured, diags);
  // ── Deduplication detail ───────────────────────────────────────────
  renderDedupDetail(dedup);
  // ── Operator feedback stats ────────────────────────────────────────
  renderFeedbackStats();
}

// ── Chart renderers ──────────────────────────────────────────────────────

function renderLatencyChart(eng, names) {
  let maxLat = 0;
  names.forEach(n => { const p = eng[n].p95_latency_s || 0; if (p > maxLat) maxLat = p; });
  if (maxLat < 0.01) maxLat = 0.1;

  let html = '<table style="width:100%;border-collapse:collapse;font-size:13px">';
  html += '<tr style="color:var(--text3);font-size:11px"><td style="width:80px">Engine</td><td>p50</td><td>p95</td><td>Avg</td><td style="width:50%">Distribution</td></tr>';
  names.forEach(n => {
    const e = eng[n];
    if (!e.total_requests) return;
    const p50 = e.p50_latency_s || 0, p95 = e.p95_latency_s || 0, avg = e.avg_latency_s || 0;
    const barW = Math.max(2, Math.round((p95 / maxLat) * 100));
    const barW50 = Math.max(1, Math.round((p50 / maxLat) * 100));
    const col = BAR_COLORS[n] || '#94a3b8';
    html += '<tr style="border-top:1px solid var(--bg3)">' +
      '<td><strong>' + n + '</strong></td>' +
      '<td>' + p50.toFixed(3) + 's</td>' +
      '<td>' + p95.toFixed(3) + 's</td>' +
      '<td>' + avg.toFixed(3) + 's</td>' +
      '<td><div style="position:relative;height:22px;background:var(--bg3);border-radius:4px;overflow:hidden">' +
      '<div style="position:absolute;left:0;top:0;height:100%;width:' + barW + '%;background:' + col + ';opacity:.3;border-radius:4px" title="p95"></div>' +
      '<div style="position:absolute;left:0;top:0;height:100%;width:' + barW50 + '%;background:' + col + ';border-radius:4px" title="p50"></div>' +
      '<span style="position:absolute;left:4px;top:2px;font-size:10px;color:var(--text1)">' + n + '</span>' +
      '</div></td></tr>';
  });
  html += '</table>';
  document.getElementById('llmLatencyChart').innerHTML = html || '<div style="color:var(--text3);padding:12px">No data yet — run attacks to generate stats</div>';
}

function renderCostChart(eng, names) {
  let maxCost = 0;
  names.forEach(n => { const c = eng[n].total_estimated_cost_usd || 0; if (c > maxCost) maxCost = c; });
  if (maxCost < 0.001) maxCost = 0.01;

  let html = '<table style="width:100%;border-collapse:collapse;font-size:13px">';
  html += '<tr style="color:var(--text3);font-size:11px"><td style="width:80px">Engine</td><td>Requests</td><td>Success</td><td>$/call</td><td>Total $</td><td style="width:40%">Cost</td></tr>';
  names.forEach(n => {
    const e = eng[n];
    if (!e.total_requests) return;
    const cost = e.total_estimated_cost_usd || 0;
    const barW = Math.max(2, Math.round((cost / maxCost) * 100));
    const col = BAR_COLORS[n] || '#94a3b8';
    html += '<tr style="border-top:1px solid var(--bg3)">' +
      '<td><strong>' + n + '</strong></td>' +
      '<td>' + e.total_requests + '</td>' +
      '<td>' + (e.success_rate * 100).toFixed(0) + '%</td>' +
      '<td>$' + e.cost_per_call_usd.toFixed(4) + '</td>' +
      '<td>$' + cost.toFixed(4) + '</td>' +
      '<td><div style="height:18px;background:var(--bg3);border-radius:4px;overflow:hidden">' +
      '<div style="height:100%;width:' + barW + '%;background:' + col + ';border-radius:4px"></div>' +
      '</div></td></tr>';
  });
  html += '</table>';
  document.getElementById('llmCostChart').innerHTML = html || '<div style="color:var(--text3);padding:12px">No data yet</div>';
}

function renderTokenTable(eng, names) {
  let rows = '';
  names.forEach(n => {
    const e = eng[n];
    if (!e.total_requests) return;
    rows += '<tr>' +
      '<td><strong>' + n + '</strong></td>' +
      '<td>' + (e.prompt_tokens_total || 0) + '</td>' +
      '<td>' + (e.completion_tokens_total || 0) + '</td>' +
      '<td>' + (e.tokens_total || 0) + '</td>' +
      '<td>' + (e.avg_tokens_per_request || 0) + '</td>' +
      '<td>$' + ((e.avg_cost_per_request_usd || 0).toFixed(6)) + '</td>' +
      '</tr>';
  });
  document.getElementById('llmTokenTable').innerHTML = rows || '<tr><td colspan="6" style="text-align:center;color:var(--text3)">No token data yet</td></tr>';
}

// ── Provider cards ───────────────────────────────────────────────────────

function renderProviderCards(configured, engines, diags) {
  const pc = document.getElementById('llmProviderCards');
  let html = '';
  ALL_PROVIDERS.forEach(p => {
    const info = engines[p.id];
    const d = diags[p.id] || {};
    const isConfigured = configured.indexOf(p.id) !== -1 || !!info || d.configured;
    const ds = d.status || 'unknown';
    const color = ds === 'operational' ? 'var(--green)' : ds === 'not_configured' ? 'var(--text3)' : ds === 'cooldown' ? 'var(--yellow)' : 'var(--red)';
    const statusLabel = ds === 'operational' ? (d.successes > 0 ? 'Healthy' : 'Ready') :
      ds === 'not_configured' ? 'No API Key' :
      ds === 'cooldown' ? 'Cooldown (' + d.cooldown_remaining_seconds + 's)' :
      ds === 'error' ? 'Error' :
      ds === 'circuit_open' ? 'Circuit Open' :
      ds === 'recovering' ? 'Recovering' : 'Unknown';
    const pct = (d.successes && (d.successes + d.failures) > 0) ? Math.min(100, d.successes / (d.successes + d.failures) * 100) : 0;
    const reason = d.reason || '';
    const lastErr = d.last_error || '';
    const latency = d.last_latency_ms ? d.last_latency_ms + 'ms' : '-';

    html += '<div class="provider-card" style="margin-bottom:12px;border-left:3px solid ' + color + ';' + (isConfigured ? '' : 'opacity:.6') + '">' +
      '<div class="provider-icon" style="color:' + p.color + '">' + p.icon + '</div>' +
      '<div class="provider-info" style="flex:1">' +
      '<div class="provider-name">' + p.name + ' <span style="font-size:11px;color:var(--text3);font-weight:400">' + (d.model || p.model) + '</span></div>' +
      '<div class="provider-detail" style="margin:2px 0">Status: <strong style="color:' + color + '">' + statusLabel + '</strong>' + (d.attempts > 0 ? ' | ' + d.successes + ' ok / ' + d.failures + ' fail | Latency: ' + latency : '') + '</div>' +
      '<div style="font-size:11px;margin:4px 0;padding:6px 8px;border-radius:4px;background:' + (ds === 'operational' ? 'rgba(34,197,94,.08)' : ds === 'not_configured' ? 'rgba(148,163,184,.08)' : 'rgba(239,68,68,.08)') + ';color:' + (ds === 'operational' ? 'var(--green)' : ds === 'not_configured' ? 'var(--text3)' : '#ef4444') + ';line-height:1.4">' +
      '<strong>Why:</strong> ' + esc(reason) +
      (lastErr && ds !== 'operational' && ds !== 'not_configured' ? '<br><strong>Raw error:</strong> <span style="opacity:.7">' + esc(lastErr) + '</span>' : '') +
      (!d.key_format_valid && ds === 'not_configured' && p.id !== 'local' ? '<br><strong>Fix:</strong> Set <code style="background:rgba(255,255,255,.06);padding:1px 4px;border-radius:3px">' + p.id.toUpperCase() + '_API_KEY</code> environment variable' : '') +
      '</div>' +
      '<div class="progress"><div class="progress-fill" style="width:' + (isConfigured ? Math.max(pct, 5) : 0) + '%;background:' + color + '"></div></div>' +
      '</div></div>';
  });
  pc.innerHTML = html;
}

function renderCircuitBreakerDetail(cb, configured, diags) {
  let html = '<div style="font-size:13px;color:var(--text2)">' +
    '<div>Failure threshold: <strong>' + (cb && cb.failure_threshold || 5) + '</strong></div>' +
    '<div>Recovery timeout: <strong>' + (cb && cb.recovery_timeout_seconds || 30) + 's</strong></div>' +
    '<div style="margin-top:8px">';
  ALL_PROVIDERS.forEach(p => {
    const d = diags[p.id] || {};
    const isConfigured = configured.indexOf(p.id) !== -1 || d.configured;
    const ds = d.status || 'unknown';
    const badgeClass = ds === 'operational' ? 'badge-low' : ds === 'cooldown' ? 'badge-med' : (ds === 'error' || ds === 'circuit_open') ? 'badge-crit' : isConfigured ? 'badge-info' : 'badge-purple';
    const label = ds === 'operational' ? (d.successes > 0 ? 'OK' : 'READY') : ds === 'cooldown' ? 'COOLDOWN' : ds === 'error' ? 'ERROR' : ds === 'circuit_open' ? 'CB OPEN' : isConfigured ? 'READY' : 'N/A';
    const opacity = isConfigured || ds === 'operational' ? '1' : '.5';
    html += '<span class="badge ' + badgeClass + '" style="margin-right:4px;margin-bottom:4px;display:inline-block;opacity:' + opacity + '">' + p.id + ': ' + label + '</span>';
  });
  html += '</div></div>';
  document.getElementById('circuitBreakerDetail').innerHTML = html;
}

function renderDedupDetail(dedup) {
  const sevTtl = (dedup && dedup.severity_ttl) || {};
  let html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;font-size:13px">' +
    '<div><span style="color:var(--text3)">Total Alerts:</span><br><strong>' + (dedup && dedup.total_alerts || 0) + '</strong></div>' +
    '<div><span style="color:var(--text3)">Cache Hits:</span><br><strong>' + (dedup && dedup.hits || 0) + '</strong></div>' +
    '<div><span style="color:var(--text3)">Cache Misses:</span><br><strong>' + (dedup && dedup.misses || 0) + '</strong></div>' +
    '<div><span style="color:var(--text3)">Base TTL:</span><br><strong>' + (dedup && dedup.ttl_seconds || 60) + 's</strong></div>' +
    '<div><span style="color:var(--text3)">Evictions:</span><br><strong>' + (dedup && dedup.evictions || 0) + '</strong></div>' +
    '<div><span style="color:var(--text3)">Hit Rate:</span><br><strong>' + (dedup && dedup.hit_rate_percent || 0) + '%</strong></div>' +
    '</div>';

  // Severity-aware TTL tiers
  if (sevTtl.critical_gte8 !== undefined) {
    html += '<div style="margin-top:12px;font-size:12px">' +
      '<strong style="color:var(--text3);font-size:11px;text-transform:uppercase;letter-spacing:.5px">Severity-Aware TTL</strong>' +
      '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:6px">' +
      '<div style="padding:6px 10px;border-radius:6px;background:rgba(239,68,68,.08);border-left:3px solid var(--red);font-size:12px"><span style="color:var(--red);font-weight:600">Critical (&#x2265;8)</span><br>' + sevTtl.critical_gte8 + 's</div>' +
      '<div style="padding:6px 10px;border-radius:6px;background:rgba(249,115,22,.08);border-left:3px solid var(--orange);font-size:12px"><span style="color:var(--orange);font-weight:600">High (&#x2265;6)</span><br>' + sevTtl.high_gte6 + 's</div>' +
      '<div style="padding:6px 10px;border-radius:6px;background:rgba(234,179,8,.08);border-left:3px solid var(--yellow);font-size:12px"><span style="color:var(--yellow);font-weight:600">Medium (&#x2265;4)</span><br>' + sevTtl.medium_gte4 + 's</div>' +
      '<div style="padding:6px 10px;border-radius:6px;background:rgba(34,197,94,.08);border-left:3px solid var(--green);font-size:12px"><span style="color:var(--green);font-weight:600">Low (&lt;4)</span><br>' + sevTtl.low_lt4 + 's</div>' +
      '</div></div>';
  }

  document.getElementById('dedupDetail').innerHTML = html;
}

/** Reset all circuit breakers and trigger refresh. */
export function resetCircuitBreakers(refreshFn) {
  api.resetCircuitBreakers().then(() => {
    if (typeof refreshFn === 'function') refreshFn();
  });
}

// ── Operator Feedback Stats ──────────────────────────────────────────────

function renderFeedbackStats() {
  const el = document.getElementById('feedbackStats');
  if (!el) return;
  api.getFeedbackStats().then(stats => {
    if (!stats || stats._error) {
      el.innerHTML = '<div style="color:var(--text3);padding:12px">No feedback data yet — use the Detail panel in Live Alerts to rate LLM analyses</div>';
      return;
    }
    const total = stats.total || 0;
    const accurate = stats.accurate || 0;
    const inaccurate = stats.inaccurate || 0;
    const rate = stats.accuracy_rate != null ? (stats.accuracy_rate * 100).toFixed(0) : '--';
    const rateColor = rate >= 80 ? 'var(--green)' : rate >= 50 ? 'var(--yellow)' : 'var(--red)';
    const barW = rate !== '--' ? Math.max(2, parseInt(rate)) : 0;

    let html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;font-size:13px;margin-bottom:12px">';
    html += '<div><span style="color:var(--text3)">Total Reviews:</span><br><strong>' + total + '</strong></div>';
    html += '<div><span style="color:var(--text3)">Accurate:</span><br><strong style="color:var(--green)">' + accurate + '</strong></div>';
    html += '<div><span style="color:var(--text3)">Inaccurate:</span><br><strong style="color:var(--red)">' + inaccurate + '</strong></div>';
    html += '<div><span style="color:var(--text3)">Accuracy Rate:</span><br><strong style="color:' + rateColor + '">' + rate + '%</strong></div>';
    html += '</div>';

    // Accuracy bar
    if (total > 0) {
      html += '<div style="height:20px;background:var(--bg3);border-radius:4px;overflow:hidden;position:relative">';
      html += '<div style="height:100%;width:' + barW + '%;background:' + rateColor + ';border-radius:4px;transition:width .5s"></div>';
      html += '<span style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);font-size:10px;font-weight:600;color:var(--text)">' + rate + '% accuracy</span>';
      html += '</div>';
    }

    // Recent feedback
    if (stats.recent && stats.recent.length) {
      html += '<div style="margin-top:12px;font-size:12px">';
      html += '<strong style="color:var(--text3);font-size:11px;text-transform:uppercase;letter-spacing:.5px">Recent Feedback</strong>';
      html += '<div style="margin-top:6px;display:flex;flex-direction:column;gap:4px">';
      stats.recent.slice(0, 5).forEach(f => {
        const icon = f.was_accurate ? '&#x2714;' : '&#x2718;';
        const color = f.was_accurate ? 'var(--green)' : 'var(--red)';
        const ts = f.timestamp ? new Date(f.timestamp).toLocaleString() : '';
        html += '<div style="display:flex;align-items:center;gap:8px;padding:4px 8px;background:rgba(255,255,255,.02);border-radius:4px">';
        html += '<span style="color:' + color + '">' + icon + '</span>';
        html += '<span style="font-size:11px;color:var(--text2)">Alert ' + esc(f.analysis_id || '?') + '</span>';
        html += '<span style="margin-left:auto;font-size:10px;color:var(--text3)">' + ts + '</span>';
        html += '</div>';
      });
      html += '</div></div>';
    }

    el.innerHTML = html;
  }).catch(() => {
    el.innerHTML = '<div style="color:var(--text3);padding:12px">Unable to load feedback stats</div>';
  });
}
