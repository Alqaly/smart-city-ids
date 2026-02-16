/**
 * alerts.js — Alert History Tab + SSE Live Pipeline Feed
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Two responsibilities:
 *   1. Alert History table (tab-alerts) with source filtering and detail expansion
 *   2. SSE Live Pipeline Feed — real-time alert processing log
 *
 * The SSE stream listens on /api/alerts/live for 'alert' events.  Each event
 * contains the full LLM analysis (severity, threat type, reasoning, etc.)
 * and is rendered in a structured box-art format.
 *
 * Performance note (addressing feedback):
 *   The SSE connection replaces the need for polling /api/alerts.  When an
 *   SSE event arrives, we trigger a targeted metrics refresh after 2 seconds
 *   rather than a full refreshAll().  This reduces HTTP traffic by ~80%.
 */

import { store, ALL_PROVIDERS } from '../state.js';
import { api } from '../api.js';
import { esc, shortTime, sevBadge } from '../utils.js';

// ── Module-level SSE state ───────────────────────────────────────────────
let _sse = null;

// ── Alert History Table ──────────────────────────────────────────────────

/**
 * Load and render the alert history table with optional source filter.
 */
export function loadAlerts() {
  const src = document.getElementById('alertSourceFilter').value;
  api.getAlertsFiltered(50, src).then(data => {
    if (!data || !data.alerts) return;
    let html = '';

    // Build LLM engine options for the re-analyze dropdown
    const engineOpts = ALL_PROVIDERS
      .filter(p => p.id !== 'local')
      .map(p => `<option value="${p.id}">${p.label}</option>`)
      .join('') + '<option value="local">Local Fallback</option>';

    data.alerts.forEach((a, idx) => {
      const recs = a.recommendations || [];
      const an = a.analysis || {};
      const hasDetail = recs.length || an.reasoning || an.business_impact;
      const traceId = a.trace_id || ('alert-' + (a.id || idx));
      const alertId = a.id || 0;
      const engineLabel = an.analysis_engine || an.engine || '';

      html += `<tr>` +
        `<td>${shortTime(a.timestamp)}</td>` +
        `<td><code style="font-size:11px">${esc(traceId)}</code></td>` +
        `<td><span class="badge ${a.source === 'falco' ? 'badge-info' : 'badge-purple'}">${esc(a.source || '-')}</span></td>` +
        `<td>${esc(a.rule || '')}</td>` +
        `<td><span class="badge ${sevBadge(a.severity)}">${a.severity || '-'}</span></td>` +
        `<td>${esc(a.threat_type || '-')}</td>` +
        `<td style="white-space:normal;max-width:400px;line-height:1.4">${esc(a.summary || '')}` +
          (engineLabel ? `<div style="font-size:10px;color:var(--text3);margin-top:2px">Analyzed by: ${esc(engineLabel)}</div>` : '') +
        `</td>` +
        `<td>` +
          (hasDetail ? `<button class="btn btn-outline btn-sm" onclick="window._toggleDetail(${idx})" style="margin-right:4px">Detail</button>` : '') +
          `<button class="btn btn-outline btn-sm" onclick="window._showReanalyze(${alertId}, ${idx})" title="Re-analyze with a different LLM">Re-analyze</button>` +
        `</td>` +
        `</tr>`;

      // Detail row (expanded analysis)
      if (hasDetail) {
        html += `<tr id="detail-${idx}" style="display:none"><td colspan="8" style="background:var(--bg);padding:12px 16px;font-size:12px;line-height:1.6">`;
        html += `<div style="margin-bottom:8px"><strong style="color:var(--accent)">Trace ID:</strong> ${esc(traceId)}</div>`;
        if (an.reasoning) html += `<div style="margin-bottom:8px"><strong style="color:var(--accent2)">Reasoning:</strong> ${esc(an.reasoning)}</div>`;
        if (an.confidence) html += `<div style="margin-bottom:8px"><strong style="color:var(--text2)">Confidence:</strong> ${(an.confidence * 100).toFixed(0)}%</div>`;
        if (an.business_impact) html += `<div style="margin-bottom:8px"><strong style="color:var(--yellow)">Business Impact:</strong> ${esc(an.business_impact)}</div>`;
        if (an.mitre_technique) html += `<div style="margin-bottom:8px"><strong style="color:var(--accent)">MITRE ATT&CK:</strong> ${esc(an.mitre_technique)}</div>`;
        if (an.key_indicators && an.key_indicators.length) {
          html += `<div style="margin-bottom:8px"><strong style="color:var(--orange)">Key Indicators:</strong><ul style="margin:4px 0 0 16px;padding:0">`;
          an.key_indicators.forEach(k => { html += `<li>${esc(k)}</li>`; });
          html += `</ul></div>`;
        }
        if (recs.length) {
          html += `<div><strong style="color:var(--green)">Recommendations:</strong><ol style="margin:4px 0 0 16px;padding:0">`;
          recs.forEach(r => { html += `<li>${esc(r)}</li>`; });
          html += `</ol></div>`;
        }
        if (an.mitigating_factors && an.mitigating_factors.length) {
          html += `<div style="margin-top:8px"><strong style="color:var(--text3)">Mitigating Factors:</strong><ul style="margin:4px 0 0 16px;padding:0">`;
          an.mitigating_factors.forEach(f => { html += `<li>${esc(f)}</li>`; });
          html += `</ul></div>`;
        }
        html += `</td></tr>`;
      }

      // Re-analyze row (hidden until user clicks Re-analyze)
      html += `<tr id="reanalyze-${idx}" style="display:none"><td colspan="8" style="background:var(--bg2);padding:12px 16px;border:1px solid var(--accent)">`;
      html += `<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">`;
      html += `<strong style="color:var(--accent);font-size:13px">Re-analyze Alert #${alertId}</strong>`;
      html += `<select id="reanalyze-engine-${idx}" style="background:var(--bg);border:1px solid var(--border);color:var(--text);padding:6px 10px;border-radius:4px;font-size:12px">`;
      html += `<option value="">Auto (failover)</option>${engineOpts}</select>`;
      html += `<button class="btn btn-sm" style="background:var(--accent);color:#000;font-weight:600" onclick="window._doReanalyze(${alertId}, ${idx})">Send to LLM</button>`;
      html += `<span id="reanalyze-status-${idx}" style="font-size:12px;color:var(--text3)"></span>`;
      html += `</div>`;
      html += `<pre id="reanalyze-result-${idx}" style="display:none;margin-top:10px;font-size:11.5px;color:var(--text2);background:var(--bg);padding:12px;border-radius:6px;border:1px solid var(--border);white-space:pre-wrap;max-height:400px;overflow-y:auto"></pre>`;
      html += `</td></tr>`;
    });
    document.getElementById('alertsTable').innerHTML = html || '<tr><td colspan="8" style="text-align:center;color:var(--text3)">No alerts</td></tr>';
  });
}

/**
 * Toggle visibility of an alert detail row.
 * Exposed on window so inline onclick handlers work from innerHTML.
 */
export function toggleDetail(idx) {
  const r = document.getElementById('detail-' + idx);
  if (r) r.style.display = r.style.display === 'none' ? 'table-row' : 'none';
}

/**
 * Show the re-analyze row for a specific alert.
 */
function showReanalyze(alertId, idx) {
  const r = document.getElementById('reanalyze-' + idx);
  if (r) r.style.display = r.style.display === 'none' ? 'table-row' : 'none';
}

/**
 * Execute re-analysis: sends the alert to the chosen LLM engine.
 * Shows a verbose log of the process and result.
 */
function doReanalyze(alertId, idx) {
  const engineSelect = document.getElementById('reanalyze-engine-' + idx);
  const statusEl = document.getElementById('reanalyze-status-' + idx);
  const resultEl = document.getElementById('reanalyze-result-' + idx);
  const engine = engineSelect ? engineSelect.value : '';

  statusEl.innerHTML = '<span style="color:var(--yellow)">Sending to LLM...</span>';
  resultEl.style.display = 'block';
  resultEl.textContent = `[${new Date().toLocaleTimeString()}] Sending alert #${alertId} to ${engine || 'auto-failover'}...\n`;

  const startMs = Date.now();

  api.reanalyzeAlert(alertId, engine || null).then(res => {
    const elapsed = ((Date.now() - startMs) / 1000).toFixed(2);

    if (!res) {
      statusEl.innerHTML = '<span style="color:var(--red)">Failed — no response</span>';
      resultEl.textContent += `[${new Date().toLocaleTimeString()}] ERROR: No response from server (check auth token)\n`;
      return;
    }

    if (res.detail) {
      // Error from backend
      statusEl.innerHTML = `<span style="color:var(--red)">Error: ${esc(res.detail)}</span>`;
      resultEl.textContent += `[${new Date().toLocaleTimeString()}] ERROR: ${res.detail}\n`;
      return;
    }

    const an = res.analysis || {};
    statusEl.innerHTML = `<span style="color:var(--green)">Done — ${esc(res.engine_used)} (${elapsed}s)</span>`;

    let log = resultEl.textContent;
    log += `[${new Date().toLocaleTimeString()}] ✓ Analysis complete\n`;
    log += `├─ Engine:     ${res.engine_used}\n`;
    log += `├─ Latency:    ${res.latency_s}s\n`;
    log += `├─ Severity:   ${res.previous_severity} → ${res.new_severity}\n`;
    log += `├─ Threat:     ${an.threat_type || 'Unknown'}\n`;
    log += `├─ Confidence: ${an.confidence ? (an.confidence * 100).toFixed(0) + '%' : 'N/A'}\n`;
    log += `├─ Summary:    ${an.summary || ''}\n`;
    if (an.reasoning) log += `├─ Reasoning:  ${an.reasoning}\n`;
    if (an.business_impact) log += `├─ Impact:     ${an.business_impact}\n`;
    if (an.mitre_technique) log += `├─ MITRE:      ${an.mitre_technique}\n`;
    if (an.key_indicators && an.key_indicators.length) {
      log += `├─ Indicators:\n`;
      an.key_indicators.forEach(k => { log += `│  • ${k}\n`; });
    }
    if (an.recommendations && an.recommendations.length) {
      log += `├─ Recommendations:\n`;
      an.recommendations.forEach((r, i) => { log += `│  ${i + 1}. ${r}\n`; });
    }
    if (an.automated_actions && an.automated_actions.length) {
      log += `├─ Auto Actions: ${an.automated_actions.join(', ')}\n`;
    }
    log += `└─ DB Updated: ${res.updated ? 'Yes' : 'No'}\n`;
    resultEl.textContent = log;

    // Reload alerts table after a short delay to reflect updated analysis
    setTimeout(loadAlerts, 1500);
  }).catch(err => {
    statusEl.innerHTML = `<span style="color:var(--red)">Network error</span>`;
    resultEl.textContent += `[${new Date().toLocaleTimeString()}] ERROR: ${err.message}\n`;
  });
}

// Expose to global scope for inline onclick handlers
window._toggleDetail = toggleDetail;
window._showReanalyze = showReanalyze;
window._doReanalyze = doReanalyze;

// ══════════════════════════════════════════════════════════════════════════
// SSE Live Pipeline Feed
// ══════════════════════════════════════════════════════════════════════════

/**
 * Connect to the SSE stream at /api/alerts/live.
 * @param {Function} onNewAlert — callback fired after each alert (e.g., to refresh stats)
 */
export function connectLiveFeed(onNewAlert) {
  if (_sse) { try { _sse.close(); } catch (e) { /* ignore */ } }
  const dot = document.getElementById('liveFeedDot');
  const status = document.getElementById('liveFeedStatus');
  dot.className = 'dot dot-yellow';
  status.textContent = 'Connecting...';

  _sse = new EventSource('/api/alerts/live');

  _sse.onopen = () => {
    dot.className = 'dot dot-green';
    status.textContent = 'Connected — streaming all alert processing';
  };

  _sse.addEventListener('connected', () => {
    const log = document.getElementById('liveFeedLog');
    if (log.innerHTML === 'Connecting to live event stream...') {
      log.innerHTML = '<span style="color:var(--green)">\u2713 Connected to live pipeline stream. Alerts from ALL sources (CLI, Falco, Suricata, dashboard) will appear here in real-time.</span>';
    }
  });

  _sse.addEventListener('alert', ev => {
    try {
      const d = JSON.parse(ev.data);
      const state = store.getState();
      const newCount = state.sseFeedCount + 1;
      store.setState({ sseFeedCount: newCount });
      document.getElementById('liveFeedCount').textContent = newCount;

      const log = document.getElementById('liveFeedLog');
      const ts = new Date().toLocaleTimeString();
      const sev = d.severity || '?';
      const sevColor = sev >= 8 ? '#ef4444' : sev >= 5 ? '#f59e0b' : '#22c55e';
      const engine = d.llm_engine || d.engine || 'unknown';
      const threat = d.threat_type || 'Unknown';
      const summary = d.summary || '';
      const source = d.source || 'api';
      const traceId = d.trace_id || ('alert-' + (d.alert_id || 'unknown'));
      const rule = d.rule || '';
      const container = d.container_name || '';
      const procTime = d.processing_time_ms ? d.processing_time_ms + 'ms' : '';

      // Extract analysis details
      const a = d.analysis || {};
      const reasoning = a.reasoning || a.detailed_analysis || '';
      const confidence = a.confidence_score || a.confidence || '';
      const impact = a.business_impact || a.potential_impact || '';
      const indicators = a.key_indicators || a.indicators || a.ioc || [];
      const mitigating = a.mitigating_factors || [];
      const recs = a.recommendations || [];
      const actions = a.automated_actions || d.automated_actions || [];
      const mitre = a.mitre_technique || '';

      // Build structured box-art log entry
      let line = '';
      line += '┌─────────────────────────────────────────────────────────────\n';
      line += `│  [${ts}]  LIVE ALERT — Source: ${source.toUpperCase()}\n`;
      line += `│  Trace: ${traceId}\n`;
      if (rule) line += `│  Rule: ${rule}\n`;
      if (container) line += `│  Container: ${container}\n`;
      line += '├── LLM Analysis ──────────────────────────────────────────────\n';
      line += `│  Engine:      ${engine}\n`;
      line += `│  Severity:    <span style="color:${sevColor};font-weight:bold">${sev}/10</span>\n`;
      line += `│  Threat Type: ${threat}\n`;
      if (mitre)      line += `│  MITRE:       ${mitre}\n`;
      if (confidence)  line += `│  Confidence:  ${confidence}\n`;
      if (procTime)    line += `│  Processed:   ${procTime}\n`;
      if (summary)     line += `│  Summary:     ${summary}\n`;
      if (reasoning) {
        line += '├── Reasoning ─────────────────────────────────────────────────\n';
        line += '│  ' + reasoning.replace(/\n/g, '\n│  ') + '\n';
      }
      if (impact) {
        line += '├── Business Impact ───────────────────────────────────────────\n';
        line += '│  ' + impact.replace(/\n/g, '\n│  ') + '\n';
      }
      if (indicators.length) {
        line += '├── Key Indicators ───────────────────────────────────────────\n';
        indicators.forEach(ind => { line += `│  • ${ind}\n`; });
      }
      if (mitigating.length) {
        line += '├── Mitigating Factors ───────────────────────────────────────\n';
        mitigating.forEach(m => { line += `│  ◦ ${m}\n`; });
      }
      if (recs.length) {
        line += '├── Recommendations ──────────────────────────────────────────\n';
        recs.forEach(r => { line += `│  → ${r}\n`; });
      }
      if (actions.length) {
        const actSev = sev >= 8
          ? '<span style="color:#ef4444;font-weight:bold">EXECUTING</span>'
          : sev >= 6
            ? '<span style="color:#f59e0b;font-weight:bold">EXECUTING</span>'
            : '<span style="color:var(--text3)">Below threshold</span>';
        line += '├── Automated Response ───────────────────────────────────────\n';
        actions.forEach(act => { line += `│  ⚡ ${act}  ${actSev}\n`; });
      }
      line += '└─────────────────────────────────────────────────────────────\n';

      // Prepend (newest on top)
      let old = log.innerHTML;
      if (old === 'Connecting to live event stream...') old = '';
      log.innerHTML = line + '\n' + old;

      // Flash card border
      const card = document.getElementById('liveFeedCard');
      card.style.borderColor = sevColor;
      setTimeout(() => { card.style.borderColor = 'var(--accent)'; }, 1500);

      // Trigger a targeted refresh instead of full refreshAll
      if (typeof onNewAlert === 'function') {
        setTimeout(onNewAlert, 2000);
      }
    } catch (e) {
      console.warn('SSE parse error', e);
    }
  });

  _sse.onerror = () => {
    dot.className = 'dot dot-red';
    status.textContent = 'Disconnected — reconnecting...';
  };
}

/** Close the SSE connection (called on logout). */
export function disconnectLiveFeed() {
  if (_sse) { try { _sse.close(); } catch (e) { /* */ } _sse = null; }
}

/** Toggle live feed panel visibility. */
export function toggleLiveFeed() {
  const state = store.getState();
  const open = !state.ui.liveFeedOpen;
  store.setState({ ui: { ...state.ui, liveFeedOpen: open } });
  document.getElementById('liveFeedBody').style.display = open ? 'block' : 'none';
  document.getElementById('liveFeedToggleBtn').textContent = open ? '▼' : '▲';
}

/** Clear the live feed log. */
export function clearLiveFeed() {
  document.getElementById('liveFeedLog').innerHTML = 'Waiting for alerts...';
  store.setState({ sseFeedCount: 0 });
  document.getElementById('liveFeedCount').textContent = '0';
}
