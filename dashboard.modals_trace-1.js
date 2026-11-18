// dashboard.modals_trace-1.js - Multi-Agent Step-Trace Timeline Modal
// Modularized per gemini.md Rule 2 (Limit 400-500 lines)

let activeTraceItem = null;

function openTraceModal(reqId) {
  const modal = document.getElementById('trace-modal');
  if (!modal) return;

  // Search in global feed data or fetch live snapshot
  let feed = [];
  try {
    if (typeof lastLiveSnapshot !== 'undefined' && lastLiveSnapshot && Array.isArray(lastLiveSnapshot.feed)) {
      feed = lastLiveSnapshot.feed;
    }
  } catch (e) {}
  const item = feed.find(f => f.id === reqId);

  if (!item) {
    if (typeof showToast === 'function') showToast('Trace telemetry not found for this request', true);
    return;
  }

  activeTraceItem = item;
  const titleEl = document.getElementById('trace-modal-title');
  const metaEl = document.getElementById('trace-modal-meta');
  const bodyEl = document.getElementById('trace-modal-timeline');

  if (titleEl) {
    titleEl.innerHTML = `🔍 Trace: <span style="color:#d2a8ff;">${_esc(item.provider_name || 'Multi-Agent Team')}</span>`;
  }

  if (metaEl) {
    metaEl.innerHTML = `
      <span class="trace-meta-pill">⏱️ Total: <strong>${item.latency_ms || 0}ms</strong></span>
      <span class="trace-meta-pill">📊 Tokens: <strong>${item.input_tokens || 0} in ➔ ${item.output_tokens || 0} out</strong></span>
      <span class="trace-meta-pill">⚡ Speed: <strong>${item.tok_per_sec || 0} t/s</strong></span>
      <span class="trace-meta-pill" style="border-color:#58338f; color:#d2a8ff;">🏆 Winner: <strong>${_esc(item.passed_by || item.model)}</strong></span>
    `;
  }

  const steps = item.steps_detail || [];
  if (!steps.length) {
    bodyEl.innerHTML = `
      <div style="padding:20px; text-align:center; color:var(--text-muted); font-size:12px;">
        No granular step telemetry recorded for this request.<br>
        <span style="font-size:10px; color:#8b949e;">(Summary: ${_esc(item.recovery_stage || 'Standard pipeline')})</span>
      </div>
    `;
  } else {
    bodyEl.innerHTML = steps.map((s, idx) => {
      const isAgentic = (s.mode || '').toLowerCase() === 'agentic';
      const modeIcon = isAgentic ? '⚡ Agentic' : '💡 Normal';
      const modeClass = isAgentic ? 'is-agentic' : 'is-normal';
      const isLast = idx === steps.length - 1;

      return `
        <div class="trace-timeline-item">
          <div class="trace-node-line ${isLast ? 'is-last' : ''}">
            <div class="trace-node-dot ${modeClass}">${s.step}</div>
          </div>
          <div class="trace-card">
            <div class="trace-card-head">
              <div class="trace-card-role">
                <span class="trace-role-tag">${_esc(s.role || `Step ${s.step}`)}</span>
                <span class="member-mode-glow-btn ${modeClass}" style="cursor:default;" title="Engine Mode: ${modeIcon}">${isAgentic ? '⚡' : '💡'} ${s.mode || 'normal'}</span>
              </div>
              <div class="trace-card-perf">
                <span class="trace-perf-badge">${s.latency_ms || 0}ms</span>
                <span class="trace-perf-badge">${s.in_tokens || 0}→${s.out_tokens || 0} tok</span>
              </div>
            </div>
            <div class="trace-card-sub">
              <strong>${_esc(s.provider || 'Provider')}</strong> • <span style="color:#79c0ff; font-family:var(--mono);">${_esc(s.model || 'model')}</span>
            </div>
            ${s.snippet ? `
              <details class="trace-card-details">
                <summary>👁️ View Output Snippet (${s.snippet.length} chars)</summary>
                <pre class="trace-snippet-pre">${_esc(s.snippet)}</pre>
              </details>
            ` : ''}
          </div>
        </div>
      `;
    }).join('');
  }

  modal.classList.add('active');
}

function closeTraceModal() {
  const modal = document.getElementById('trace-modal');
  if (modal) modal.classList.remove('active');
  activeTraceItem = null;
}
