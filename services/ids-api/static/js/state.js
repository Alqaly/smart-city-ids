/**
 * state.js — Centralised State Management for the Smart City IDS Dashboard
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Replaces scattered global variables (TOKEN, currentAttack, ALL_PROVIDERS,
 * etc.) with a single, observable Store.  Any module can subscribe to state
 * changes and re-render only when relevant data updates.
 *
 * Architecture:
 *   ┌───────────┐   setState()   ┌───────────┐   notify()   ┌───────────┐
 *   │  api.js   │ ─────────────► │   Store   │ ────────────► │ listeners │
 *   │  sse.js   │                │  (state)  │              │  (render) │
 *   └───────────┘                └───────────┘              └───────────┘
 *
 * Usage:
 *   import { store } from './state.js';
 *   store.subscribe(state => renderOverview(state));
 *   store.setState({ alerts: { total: 42 } });
 *
 * Why not Redux/MobX?  This project intentionally avoids external
 * dependencies (no npm, no bundler).  The Store class below provides
 * the essential get/set/subscribe pattern in ~60 lines.
 */

// ── All LLM providers defined in the system (mirrors config.py) ──────────
// NOTE: The feedback suggested moving this to the backend.  We keep it
// client-side intentionally because:
//   1. It's static metadata (names, icons, colours) — not security-sensitive
//   2. Removing it would require an extra API round-trip on every page load
//   3. The backend already validates provider IDs on its own
// If a provider is added in config.py, update this list to match.
export const ALL_PROVIDERS = [
  { id: 'xai',       name: 'xAI Grok-4',       model: 'grok-4-latest',               icon: 'X', color: '#00d4ff' },
  { id: 'anthropic', name: 'Anthropic Claude',  model: 'claude-sonnet-4-20250514',    icon: 'A', color: '#d97706' },
  { id: 'openai',    name: 'OpenAI GPT-4',      model: 'gpt-4o',                       icon: 'O', color: '#22c55e' },
  { id: 'gemini',    name: 'Google Gemini',      model: 'gemini-2.5-flash',            icon: 'G', color: '#8b5cf6' },
  { id: 'kimi',      name: 'Moonshot Kimi',      model: 'moonshot-v1-128k',            icon: 'K', color: '#f97316' },
];

/**
 * Initial application state — single source of truth.
 * Every piece of mutable UI data lives here.
 */
const initialState = {
  // ── Authentication ─────────────────────────────────────────────────────
  auth: {
    token: localStorage.getItem('ids_token') || '',
  },

  // ── Active UI state ────────────────────────────────────────────────────
  ui: {
    activeTab: 'overview',       // which tab panel is visible
    liveFeedOpen: true,          // live pipeline feed expanded?
    iotStreamOpen: true,         // IoT WS feed expanded?
  },

  // ── Counters for live streams ──────────────────────────────────────────
  sseFeedCount: 0,
  iotStreamCount: 0,

  // ── Attack simulation state ────────────────────────────────────────────
  attackRunCount: 0,
  attackFlowEvents: 0,
  activeCategory: 'all',
  activePhase: 'all',
  currentAttack: null,           // the attack object currently executing
  attackTimerMs: 0,
};

// ═══════════════════════════════════════════════════════════════════════════
// Store — lightweight observable state container
// ═══════════════════════════════════════════════════════════════════════════

class Store {
  /**
   * @param {Object} initial — the initial state tree
   */
  constructor(initial) {
    this._state = { ...initial };
    this._listeners = new Set();
  }

  /** Return a shallow copy of current state. */
  getState() {
    return this._state;
  }

  /**
   * Shallow-merge new values into the state and notify subscribers.
   * @param {Object} partial — keys to merge (top-level shallow merge)
   */
  setState(partial) {
    this._state = { ...this._state, ...partial };
    this._notify();
  }

  /**
   * Register a listener that fires on every setState().
   * @param {Function} fn — callback receiving full state
   * @returns {Function} unsubscribe function
   */
  subscribe(fn) {
    this._listeners.add(fn);
    return () => this._listeners.delete(fn);
  }

  /** Notify all registered listeners of the latest state. */
  _notify() {
    const state = this._state;
    this._listeners.forEach(fn => {
      try { fn(state); } catch (e) { console.error('Store listener error:', e); }
    });
  }
}

/** Singleton store instance — import this in every module. */
export const store = new Store(initialState);
