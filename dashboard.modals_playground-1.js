// dashboard.modals_playground-1.js - In-Dashboard Multi-Agent Dry Run Playground UI
// Modularized per gemini.md Rule 2 (Limit 400-500 lines)

let activePlaygroundTeamId = null;

function openPlaygroundModal(teamId) {
  const modal = document.getElementById('playground-modal');
  if (!modal) return;

  const team = currentConfig?.multi_agent_teams?.[teamId];
  if (!team) {
    if (typeof showToast === 'function') showToast('Team not found', true);
    return;
  }

  activePlaygroundTeamId = teamId;
  const titleEl = document.getElementById('playground-modal-title');
  const teamInfoEl = document.getElementById('playground-team-info');
  const promptInput = document.getElementById('playground-prompt-input');
  const resultsWrap = document.getElementById('playground-results-wrap');
  const runBtn = document.getElementById('playground-run-btn');

  if (titleEl) {
    titleEl.innerHTML = `⚡ Run Playground: <span style="color:#d2a8ff;">${_esc(team.name || teamId)}</span>`;
  }

  if (teamInfoEl) {
    const memHtml = (team.members || []).map((m, idx) => {
      const pObj = currentConfig.providers?.[m.provider] || {};
      const pName = pObj.name || m.provider;
      const mName = (m.model || '').split('/').pop();
      const mMode = m.mode || (idx === 0 ? 'normal' : 'agentic');
      const modeIcon = mMode === 'agentic' ? '⚡' : '💡';
      return `<span class="chip" style="font-size:10px;"><strong style="color:#d2a8ff;">${_esc(m.role || `step_${idx+1}`)}:</strong> ${pName} (${mName}) ${modeIcon}</span>`;
    }).join(' ');

    teamInfoEl.innerHTML = `
      <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;">Workflow: <strong style="color:#79c0ff;">${_esc(team.workflow || 'role_pipeline')}</strong> (${(team.members || []).length} members)</div>
      <div style="display:flex; flex-wrap:wrap; gap:4px;">${memHtml}</div>
    `;
  }

  if (promptInput) {
    if (!promptInput.value) {
      promptInput.value = 'Write a concise Python function to calculate the nth Fibonacci number with memoization.';
    }
  }

  if (resultsWrap) {
    resultsWrap.innerHTML = '<div style="padding:15px; text-align:center; color:var(--text-muted); font-size:11px;">Enter a test prompt above and click <strong>▶️ Execute Orchestra</strong> to run this team in real-time.</div>';
  }

  if (runBtn) {
    runBtn.disabled = false;
    runBtn.innerHTML = '▶️ Execute Orchestra';
  }

  modal.classList.add('active');
}

function setPlaygroundPrompt(text) {
  const input = document.getElementById('playground-prompt-input');
  if (input) input.value = text;
}

function closePlaygroundModal() {
  const modal = document.getElementById('playground-modal');
  if (modal) modal.classList.remove('active');
  activePlaygroundTeamId = null;
}

async function runPlaygroundPrompt() {
  if (!activePlaygroundTeamId) return;
  const promptInput = document.getElementById('playground-prompt-input');
  const resultsWrap = document.getElementById('playground-results-wrap');
  const runBtn = document.getElementById('playground-run-btn');

  const text = (promptInput?.value || '').trim();
  if (!text) {
    if (typeof showToast === 'function') showToast('Please enter a test prompt', true);
    return;
  }

  if (runBtn) {
    runBtn.disabled = true;
    runBtn.innerHTML = '⏳ Executing Orchestra...';
  }

  if (resultsWrap) {
    resultsWrap.innerHTML = `
      <div style="padding:20px; text-align:center; color:#79c0ff; font-size:12px;">
        <div style="display:inline-block; animation:spin 1s linear infinite; margin-bottom:8px; font-size:16px;">⚡</div>
        <div>Multi-Agent Orchestra is thinking across providers...</div>
      </div>
    `;
  }

  try {
    const res = await fetch('/api/ui/team-dry-run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ team_id: activePlaygroundTeamId, prompt: text })
    });
    const data = await res.json();

    if (!res.ok) {
      if (resultsWrap) {
        resultsWrap.innerHTML = `
          <div style="padding:12px; background:rgba(248, 81, 73, 0.15); border:1px solid #f85149; border-radius:6px; color:#ff7b72; font-size:12px;">
            <strong>❌ Execution Failed (Step ${data.failed_step || '?'}: ${data.failed_role || 'Agent'}):</strong><br>
            ${_esc(data.message || 'Unknown error')}
          </div>
        `;
      }
      return;
    }

    // Render Steps Results
    const stepsHtml = (data.steps || []).map(s => {
      const isAgentic = (s.mode || '').toLowerCase() === 'agentic';
      return `
        <div class="trace-card" style="margin-bottom:10px;">
          <div class="trace-card-head">
            <div class="trace-card-role">
              <span class="trace-role-tag">${_esc(s.role)}</span>
              <span class="member-mode-glow-btn ${isAgentic ? 'is-agentic' : 'is-normal'}" style="cursor:default;">${isAgentic ? '⚡' : '💡'} ${s.mode}</span>
            </div>
            <div class="trace-card-perf">
              <span class="trace-perf-badge">${s.latency_ms}ms</span>
              <span class="trace-perf-badge">${s.input_tokens}→${s.output_tokens} tok</span>
            </div>
          </div>
          <div class="trace-card-sub">
            ${_esc(s.provider)} • <span style="color:#79c0ff; font-family:var(--mono);">${_esc(s.model)}</span>
          </div>
          <pre class="trace-snippet-pre" style="max-height:160px;">${_esc(s.output_text)}</pre>
        </div>
      `;
    }).join('');

    if (resultsWrap) {
      resultsWrap.innerHTML = `
        <div class="trace-modal-meta-row" style="margin-bottom:10px;">
          <span class="trace-meta-pill">⏱️ Total: <strong>${data.total_latency_ms}ms</strong></span>
          <span class="trace-meta-pill">📊 Tokens: <strong>${data.total_input_tokens} in ➔ ${data.total_output_tokens} out</strong></span>
          <span class="trace-meta-pill">⚡ Speed: <strong>${data.tok_per_sec} t/s</strong></span>
        </div>
        <div style="font-size:11px; font-weight:600; color:#d2a8ff; margin-bottom:6px;">Step-by-Step Outputs:</div>
        ${stepsHtml}
      `;
    }

    if (typeof showToast === 'function') {
      showToast(`Orchestra complete in ${data.total_latency_ms}ms (${data.total_output_tokens} tok)`);
    }

  } catch (err) {
    if (resultsWrap) {
      resultsWrap.innerHTML = `
        <div style="padding:12px; background:rgba(248, 81, 73, 0.15); border:1px solid #f85149; border-radius:6px; color:#ff7b72; font-size:12px;">
          <strong>Network Error:</strong> ${err.message}
        </div>
      `;
    }
  } finally {
    if (runBtn) {
      runBtn.disabled = false;
      runBtn.innerHTML = '▶️ Execute Orchestra';
    }
  }
}
