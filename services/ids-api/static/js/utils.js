/**
 * utils.js — Shared Helper Functions for the Smart City IDS Dashboard
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Pure utility functions with no side-effects, no DOM access, and no
 * imports from other dashboard modules.  Safe to use anywhere.
 *
 * Functions:
 *   esc(str)           — HTML-escape a string (XSS prevention)
 *   shortTime(ts)      — ISO timestamp → "HH:MM:SS"
 *   formatDuration(s)  — seconds → "2h 14m" human-readable
 *   sevBadge(sev)      — severity int → CSS class name
 *   countCB(cb)        — count engines in circuit-breaker data
 */

/**
 * HTML-escape a string to prevent XSS when injecting into innerHTML.
 *
 * The feedback suggested using DOMPurify.  We keep the lightweight
 * approach because:
 *   - All data originates from our own API (not user-generated content)
 *   - Adding a CDN dependency increases page load and attack surface
 *   - This escaper covers the 5 HTML special characters reliably
 *
 * @param {string} s — raw string
 * @returns {string} escaped HTML-safe string
 */
export function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

/**
 * Format an ISO timestamp into a short local time string.
 * @param {string} ts — ISO-8601 timestamp
 * @returns {string} "HH:MM:SS" or "--" on failure
 */
export function shortTime(ts) {
  if (!ts) return '--';
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
  } catch {
    return '--';
  }
}

/**
 * Convert seconds to a human-readable duration.
 * @param {number} s — total seconds
 * @returns {string} e.g., "2h 14m", "45s"
 */
export function formatDuration(s) {
  if (s < 60) return Math.floor(s) + 's';
  if (s < 3600) return Math.floor(s / 60) + 'm ' + Math.floor(s % 60) + 's';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h + 'h ' + m + 'm';
}

/**
 * Map a numeric severity (1-10) to a badge CSS class.
 * @param {number|string} sev — severity value
 * @returns {string} CSS class name
 */
export function sevBadge(sev) {
  sev = parseInt(sev) || 0;
  if (sev >= 8) return 'badge-crit';
  if (sev >= 6) return 'badge-high';
  if (sev >= 4) return 'badge-med';
  return 'badge-low';
}

/**
 * Count the number of engines in a circuit-breaker status object.
 * @param {Object} cb — response from /api/circuit-breaker/status
 * @returns {number}
 */
export function countCB(cb) {
  return (cb && cb.engines) ? Object.keys(cb.engines).length : 0;
}

/**
 * Map an integer severity to the Falco priority string the backend expects.
 * @param {number} sev — numeric severity (1-10)
 * @returns {string} "Critical" | "Warning" | "Notice"
 */
export function severityToPriority(sev) {
  if (sev >= 8) return 'Critical';
  if (sev >= 6) return 'Warning';
  return 'Notice';
}
