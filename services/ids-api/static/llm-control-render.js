/**
 * Enhanced LLM Control Center Rendering Functions
 * Addresses UX improvements, error handling, and visual hierarchy
 */

// ============================================================================
// SSE Connection Management with Error Deduplication
// ============================================================================

const sseManager = {
    connection: null,
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,
    reconnectDelay: 1000,
    lastEventTime: null,
    errorLog: new Map(), // For deduplicating error messages
    errorSilenceMode: false,
    
    connect() {
        if (this.connection?.readyState === EventSource.OPEN) return;
        
        this.updateStatus('connecting');
        
        try {
            this.connection = new EventSource(CFG.API + '/api/alerts/live');
            
            this.connection.onopen = () => {
                this.reconnectAttempts = 0;
                this.updateStatus('connected');
                this.logEvent('system', 'Live updates connected');
            };
            
            this.connection.onerror = () => {
                this.updateStatus('disconnected');
                this.attemptReconnect();
            };
            
            this.connection.addEventListener('alert', (e) => {
                this.lastEventTime = Date.now();
                this.handleAlertEvent(e);
            });
            
        } catch (e) {
            this.updateStatus('error');
            this.logEvent('error', 'Failed to connect to live updates');
        }
    },
    
    attemptReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            this.updateStatus('failed');
            this.logEvent('error', 'Live updates unavailable - using polling mode');
            return;
        }
        
        this.reconnectAttempts++;
        const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts), 30000);
        
        setTimeout(() => {
            this.logEvent('system', `Reconnecting... (attempt ${this.reconnectAttempts})`);
            this.connect();
        }, delay);
    },
    
    updateStatus(status) {
        const dot = $('sseStatusDot');
        const text = $('sseStatusText');
        const badge = $('llmConnectivityBadge');
        
        const configs = {
            connected: { dot: '#22c55e', text: 'Live updates active', badge: 'Connected', badgeColor: '#22c55e' },
            connecting: { dot: '#eab308', text: 'Connecting to live updates...', badge: 'Connecting...', badgeColor: '#eab308' },
            disconnected: { dot: '#facc15', text: 'Reconnecting...', badge: 'Reconnecting', badgeColor: '#facc15' },
            failed: { dot: '#ef4444', text: 'Live updates unavailable - dashboard refreshes every 15s', badge: 'Polling Mode', badgeColor: '#ef4444' },
            error: { dot: '#ef4444', text: 'Connection error', badge: 'Error', badgeColor: '#ef4444' }
        };
        
        const cfg = configs[status] || configs.error;
        
        if (dot) {
            dot.style.background = cfg.dot;
            dot.style.boxShadow = `0 0 6px ${cfg.dot}`;
        }
        if (text) text.textContent = cfg.text;
        if (badge) {
            badge.innerHTML = `<i class="fas fa-circle" style="font-size:8px;margin-right:4px;color:${cfg.badgeColor};"></i>${cfg.badge}`;
            badge.style.borderColor = cfg.badgeColor;
        }
    },
    
    handleAlertEvent(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'llm_route' || data.type === 'llm_provider_change') {
                this.logEvent('routing', `Switched to ${data.provider}`);
            }
        } catch (e) {
            // Ignore parse errors
        }
    },
    
    logEvent(type, message) {
        if (this.errorSilenceMode && type === 'error') return;
        
        // Deduplicate similar messages within 30 seconds
        const key = `${type}:${message}`;
        const now = Date.now();
        const lastSeen = this.errorLog.get(key);
        
        if (lastSeen && (now - lastSeen) < 30000) {
            // Skip duplicate
            return;
        }
        
        this.errorLog.set(key, now);
        
        // Cleanup old entries
        if (this.errorLog.size > 100) {
            const cutoff = now - 300000; // 5 minutes
            for (const [k, v] of this.errorLog) {
                if (v < cutoff) this.errorLog.delete(k);
            }
        }
        
        // Add to event log UI
        if (window.app && app.appendLiveLLMEvent) {
            app.appendLiveLLMEvent(`[${type}] ${message}`);
        }
    },
    
    toggleSilence() {
        this.errorSilenceMode = !this.errorSilenceMode;
        return this.errorSilenceMode;
    }
};

// ============================================================================
// Enhanced Render Functions
// ============================================================================

const llmRender = {
    
    /**
     * Main LLM Control Center renderer
     */
    llmControl(status, comparison, healthSummary) {
        const providers = status?.providers || {};
        const names = status?.provider_names || Object.keys(providers);
        const fallbackChain = status?.fallback_chain || [];
        const comparisonRows = Array.isArray(comparison?.providers) ? comparison.providers : [];
        
        // Categorize providers by health state
        const operational = [];
        const degraded = [];
        const failed = [];
        
        names.forEach(name => {
            const p = providers[name] || {};
            const probe = status?.live_probe?.[name];
            const enriched = { ...p, name, probe };
            
            if (p.status === 'not_configured') {
                failed.push(enriched);
            } else if (p.status === 'operational' || p.status === 'healthy') {
                if (probe && probe.status === 'ok') {
                    operational.push(enriched);
                } else {
                    degraded.push(enriched);
                }
            } else if (p.status === 'cooldown' || p.status === 'degraded') {
                degraded.push(enriched);
            } else {
                failed.push(enriched);
            }
        });
        
        // Update KPI cards
        this._updateKPICards(status, healthSummary, comparison, operational.length, names.length);
        
        // Render provider cards grouped by state
        this._renderProviderCards(operational, degraded, failed);
        
        // Render failover chain
        this._renderFallbackChain(fallbackChain, providers, status?.forced_provider);
        
        // Update selector options
        this._updateSelectors(names, providers, status);
        
        // Update last refresh time
        this._updateLastRefreshTime();
    },
    
    /**
     * Update KPI cards with better visual indicators
     */
    _updateKPICards(status, healthSummary, comparison, healthyCount, totalCount) {
        const opEl = $('llmCtrlOperational');
        const actEl = $('llmCtrlActive');
        const actMeta = $('llmCtrlActiveMeta');
        const callsEl = $('llmCtrlCalls');
        const tokensEl = $('llmCtrlTokens');
        const costEl = $('llmCtrlCost');
        const successEl = $('llmCtrlSuccess');
        
        // Provider count with color coding
        if (opEl) {
            opEl.textContent = `${healthyCount}/${totalCount}`;
            opEl.style.color = healthyCount === totalCount ? '#22c55e' : 
                               healthyCount >= totalCount / 2 ? '#facc15' : '#ef4444';
        }
        
        const opSub = $('llmCtrlOperationalSub');
        if (opSub) {
            const unavailable = totalCount - healthyCount;
            opSub.textContent = unavailable === 0 ? 'all systems operational' : 
                               `${unavailable} unavailable`;
            opSub.style.color = unavailable === 0 ? '#4ade80' : '#facc15';
        }
        
        // Active provider with prominence
        const activeProvider = status?.effective_provider || status?.active_provider || '—';
        if (actEl) {
            actEl.textContent = activeProvider.toUpperCase();
            actEl.style.color = '#fff';
        }
        
        if (actMeta) {
            const details = status?.active_provider_details || {};
            const p95 = Number(details?.p95_latency_s || 0) > 0 ? 
                `${Number(details.p95_latency_s).toFixed(2)}s` : 'measuring...';
            const sr = details?.success_rate != null ? 
                `${Math.round(Number(details.success_rate || 0) * 100)}% success` : 'collecting data...';
            actMeta.textContent = details?.success_rate != null ? `${p95} · ${sr}` : 'warming up...';
        }
        
        // Metrics with formatting
        const totalCalls = healthSummary?.calls ?? comparison?.summary?.calls ?? 0;
        const totalTokens = healthSummary?.tokens ?? comparison?.summary?.tokens ?? 0;
        const totalCost = healthSummary?.cost_usd ?? comparison?.summary?.cost_usd ?? 0;
        const successRate = healthSummary?.success_rate ?? comparison?.summary?.success_rate ?? 0;
        
        if (callsEl) callsEl.textContent = this._formatNumber(totalCalls);
        if (tokensEl) tokensEl.textContent = this._formatNumber(totalTokens);
        
        if (costEl) {
            costEl.textContent = `$${Number(totalCost || 0).toFixed(2)}`;
            // Color code cost (green under $5, yellow $5-20, red over $20)
            const costVal = Number(totalCost || 0);
            costEl.style.color = costVal < 5 ? '#4ade80' : costVal < 20 ? '#facc15' : '#f87171';
        }
        
        if (successEl) {
            const srPct = Math.round(Number(successRate || 0) * 100);
            successEl.textContent = srPct > 0 ? `${srPct}%` : '—';
            successEl.style.color = srPct >= 95 ? '#4ade80' : srPct >= 80 ? '#facc15' : '#f87171';
        }
    },
    
    /**
     * Render provider cards grouped by operational state
     */
    _renderProviderCards(operational, degraded, failed) {
        // Show/hide sections based on content
        const showSection = (id, items) => {
            const el = $(id);
            if (el) el.style.display = items.length > 0 ? 'block' : 'none';
        };
        
        showSection('llmProvidersOperational', operational);
        showSection('llmProvidersDegraded', degraded);
        showSection('llmProvidersFailed', failed);
        
        // Render each group
        this._renderCardGroup('llmProviderCardsOperational', operational, 'operational');
        this._renderCardGroup('llmProviderCardsDegraded', degraded, 'degraded');
        this._renderCardGroup('llmProviderCardsFailed', failed, 'failed');
    },
    
    /**
     * Render a group of provider cards
     */
    _renderCardGroup(containerId, providers, stateClass) {
        const container = $(containerId);
        if (!container) return;
        
        if (providers.length === 0) {
            container.innerHTML = '';
            return;
        }
        
        container.innerHTML = providers.map(p => this._createProviderCard(p, stateClass)).join('');
    },
    
    /**
     * Create a single provider card HTML
     */
    _createProviderCard(p, stateClass) {
        const name = p.name;
        const isConfigured = p.status !== 'not_configured';
        const isCooldown = p.status === 'cooldown';
        const cooldownS = Number(p.cooldown_remaining_seconds || 0);
        
        // Status indicator
        let statusText = p.status || 'unknown';
        let statusIcon = 'fa-circle';
        
        if (isCooldown) {
            statusText = `cooldown (${cooldownS}s)`;
            statusIcon = 'fa-clock';
        } else if (p.status === 'not_configured') {
            statusText = 'not configured';
            statusIcon = 'fa-ban';
        } else if (p.status === 'operational' || p.status === 'healthy') {
            statusText = 'healthy';
            statusIcon = 'fa-check-circle';
        } else if (p.status === 'auth_failed') {
            statusText = 'auth failed';
            statusIcon = 'fa-key';
        }
        
        // Probe info
        const probe = p.probe;
        const probeText = probe ? 
            (probe.status === 'ok' ? 
                `<span style="color:#4ade80;"><i class="fas fa-bolt mr-1"></i>${probe.latency_ms}ms</span>` : 
                `<span style="color:#f87171;">${probe.status}</span>`) :
            '<span style="color:#606080;">not probed</span>';
        
        // Credits with visual indicator
        let creditHtml = '';
        if (p.credits != null) {
            const creditNum = Number(p.credits);
            const creditColor = creditNum > 10 ? '#4ade80' : creditNum > 2 ? '#facc15' : '#f87171';
            const creditIcon = creditNum > 10 ? 'fa-wallet' : creditNum > 2 ? 'fa-exclamation-circle' : 'fa-exclamation-triangle';
            creditHtml = `<div style="font-size:12px;color:${creditColor};"><i class="fas ${creditIcon} mr-1"></i>$${creditNum.toFixed(2)} credits</div>`;
        } else if (p.status === 'not_configured') {
            creditHtml = `<div style="font-size:12px;color:#64748b;"><i class="fas fa-ban mr-1"></i>no API key</div>`;
        } else {
            creditHtml = `<div style="font-size:12px;color:#606080;"><i class="fas fa-question-circle mr-1"></i>credits unknown</div>`;
        }
        
        // Metrics row
        const calls = p.attempts || 0;
        const successes = p.successes || 0;
        const failures = p.failures || 0;
        const sr = calls > 0 ? Math.round((successes / calls) * 100) : 0;
        
        // Action buttons
        const canTest = isConfigured;
        const btnStyle = 'padding:5px 10px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);color:#fff;border-radius:6px;font-size:11px;cursor:pointer;';
        const btnDisabled = 'padding:5px 10px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);color:#606080;border-radius:6px;font-size:11px;cursor:not-allowed;';
        
        return `
            <div class="provider-card ${stateClass}">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span class="provider-status-dot ${stateClass}"></span>
                        <strong style="font-size:14px;text-transform:uppercase;">${esc(name)}</strong>
                    </div>
                    <span style="font-size:11px;color:#606080;background:rgba(0,0,0,0.3);padding:2px 8px;border-radius:4px;">${esc(p.model || 'unknown model')}</span>
                </div>
                
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px;">
                    <div>
                        <div style="font-size:10px;color:#606080;text-transform:uppercase;">Status</div>
                        <div style="font-size:12px;"><i class="fas ${statusIcon} mr-1" style="color:var(--accent-cyan);"></i>${esc(statusText)}</div>
                    </div>
                    <div>
                        <div style="font-size:10px;color:#606080;text-transform:uppercase;">Response</div>
                        <div style="font-size:12px;">${probeText}</div>
                    </div>
                    <div>
                        <div style="font-size:10px;color:#606080;text-transform:uppercase;">Success Rate</div>
                        <div style="font-size:12px;color:${sr >= 90 ? '#4ade80' : sr >= 70 ? '#facc15' : '#f87171'};">${sr}% (${successes}/${calls})</div>
                    </div>
                    <div>
                        <div style="font-size:10px;color:#606080;text-transform:uppercase;">Credits</div>
                        ${creditHtml}
                    </div>
                </div>
                
                <div style="display:flex;gap:6px;">
                    <button onclick="app.testProviderKey('${esc(name)}')" ${canTest ? '' : 'disabled'} style="${canTest ? btnStyle : btnDisabled}">
                        <i class="fas fa-key mr-1"></i>Test Key
                    </button>
                    <button onclick="app.probeProvider('${esc(name)}')" style="${btnStyle}">
                        <i class="fas fa-heartbeat mr-1"></i>Probe
                    </button>
                    <button onclick="app.forceProvider('${esc(name)}')" ${canTest ? '' : 'disabled'} style="${canTest ? btnStyle : btnDisabled}" title="Force traffic to this provider">
                        <i class="fas fa-bolt mr-1"></i>Use
                    </button>
                </div>
            </div>
        `;
    },
    
    /**
     * Render failover chain as visual flow
     */
    _renderFallbackChain(chain, providers, forcedProvider) {
        const el = $('llmFallbackChain');
        if (!el) return;
        
        if (chain.length === 0) {
            el.innerHTML = '<span style="color:#606080;font-size:12px;">No failover chain configured</span>';
            return;
        }
        
        el.innerHTML = chain.map((name, i) => {
            const p = providers[name] || {};
            const status = (p.status || 'unknown').toLowerCase();
            const isActive = name === forcedProvider;
            
            let stateClass = 'healthy';
            if (status === 'cooldown' || status === 'degraded') stateClass = 'degraded';
            else if (status === 'not_configured' || status === 'error' || status === 'auth_failed') stateClass = 'failed';
            
            return `
                <span class="chain-pill ${stateClass} ${isActive ? 'active' : ''}" title="${status}">
                    ${isActive ? '<i class="fas fa-star" style="font-size:10px;"></i>' : ''}
                    ${esc(name)}
                    ${i === 0 ? '<i class="fas fa-arrow-right" style="font-size:10px;opacity:0.5;"></i>' : ''}
                </span>
                ${i < chain.length - 1 ? '<i class="fas fa-chevron-right" style="color:#606080;font-size:12px;"></i>' : ''}
            `;
        }).join('');
    },
    
    /**
     * Update dropdown selectors with provider options
     */
    _updateSelectors(names, providers, status) {
        const forceSel = $('forceProviderSelect');
        const testSel = $('llmTestProvider');
        const routingA = $('llmRoutingA');
        const routingB = $('llmRoutingB');
        
        const selectable = names.filter(n => {
            const p = providers[n] || {};
            return p.configured !== false && p.status !== 'not_configured';
        });
        
        const options = selectable.map(n => `<option value="${esc(n)}">${esc(n.toUpperCase())}</option>`).join('');
        
        if (forceSel) {
            forceSel.innerHTML = '<option value="">Automatic (failover)</option>' + options;
            forceSel.value = status?.forced_provider || '';
        }
        
        if (testSel) {
            testSel.innerHTML = '<option value="">Auto-select</option>' + options;
        }
        
        if (routingA) routingA.innerHTML = options;
        if (routingB) routingB.innerHTML = options;
    },
    
    /**
     * Update last refresh timestamp
     */
    _updateLastRefreshTime() {
        const timeEl = $('lastUpdateTime');
        const ageEl = $('dataAge');
        
        if (timeEl) {
            timeEl.textContent = new Date().toLocaleTimeString('en-GB');
        }
        
        if (ageEl) {
            ageEl.textContent = 'just now';
            // Update age text every 10 seconds
            if (this._ageInterval) clearInterval(this._ageInterval);
            let seconds = 0;
            this._ageInterval = setInterval(() => {
                seconds += 10;
                if (ageEl) {
                    ageEl.textContent = seconds < 60 ? `${seconds}s ago` : 
                                       seconds < 3600 ? `${Math.floor(seconds/60)}m ago` : 
                                       `${Math.floor(seconds/3600)}h ago`;
                }
            }, 10000);
        }
    },
    
    /**
     * Format large numbers with k/m suffixes
     */
    _formatNumber(n) {
        if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
        if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
        return String(n);
    },
    
    /**
     * Render provider comparison table
     */
    llmUsageCompare(comparison) {
        const el = $('llmUsageCompare');
        if (!el) return;
        
        const rows = comparison?.providers || [];
        
        if (rows.length === 0) {
            el.innerHTML = `
                <div style="text-align:center;padding:30px;color:#606080;">
                    <i class="fas fa-chart-bar" style="font-size:32px;margin-bottom:12px;opacity:0.3;"></i>
                    <div style="font-size:13px;">No provider usage data yet</div>
                    <div style="font-size:11px;margin-top:6px;">Metrics will appear after LLM analysis begins</div>
                </div>
            `;
            return;
        }
        
        el.innerHTML = `
            <div style="max-height:300px;overflow-y:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:12px;">
                    <thead>
                        <tr style="font-size:10px;color:#606080;text-transform:uppercase;background:rgba(0,0,0,0.25);position:sticky;top:0;">
                            <th style="padding:10px;text-align:left;">Provider</th>
                            <th style="padding:10px;text-align:right;">Calls</th>
                            <th style="padding:10px;text-align:right;">Tokens</th>
                            <th style="padding:10px;text-align:right;">Cost</th>
                            <th style="padding:10px;text-align:center;">Success</th>
                            <th style="padding:10px;text-align:right;">Latency</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map(r => {
                            const sr = Math.round((Number(r.success_rate) || 0) * 100);
                            const p95 = Number(r.p95_latency_s) > 0 ? `${Number(r.p95_latency_s).toFixed(2)}s` : '—';
                            const tokens = Number(r.tokens_total || 0);
                            const tokensFmt = tokens >= 1000 ? `${(tokens/1000).toFixed(1)}k` : String(tokens);
                            const cost = Number(r.total_estimated_cost_usd || 0);
                            
                            return `
                                <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                                    <td style="padding:10px;font-weight:600;">${esc(r.provider?.toUpperCase() || '—')}</td>
                                    <td style="padding:10px;text-align:right;color:#c0c0d0;">${Number(r.attempts || 0)}</td>
                                    <td style="padding:10px;text-align:right;color:#c0c0d0;">${tokensFmt}</td>
                                    <td style="padding:10px;text-align:right;color:#c0c0d0;">$${cost.toFixed(3)}</td>
                                    <td style="padding:10px;text-align:center;">
                                        <span style="padding:2px 8px;border-radius:4px;font-size:11px;background:${sr >= 95 ? 'rgba(34,197,94,0.15)' : sr >= 80 ? 'rgba(250,204,21,0.15)' : 'rgba(239,68,68,0.15)'};color:${sr >= 95 ? '#4ade80' : sr >= 80 ? '#facc15' : '#f87171'};">${sr}%</span>
                                    </td>
                                    <td style="padding:10px;text-align:right;color:#c0c0d0;font-family:'JetBrains Mono',monospace;">${p95}</td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        `;
    },
    
    /**
     * Render routing strategy section
     */
    llmRouting(routing, risk) {
        const modeSel = $('llmRoutingMode');
        const costIn = $('llmRoutingCost');
        const aIn = $('llmRoutingA');
        const bIn = $('llmRoutingB');
        const splitIn = $('llmRoutingSplit');
        const riskEl = $('llmPredictiveRisk');
        
        if (modeSel && routing?.mode) modeSel.value = routing.mode;
        if (costIn && routing?.cost_ceiling_usd != null) costIn.value = String(routing.cost_ceiling_usd);
        if (aIn) aIn.value = routing?.ab_test?.provider_a || '';
        if (bIn) bIn.value = routing?.ab_test?.provider_b || '';
        if (splitIn && routing?.ab_test?.split_percent_a != null) splitIn.value = String(routing.ab_test.split_percent_a);
        
        // Update help text based on mode
        this._updateRoutingHelp(routing?.mode);
        
        // Show/hide conditional inputs
        this._toggleRoutingInputs(routing?.mode);
        
        // Render risk forecast
        if (riskEl && risk) {
            if (risk.risk_score != null) {
                const score = Math.round(risk.risk_score);
                const color = score >= 70 ? '#ef4444' : score >= 40 ? '#facc15' : '#22c55e';
                const level = score >= 70 ? 'HIGH' : score >= 40 ? 'ELEVATED' : 'NORMAL';
                
                riskEl.innerHTML = `
                    <div style="display:flex;align-items:center;gap:16px;">
                        <div style="text-align:center;">
                            <div style="font-size:32px;font-weight:700;color:${color};">${score}</div>
                            <div style="font-size:10px;color:#606080;text-transform:uppercase;">Risk Score</div>
                        </div>
                        <div style="flex:1;">
                            <div style="font-size:14px;font-weight:600;color:${color};margin-bottom:4px;">${level} RISK</div>
                            <div style="font-size:12px;color:#a0a0b0;">${risk.recommendation || 'Monitoring alert patterns...'}</div>
                            <div style="margin-top:8px;height:4px;background:rgba(255,255,255,0.1);border-radius:2px;overflow:hidden;">
                                <div style="width:${score}%;height:100%;background:${color};transition:width 0.3s;"></div>
                            </div>
                        </div>
                    </div>
                    <div style="margin-top:12px;display:flex;gap:16px;font-size:11px;color:#606080;">
                        <span><i class="fas fa-chart-line mr-1"></i>Trend: ${risk.trend || 'stable'}</span>
                        <span><i class="fas fa-exclamation-circle mr-1"></i>Critical rate: ${Math.round((risk.critical_rate || 0) * 100)}%</span>
                    </div>
                `;
            } else {
                riskEl.innerHTML = `
                    <div style="text-align:center;padding:20px;color:#606080;">
                        <i class="fas fa-chart-area" style="font-size:24px;margin-bottom:8px;opacity:0.5;"></i>
                        <div style="font-size:12px;">Collecting alert data...</div>
                        <div style="font-size:11px;margin-top:4px;">Risk forecast appears after processing 20+ alerts</div>
                    </div>
                `;
            }
        }
    },
    
    _updateRoutingHelp(mode) {
        const helpEl = $('routingModeHelp');
        if (!helpEl) return;
        
        const helps = {
            priority: 'Use failover chain order. If a provider fails, automatically switch to the next healthy provider.',
            cost_optimized: 'Always route to the cheapest available provider within your cost ceiling.',
            severity_adaptive: 'Use premium providers for critical alerts (severity 8+), cost-optimized for others.',
            ab_test: 'Split traffic between two providers for comparison testing.'
        };
        
        helpEl.textContent = helps[mode] || helps.priority;
    },
    
    _toggleRoutingInputs(mode) {
        const costGroup = $('costCeilingGroup');
        const abGroup = $('abTestGroup');
        
        if (costGroup) costGroup.style.display = mode === 'cost_optimized' ? 'block' : 'none';
        if (abGroup) abGroup.style.display = mode === 'ab_test' ? 'block' : 'none';
    }
};

// ============================================================================
// App Integration Helpers
// ============================================================================

// Extend app object with enhanced functions
if (typeof window.app !== 'undefined') {
    // Store reference to original render functions
    const originalRender = window.render || {};
    
    // Override with enhanced versions
    window.render = {
        ...originalRender,
        llmControl: llmRender.llmControl.bind(llmRender),
        llmUsageCompare: llmRender.llmUsageCompare.bind(llmRender),
        llmRouting: llmRender.llmRouting.bind(llmRender)
    };
    
    // Add new app methods
    app.toggleErrorSilence = function() {
        const enabled = sseManager.toggleSilence();
        const btn = $('silenceErrorsBtn');
        if (btn) {
            btn.innerHTML = enabled ? 
                '<i class="fas fa-bell mr-1"></i>Show All' : 
                '<i class="fas fa-bell-slash mr-1"></i>Silence Noise';
            btn.style.color = enabled ? '#facc15' : '#a0a0b0';
        }
        return enabled;
    };
    
    app.onRoutingModeChange = function() {
        const mode = $('llmRoutingMode')?.value;
        llmRender._updateRoutingHelp(mode);
        llmRender._toggleRoutingInputs(mode);
    };
    
    app.forceProvider = async function(provider) {
        if (!provider) return;
        const select = $('forceProviderSelect');
        if (select) select.value = provider;
        await app.applyForcedProvider();
    };
    
    app.clearLLMEvents = function() {
        const log = $('llmEventLog');
        if (log) {
            log.innerHTML = '<span style="color:#606080;">// Events cleared</span>';
        }
    };
}

// Initialize SSE on page load
document.addEventListener('DOMContentLoaded', () => {
    sseManager.connect();
});
