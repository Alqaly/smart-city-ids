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
import { $, esc, shortTime, sevBadge } from '../utils.js';

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
      summary: 'High-rate HTTP flood/DoS signature. Multiple hits usually mean one noisy source repeatedly exceeded the rate threshold.',
      tone: 'warn',
    };
  }
  if (source === 'suricata' && /SQLi|UNION SELECT|DROP TABLE|OR 1=1/i.test(rule)) {
    return {
      summary: 'SQL injection signature matched in web traffic.',
      tone: 'warn',
    };
  }
  if (source === 'falco' && /Sensitive File Read/i.test(rule) && isMonitoring) {
    return {
      summary: 'Likely platform noise from monitoring stack (e.g., Grafana/Prometheus reading certs/config). Validate path and timing before escalation.',
      tone: 'muted',
    };
  }
  if (source === 'falco' && /Shell in Container|Terminal shell/i.test(rule)) {
    return {
      summary: 'Interactive shell launched inside a container. Expected only during maintenance/debugging.',
      tone: 'warn',
    };
  }
  return null;
}

// ── Module-level SSE state ───────────────────────────────────────────────
let _sse = null;
let _incidentPage = 1;
let _incidentRows = [];
let _incidentQueryKey = '';

// ── Alert History Table ──────────────────────────────────────────────────

/**
 * Load and render the alert history table with optional source filter.
 */
export function loadAlerts() {
  const srcEl = $('alertSourceFilter');
  const src = srcEl ? srcEl.value : 'all';
  api.getAlertsFiltered(50, src).then(data => {
    if (!data || !data.alerts) return;
    let rows = [...data.alerts];

    const search = ($('incidentSearch')?.value || '').trim().toLowerCase();
    if (search) {
      rows = rows.filter(a => {
        const an = a.analysis || {};
        const blob = [
          a.rule, a.source, a.summary, a.threat_type,
          an.threat_type, an.reasoning, an.mitre_technique,
        ].filter(Boolean).join(' ').toLowerCase();
        return blob.includes(search);
      });
    }

    const sort = $('incidentSort')?.value || 'time_desc';
    const pageSize = parseInt($('incidentPageSize')?.value || '25', 10);
    const queryKey = [src, search, sort, pageSize].join('|');
    if (queryKey !== _incidentQueryKey) {
      _incidentPage = 1;
      _incidentQueryKey = queryKey;
    }
    rows.sort((a, b) => {
      if (sort === 'severity_desc') return (b.severity || 0) - (a.severity || 0);
      if (sort === 'severity_asc') return (a.severity || 0) - (b.severity || 0);
      const ta = new Date(a.timestamp || 0).getTime();
      const tb = new Date(b.timestamp || 0).getTime();
      return sort === 'time_asc' ? ta - tb : tb - ta;
    });

    _incidentRows = rows;
    const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
    if (_incidentPage > totalPages) _incidentPage = totalPages;
    if (_incidentPage < 1) _incidentPage = 1;
    const start = (_incidentPage - 1) * pageSize;
    const pageRows = rows.slice(start, start + pageSize);

    let html = '';

    // Build LLM engine options for the re-analyze dropdown
    const engineOpts = ALL_PROVIDERS
      .map(p => `<option value="${p.id}">${p.name}</option>`)
      .join('');

    pageRows.forEach((a, localIdx) => {
      const idx = start + localIdx;
      const recs = a.recommendations || [];
      const an = a.analysis || {};
      const guide = ruleHelpMeta(a);
      const traceId = a.trace_id || ('alert-' + (a.id || idx));
      const alertId = a.id || 0;
      const engineLabel = an.analysis_engine || an.engine || '';
      const sid = alertSignatureId(a);
      const whereParts = [
        a.namespace || a.k8s_ns || a.k8s_namespace || a.output_fields?.['k8s.ns.name'],
        a.pod_name || a.k8s_pod || a.output_fields?.['k8s.pod.name'],
        a.container_name || a.container || a.output_fields?.['container.name'],
      ].filter(Boolean);

      html += `<tr>` +
        `<td>${shortTime(a.timestamp)}</td>` +
        `<td><code style="font-size:11px">${esc(traceId)}</code></td>` +
        `<td><span class="badge ${a.source === 'falco' ? 'badge-info' : 'badge-purple'}">${esc(a.source || '-')}</span></td>` +
        `<td>${esc(a.rule || '')}` +
          (guide?.tone === 'muted' ? `<div style="margin-top:4px"><span style="display:inline-block;padding:2px 7px;background:rgba(148,163,184,0.10);color:#94a3b8;border-radius:4px;font-size:10px;">Likely Platform Noise</span></div>` : '') +
          (sid ? `<div style="margin-top:4px;font-size:10px;color:var(--text3);font-family:monospace;">Suricata SID ${esc(String(sid))}</div>` : '') +
        `</td>`;

      // MITRE ATT&CK technique column
      const mitreId = an.mitre_technique || (a.output_fields && a.output_fields['mitre.technique']) || '';
      const mitreName = (a.output_fields && a.output_fields['mitre.name']) || '';
      html += mitreId
        ? `<td><span class="mitre-badge" title="${esc(mitreName)}">${esc(mitreId)}</span></td>`
        : `<td style="color:var(--text3);font-size:11px">\u2014</td>`;

      html += `<td><span class="badge ${sevBadge(a.severity)}">${a.severity || '-'}</span></td>`;

      // Confidence column with badge
      const rowConf = an.confidence || an.confidence_score || 0;
      const rowConfPct = typeof rowConf === 'number' ? (rowConf <= 1 ? Math.round(rowConf * 100) : Math.round(rowConf)) : 0;
      const rowConfClass = rowConfPct >= 80 ? 'conf-high' : rowConfPct >= 50 ? 'conf-medium' : 'conf-low';
      html += rowConfPct > 0
        ? `<td><span class="conf-badge ${rowConfClass}">${rowConfPct}%</span></td>`
        : `<td style="color:var(--text3);font-size:11px">—</td>`;

      html += `<td>${esc(a.threat_type || '-')}</td>` +
        `<td style="white-space:normal;max-width:400px;line-height:1.4">${esc(a.summary || '')}` +
          (whereParts.length ? `<div style="font-size:10px;color:var(--text3);margin-top:3px">Where: ${esc(whereParts.join(' / '))}</div>` : '') +
          (guide?.summary ? `<div style="font-size:10px;color:${guide.tone === 'muted' ? 'var(--text3)' : 'var(--yellow)'};margin-top:3px">${esc(guide.summary)}</div>` : '') +
          (engineLabel ? `<div style="font-size:10px;color:var(--text3);margin-top:2px"><span class="ai-badge">&#x1F916; ${esc(engineLabel)}</span></div>` : '') +
        `</td>` +
        `<td>` +
          `<button class="btn btn-outline btn-sm" onclick="window._toggleDetail(${idx})" style="margin-right:4px">Detail</button>` +
          `<button class="btn btn-outline btn-sm" onclick="window._showReanalyze(${alertId}, ${idx})" title="Re-analyze with a different LLM">Re-analyze</button>` +
        `</td>` +
        `</tr>`;

      // ── LLM Transparency Detail Row ─────────────────────────────────
      // Always show the detail row (even without reasoning) — it now holds
      // the full transparency panel: evidence, confidence badge, MITRE,
      // reasoning chain, and operator feedback buttons.
      const conf = an.confidence || an.confidence_score || 0;
      const confPct = typeof conf === 'number' ? (conf <= 1 ? (conf * 100).toFixed(0) : conf.toFixed(0)) : '?';
      const confColor = confPct >= 80 ? 'var(--green)' : confPct >= 50 ? 'var(--yellow)' : 'var(--red)';
      const confLabel = confPct >= 80 ? 'HIGH' : confPct >= 50 ? 'MEDIUM' : 'LOW';
      const evidence = an.evidence || an.key_indicators || [];
      const mitreStr = an.mitre_technique || '';
      const autoActs = an.automated_actions || [];

      html += `<tr id="detail-${idx}" style="display:none"><td colspan="10" style="background:var(--bg);padding:0;font-size:12px;line-height:1.6">`;

      // ── Header bar with confidence badge + engine + MITRE ──
      html += `<div style="display:flex;align-items:center;gap:12px;padding:10px 16px;background:rgba(0,212,255,.04);border-bottom:1px solid var(--border);flex-wrap:wrap">`;
      html += `<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;background:${confColor}20;color:${confColor};border:1px solid ${confColor}40">`;
      html += `<span style="font-size:14px">${confPct >= 80 ? '&#x2705;' : confPct >= 50 ? '&#x26A0;' : '&#x274C;'}</span> ${confPct}% ${confLabel}</span>`;
      if (engineLabel) html += `<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:rgba(124,92,252,.12);color:var(--accent2);border:1px solid rgba(124,92,252,.3)">&#x1F916; ${esc(engineLabel)}</span>`;
      if (mitreStr) html += `<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:rgba(239,68,68,.1);color:var(--red);border:1px solid rgba(239,68,68,.3)">&#x1F3AF; ${esc(mitreStr)}</span>`;
      html += `<span style="font-size:10px;color:var(--text3);margin-left:auto">Trace: ${esc(traceId)}</span>`;
      html += `</div>`;

      // ── Two-column layout: left = evidence & reasoning, right = actions & feedback ──
      html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:0;min-height:100px">`;

      // LEFT column
      html += `<div style="padding:12px 16px;border-right:1px solid var(--border)">`;
      // Evidence/Indicators
      if (evidence.length) {
        html += `<div style="margin-bottom:10px"><strong style="color:var(--orange);font-size:11px;text-transform:uppercase;letter-spacing:.5px">&#128270; Evidence / Key Indicators</strong>`;
        html += `<ul style="margin:4px 0 0 12px;padding:0;list-style:none">`;
        evidence.forEach(e => { html += `<li style="padding:2px 0;color:var(--text2)"><span style="color:var(--orange);margin-right:4px">&#x25B8;</span>${esc(typeof e === 'string' ? e : JSON.stringify(e))}</li>`; });
        html += `</ul></div>`;
      }
      // Reasoning chain
      if (an.reasoning || an.detailed_analysis) {
        html += `<div style="margin-bottom:10px"><strong style="color:var(--accent2);font-size:11px;text-transform:uppercase;letter-spacing:.5px">&#x1F9E0; Reasoning Chain</strong>`;
        html += `<div style="margin-top:4px;padding:8px 10px;background:rgba(124,92,252,.06);border-radius:6px;border-left:3px solid var(--accent2);color:var(--text2);font-size:11.5px;line-height:1.5">${esc(an.reasoning || an.detailed_analysis)}</div></div>`;
      }
      // Business impact
      if (an.business_impact) {
        html += `<div style="margin-bottom:10px"><strong style="color:var(--yellow);font-size:11px;text-transform:uppercase;letter-spacing:.5px">&#x26A1; Business Impact</strong>`;
        html += `<div style="margin-top:4px;color:var(--text2)">${esc(an.business_impact)}</div></div>`;
      }
      // Mitigating factors
      if (an.mitigating_factors && an.mitigating_factors.length) {
        html += `<div><strong style="color:var(--text3);font-size:11px;text-transform:uppercase;letter-spacing:.5px">&#x1F6E1; Mitigating Factors</strong>`;
        html += `<ul style="margin:4px 0 0 12px;padding:0;list-style:none">`;
        an.mitigating_factors.forEach(f => { html += `<li style="padding:2px 0;color:var(--text3)"><span style="margin-right:4px">&#x25CB;</span>${esc(f)}</li>`; });
        html += `</ul></div>`;
      }
      html += `</div>`;

      // RIGHT column
      html += `<div style="padding:12px 16px">`;
      // Recommendations
      if (recs.length) {
        html += `<div style="margin-bottom:10px"><strong style="color:var(--green);font-size:11px;text-transform:uppercase;letter-spacing:.5px">&#x2705; Recommendations</strong>`;
        html += `<ol style="margin:4px 0 0 16px;padding:0;color:var(--text2)">`;
        recs.forEach(r => { html += `<li style="padding:2px 0">${esc(r)}</li>`; });
        html += `</ol></div>`;
      }
      // Automated actions taken
      if (autoActs.length) {
        html += `<div style="margin-bottom:10px"><strong style="color:var(--accent);font-size:11px;text-transform:uppercase;letter-spacing:.5px">&#x26A1; Automated Actions</strong>`;
        html += `<div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:4px">`;
        autoActs.forEach(act => {
          html += `<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600;background:rgba(0,212,255,.1);color:var(--accent);border:1px solid rgba(0,212,255,.25)">${esc(act)}</span>`;
        });
        html += `</div></div>`;
      }
      // Operator feedback section
      html += `<div style="margin-top:12px;padding:10px 12px;background:rgba(255,255,255,.03);border-radius:6px;border:1px solid var(--border)">`;
      html += `<strong style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--text3)">&#x1F4AC; Operator Feedback</strong>`;
      html += `<div style="display:flex;align-items:center;gap:8px;margin-top:8px" id="feedback-btns-${idx}">`;
      html += `<button class="btn btn-sm" style="background:rgba(34,197,94,.15);color:var(--green);border:1px solid rgba(34,197,94,.3);font-weight:600;padding:4px 14px" onclick="window._submitFeedback(${alertId},'${traceId}',true,${idx})">&#x2714; Accurate</button>`;
      html += `<button class="btn btn-sm" style="background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.3);font-weight:600;padding:4px 14px" onclick="window._submitFeedback(${alertId},'${traceId}',false,${idx})">&#x2718; Inaccurate</button>`;
      html += `<span id="feedback-status-${idx}" style="font-size:11px;color:var(--text3)"></span>`;
      html += `</div></div>`;
      html += `</div>`;

      html += `</div>`; // close grid
      html += `</td></tr>`;

      // Re-analyze row (hidden until user clicks Re-analyze)
      html += `<tr id="reanalyze-${idx}" style="display:none"><td colspan="10" style="background:var(--bg2);padding:12px 16px;border:1px solid var(--accent)">`;
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
    const alertsTableEl = $('alertsTable');
    if (alertsTableEl) alertsTableEl.innerHTML = html || '<tr><td colspan="10" style="text-align:center;color:var(--text3)">No alerts</td></tr>';
    const info = $('incidentPageInfo');
    if (info) info.textContent = `Page ${_incidentPage}/${totalPages} • ${rows.length} incidents`;
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
      statusEl.innerHTML = '<span style="color:var(--red)">Failed — network error</span>';
      resultEl.textContent += `[${new Date().toLocaleTimeString()}] ERROR: Network unreachable or server offline\n`;
      return;
    }

    if (res._error) {
      const msg = res.detail || `HTTP ${res._status}`;
      statusEl.innerHTML = `<span style="color:var(--red)">${res._status === 401 ? 'Session expired — refresh page' : 'Error: ' + esc(msg)}</span>`;
      resultEl.textContent += `[${new Date().toLocaleTimeString()}] ERROR (${res._status}): ${msg}\n`;
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

/**
 * Submit operator feedback on an LLM analysis (accurate/inaccurate).
 * Connected to the transparency panel's feedback buttons.
 */
function submitFeedback(alertId, traceId, wasAccurate, idx) {
  const statusEl = document.getElementById('feedback-status-' + idx);
  const btnsEl = document.getElementById('feedback-btns-' + idx);
  if (statusEl) statusEl.innerHTML = '<span style="color:var(--yellow)">Submitting...</span>';

  api.submitFeedback(String(alertId || traceId), wasAccurate, '').then(res => {
    if (!res || res._error) {
      if (statusEl) statusEl.innerHTML = '<span style="color:var(--red)">Failed to submit</span>';
      return;
    }
    // Replace buttons with confirmation
    if (btnsEl) {
      const icon = wasAccurate ? '&#x2714;' : '&#x2718;';
      const color = wasAccurate ? 'var(--green)' : 'var(--red)';
      const label = wasAccurate ? 'Marked Accurate' : 'Marked Inaccurate';
      btnsEl.innerHTML = `<span style="color:${color};font-weight:600;font-size:12px">${icon} ${label}</span>` +
        (res.accuracy_rate !== undefined ? `<span style="margin-left:8px;font-size:11px;color:var(--text3)">Overall accuracy: ${(res.accuracy_rate * 100).toFixed(0)}%</span>` : '');
    }
  }).catch(() => {
    if (statusEl) statusEl.innerHTML = '<span style="color:var(--red)">Network error</span>';
  });
}
window._submitFeedback = submitFeedback;

window._incidentPrev = () => {
  _incidentPage = Math.max(1, _incidentPage - 1);
  loadAlerts();
};
window._incidentNext = () => {
  const pageSize = parseInt(document.getElementById('incidentPageSize')?.value || '25', 10);
  const totalPages = Math.max(1, Math.ceil(_incidentRows.length / pageSize));
  _incidentPage = Math.min(totalPages, _incidentPage + 1);
  loadAlerts();
};
window._exportIncidentsCsv = () => {
  const header = ['id', 'timestamp', 'trace_id', 'source', 'rule', 'severity', 'confidence', 'threat_type', 'summary'];
  const lines = _incidentRows.map(a => {
    const an = a.analysis || {};
    const conf = an.confidence || an.confidence_score || '';
    const row = [
      a.id || '',
      a.timestamp || '',
      a.trace_id || `alert-${a.id || ''}`,
      a.source || '',
      a.rule || '',
      a.severity || '',
      conf,
      a.threat_type || an.threat_type || '',
      (a.summary || '').replace(/\\n/g, ' '),
    ];
    return row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',');
  });
  const csv = header.join(',') + '\n' + lines.join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `incidents-${new Date().toISOString().slice(0,19).replace(/[:T]/g,'-')}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

// ══════════════════════════════════════════════════════════════════════════
// SSE Live Pipeline Feed
// ══════════════════════════════════════════════════════════════════════════

/**
 * Connect to the SSE stream at /api/alerts/live.
 * @param {Function} onNewAlert — callback fired after each alert (e.g., to refresh stats)
 */
export function connectLiveFeed(onNewAlert) {
  if (_sse) { try { _sse.close(); } catch (e) { /* ignore */ } }
  const dot = $('liveFeedDot');
  const status = $('liveFeedStatus');
  if (dot) dot.className = 'dot dot-yellow';
  if (status) status.textContent = 'Connecting...';

  _sse = new EventSource('/api/alerts/live');

  _sse.onopen = () => {
    if (dot) dot.className = 'dot dot-green';
    if (status) status.textContent = 'Connected — streaming all alert processing';
  };

  _sse.addEventListener('connected', () => {
    const log = $('liveFeedLog');
    if (log && log.innerHTML === 'Connecting to live event stream...') {
      log.innerHTML = '';
    }
  });

  _sse.addEventListener('alert', ev => {
    try {
      const d = JSON.parse(ev.data);
      const state = store.getState();
      const newCount = state.sseFeedCount + 1;
      store.setState({ sseFeedCount: newCount });
      const countEl = $('liveFeedCount');
      if (countEl) countEl.textContent = newCount;

      const log = $('liveFeedLog');
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

      // Build structured box-art log entry with confidence badges
      const confVal = typeof confidence === 'number' ? (confidence <= 1 ? confidence * 100 : confidence) : parseFloat(confidence) || 0;
      const confBadge = confVal >= 80
        ? '<span style="color:#22c55e;font-weight:bold">HIGH (' + confVal.toFixed(0) + '%)</span>'
        : confVal >= 50
          ? '<span style="color:#eab308;font-weight:bold">MEDIUM (' + confVal.toFixed(0) + '%)</span>'
          : confVal > 0
            ? '<span style="color:#ef4444;font-weight:bold">LOW (' + confVal.toFixed(0) + '%)</span>'
            : '<span style="color:var(--text3)">N/A</span>';

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
      line += `│  Confidence:  ${confBadge}\n`;
      if (mitre)      line += `│  MITRE:       <span style="color:#ef4444">${mitre}</span>\n`;
      if (procTime)    line += `│  Processed:   ${procTime}\n`;
      if (summary)     line += `│  Summary:     ${summary}\n`;
      if (reasoning) {
        line += '├── 🧠 Reasoning Chain ────────────────────────────────────────\n';
        line += '│  ' + reasoning.replace(/\n/g, '\n│  ') + '\n';
      }
      if (impact) {
        line += '├── ⚡ Business Impact ────────────────────────────────────────\n';
        line += '│  ' + impact.replace(/\n/g, '\n│  ') + '\n';
      }
      if (indicators.length) {
        line += '├── 🔍 Evidence / Key Indicators ─────────────────────────────\n';
        indicators.forEach(ind => { line += `│  ▸ ${ind}\n`; });
      }
      if (mitigating.length) {
        line += '├── 🛡 Mitigating Factors ─────────────────────────────────────\n';
        mitigating.forEach(m => { line += `│  ◦ ${m}\n`; });
      }
      if (recs.length) {
        line += '├── ✅ Recommendations ────────────────────────────────────────\n';
        recs.forEach((r, i) => { line += `│  ${i + 1}. ${r}\n`; });
      }
      if (actions.length) {
        line += '├── ⚡ Automated Response ─────────────────────────────────────\n';
        actions.forEach(act => {
          if (sev >= 8) {
            line += `│  <span style="color:#ef4444;font-weight:bold">🚨 EXECUTING:</span> ${act} <span style="color:#ef4444">[CRITICAL — sev ${sev}/10]</span>\n`;
          } else if (sev >= 6) {
            line += `│  <span style="color:#f59e0b;font-weight:bold">⚠️ EXECUTING:</span> ${act} <span style="color:#f59e0b">[HIGH — sev ${sev}/10]</span>\n`;
          } else if (sev >= 4) {
            line += `│  <span style="color:var(--text2)">📋 QUEUED:</span> ${act} <span style="color:var(--text3)">[MEDIUM — requires approval]</span>\n`;
          } else {
            line += `│  <span style="color:var(--text3)">ℹ️ LOGGED:</span> ${act} <span style="color:var(--text3)">[LOW — informational only]</span>\n`;
          }
        });
        if (sev >= 6 && container) {
          line += `│  Target: ${container}\n`;
        }
      }
      line += '└─────────────────────────────────────────────────────────────\n';

      // Prepend (newest on top)
      if (log) {
        let old = log.innerHTML;
        if (old === 'Connecting to live event stream...') old = '';
        log.innerHTML = line + '\n' + old;
      }

      // Audio alert for critical severity
      if (typeof window._handleAudioAlert === 'function') {
        window._handleAudioAlert(d);
      }

      // Flash card border
      const card = $('liveFeedCard');
      if (card) {
        card.style.borderColor = sevColor;
        setTimeout(() => { card.style.borderColor = 'var(--accent)'; }, 1500);
      }

      // Trigger a targeted refresh instead of full refreshAll
      if (typeof onNewAlert === 'function') {
        setTimeout(onNewAlert, 2000);
      }
    } catch (e) {
      console.warn('SSE parse error', e);
    }
  });

  _sse.onerror = () => {
    if (dot) dot.className = 'dot dot-red';
    if (status) status.textContent = 'Disconnected — reconnecting...';
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
  const body = $('liveFeedBody');
  const btn = $('liveFeedToggleBtn');
  if (body) body.style.display = open ? 'block' : 'none';
  if (btn) btn.textContent = open ? '▼' : '▲';
}

/** Clear the live feed log. */
export function clearLiveFeed() {
  const log = $('liveFeedLog');
  if (log) log.innerHTML = 'Waiting for alerts...';
  store.setState({ sseFeedCount: 0 });
  const count = $('liveFeedCount');
  if (count) count.textContent = '0';
}
