/**
 * governance.js — Governance / HITL Interface Tab
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Human-in-the-loop (HITL) governance for security automation.  Provides:
 *   • Mode controls (Manual / Assisted / Autopilot)
 *   • Pending actions queue (approve / reject workflow)
 *   • Action history audit trail
 *
 * Purpose: keep analyst accountability explicit for stakeholder demos.
 */

import { api } from '../api.js';
import { $, esc, shortTime, sevBadge } from '../utils.js';

/**
 * Render the governance tab: mode selector, pending queue, history.
 * @param {Object} gov       — /api/governance/status
 * @param {Object} dashboard — /api/operator/dashboard (unused but available)
 * @param {Function} refreshFn — callback to trigger a full refresh after actions
 */
export function renderGovernanceTab(gov, dashboard, refreshFn) {
  if (!gov) {
    // Show helpful fallback instead of blank
    const govStatsEl = $('govStats');
    if (govStatsEl) govStatsEl.innerHTML =
      '<div class="stat-card purple"><div class="stat-label">Mode</div><div class="stat-value" style="font-size:20px">Loading...</div><div class="stat-sub">Connecting to governance API</div></div>' +
      '<div class="stat-card yellow"><div class="stat-label">Pending</div><div class="stat-value">-</div><div class="stat-sub">Actions awaiting decision</div></div>' +
      '<div class="stat-card green"><div class="stat-label">Approved</div><div class="stat-value">-</div><div class="stat-sub">Total approved actions</div></div>' +
      '<div class="stat-card red"><div class="stat-label">Rejected</div><div class="stat-value">-</div><div class="stat-sub">Actions blocked by analyst</div></div>';
    const govModeEl = $('govModeControl');
    if (govModeEl) govModeEl.innerHTML =
      '<div style="padding:16px;text-align:center;color:var(--text3)">' +
      '<div style="font-size:24px;margin-bottom:8px">&#x1F512;</div>' +
      '<div style="font-size:13px;margin-bottom:4px"><strong style="color:var(--text)">Governance Controls Loading</strong></div>' +
      '<div style="font-size:12px">Ensure you are logged in. Governance requires authentication.</div>' +
      '</div>';
    return;
  }
  const gm = gov.metrics || {};

  // ── Summary stat cards ─────────────────────────────────────────────
  const modeLabel = gov.mode === 'assisted' ? '&#x1F6E1;&#xFE0F; Assisted' : gov.mode === 'autopilot' ? '&#x26A1; Autopilot' : '&#x1F6D1; Manual';
  const modeColor = gov.mode === 'autopilot' ? 'orange' : gov.mode === 'assisted' ? 'purple' : 'blue';
  const govStatsEl2 = $('govStats');
  if (govStatsEl2) govStatsEl2.innerHTML =
    '<div class="stat-card ' + modeColor + '"><div class="stat-label">Automation Mode</div><div class="stat-value" style="font-size:20px">' + modeLabel +
    '</div><div class="stat-sub">Severity &ge; ' + (gov.assisted_threshold || 8) + ' requires analyst approval</div></div>' +
    '<div class="stat-card yellow"><div class="stat-label">Pending Review</div><div class="stat-value">' + (gov.pending_count || 0) + '</div><div class="stat-sub">Actions awaiting analyst decision</div></div>' +
    '<div class="stat-card green"><div class="stat-label">Approved</div><div class="stat-value">' + (gm.approved || 0) + '</div><div class="stat-sub">' + (gm.total_actions_requested || 0) + ' total actions requested</div></div>' +
    '<div class="stat-card red"><div class="stat-label">Rejected</div><div class="stat-value">' + (gm.rejected || 0) + '</div><div class="stat-sub">Actions blocked by analyst</div></div>';

  // Update navbar badge
  const pendingEl = $('pendingBadge');
  if (pendingEl) pendingEl.textContent = gov.pending_count || 0;

  // ── Mode control ───────────────────────────────────────────────────
  const modes = ['manual', 'assisted', 'autopilot'];
  const labels = ['&#x1F6D1; Manual', '&#x1F6E1;&#xFE0F; Assisted', '&#x26A1; Autopilot'];
  const descriptions = [
    'All automated actions are blocked. Every response requires analyst approval before execution.',
    'Low-severity actions auto-execute. Critical severity (&ge; ' + (gov.assisted_threshold || 8) + ') requires analyst approval.',
    'All actions auto-execute immediately. Use for demos only — no human review.'
  ];
  let mHtml = '<div style="font-size:13px;color:var(--text2);margin-bottom:12px"><strong style="color:var(--text)">Select Automation Mode</strong> — Controls how the IDS responds to detected threats</div>';
  mHtml += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:12px">';
  modes.forEach((m, idx) => {
    const active = gov.mode === m;
    const borderColor = m === 'manual' ? 'var(--accent)' : m === 'assisted' ? 'var(--accent2)' : 'var(--orange)';
    mHtml += '<div onclick="window._setGovMode(\'' + m + '\')" style="cursor:pointer;padding:16px;border-radius:8px;border:2px solid ' +
      (active ? borderColor : 'var(--border)') + ';background:' + (active ? 'rgba(0,212,255,.06)' : 'var(--bg)') +
      ';transition:all .2s;text-align:center">' +
      '<div style="font-size:16px;font-weight:700;margin-bottom:6px;color:' + (active ? borderColor : 'var(--text)') + '">' + labels[idx] + '</div>' +
      '<div style="font-size:11px;color:var(--text3);line-height:1.5">' + descriptions[idx] + '</div>' +
      (active ? '<div style="margin-top:8px"><span class="badge badge-info">ACTIVE</span></div>' : '') +
      '</div>';
  });
  mHtml += '</div>';
  const govModeEl2 = $('govModeControl');
  if (govModeEl2) govModeEl2.innerHTML = mHtml;

  loadPending(refreshFn);
  loadHistory();
}

/**
 * Set governance mode and refresh.
 */
export function setGovMode(mode, refreshFn) {
  api.setGovernanceMode(mode).then(() => {
    if (typeof refreshFn === 'function') refreshFn();
  });
}

// Expose to global scope for inline onclick handlers produced by innerHTML
window._setGovMode = (mode) => {
  // refreshFn will be wired up by app.js
  api.setGovernanceMode(mode).then(() => {
    if (window._refreshAll) window._refreshAll();
  });
};

/**
 * Load and render pending actions queue.
 */
function loadPending(refreshFn) {
  api.getGovernancePending().then(data => {
    const el = $('pendingActions');
    if (!data || !data.pending || !data.pending.length) {
      el.innerHTML = '<div style="padding:20px;color:var(--text3);text-align:center">No actions pending approval</div>';
      return;
    }
    let html = '<table><thead><tr><th>Action</th><th>Target</th><th>Severity</th><th>Reason</th><th>Actions</th></tr></thead><tbody>';
    data.pending.forEach(a => {
      html += '<tr><td>' + (a.action_type || a.action || '-') + '</td>' +
        '<td>' + (a.target || '-') + '</td>' +
        '<td><span class="badge ' + sevBadge(a.severity) + '">' + (a.severity || '-') + '</span></td>' +
        '<td style="max-width:200px">' + esc(((a.rationale || a.reason || '')).substring(0, 100)) + '</td>' +
        '<td><button class="btn btn-success btn-sm" onclick="window._approveAction(\'' + a.id + '\')">Approve</button> ' +
        '<button class="btn btn-danger btn-sm" onclick="window._rejectAction(\'' + a.id + '\')">Reject</button></td></tr>';
    });
    el.innerHTML = html + '</tbody></table>';
  });
}

/**
 * Load and render governance action history.
 */
function loadHistory() {
  api.getGovernanceHistory().then(data => {
    const el = $('govHistory');
    if (!el) return;
    if (!data || !data.history || !data.history.length) {
      el.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text3)">No action history</td></tr>';
      return;
    }
    let html = '';
    data.history.forEach(h => {
      html += '<tr><td>' + shortTime(h.timestamp) + '</td>' +
        '<td>' + (h.action_type || h.action || '-') + '</td>' +
        '<td>' + (h.target || '-') + '</td>' +
        '<td><span class="badge ' + (h.status === 'approved' || h.status === 'executed' ? 'badge-low' : h.status === 'rejected' ? 'badge-crit' : 'badge-med') + '">' + (h.status || '-') + '</span></td>' +
        '<td>' + (h.operator || '-') + '</td></tr>';
    });
    el.innerHTML = html;
  });
}

// ── Global action handlers (for inline onclick) ─────────────────────────

window._approveAction = (id) => {
  api.approveAction(id).then(() => {
    if (window._refreshAll) window._refreshAll();
  });
};

window._rejectAction = (id) => {
  api.rejectAction(id).then(() => {
    if (window._refreshAll) window._refreshAll();
  });
};
