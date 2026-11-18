let activeModalProvider = null;
let activeDiscoveredModels = [];
let activeFilteredModels = [];
let onlyWorkingModelsFilter = false;
let modalTestRunId = 0;
let logsRefreshTimer = null;
const modelPingCache = {}; // { [providerId]: { [modelId]: { state: 'ok'|'err'|'pending', short, status } } }

function _getCachedModelStatus(pId, m) {
  return modelPingCache[pId]?.[m] || null;
}

function _setCachedModelStatus(pId, m, info) {
  if (!modelPingCache[pId]) modelPingCache[pId] = {};
  modelPingCache[pId][m] = info;
}

async function testModels(pId) {
  const p = currentConfig?.providers?.[pId];
  if (!p) return;
  const btn = document.getElementById(`ping-btn-${pId}`);
  const summaryBox = document.getElementById(`ping-${pId}`);
  const models = p.models || [];
  if (!models.length) return;

  if (btn) btn.innerText = '⏳...';
  models.forEach(m => {
    const el = document.getElementById(`chip-status-${pId}-${m}`);
    if (el) { el.innerHTML = '⏳'; el.title = 'Pinging...'; }
  });

  let completed = 0, okCount = 0;
  const updateSummary = () => {
    if (summaryBox) summaryBox.innerText = `${okCount}/${models.length} active (${completed}/${models.length} checked)`;
  };
  updateSummary();

  const pingPromises = models.map(m => {
    return fetch('/api/ui/test-models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: pId, model: m, discover_only: false })
    }).then(res => res.json()).then(data => {
      completed++;
      const resObj = (data.models || [])[0];
      const el = document.getElementById(`chip-status-${pId}-${m}`);
      if (resObj && resObj.active) {
        okCount++;
        _setCachedModelStatus(pId, m, { state: 'ok', short: resObj.short || '🟢 200', status: resObj.status || '🟢 200 OK' });
        if (el) { el.innerHTML = '🟢'; el.title = resObj.status; }
      } else {
        _setCachedModelStatus(pId, m, { state: 'err', short: resObj?.short || '🔴 Fail', status: resObj?.status || 'Failed' });
        if (el) { el.innerHTML = '🔴'; el.title = resObj?.status || 'Failed'; }
      }
      updateSummary();
    }).catch(err => {
      completed++;
      _setCachedModelStatus(pId, m, { state: 'err', short: '🔴 Err', status: 'Network error / Timeout' });
      const el = document.getElementById(`chip-status-${pId}-${m}`);
      if (el) { el.innerHTML = '🔴'; el.title = 'Network error / Timeout'; }
      updateSummary();
    });
  });

  try {
    await Promise.all(pingPromises);
    if (summaryBox) summaryBox.innerText = `${okCount}/${models.length} active (200 OK)`;
    showToast(`${p.name || pId} ping complete: ${okCount}/${models.length} active`);
  } finally {
    if (btn) btn.innerText = 'Ping';
  }
}

async function testKeys(pId) {
  const p = currentConfig?.providers?.[pId];
  if (!p) return;
  const keys = p.keys || [];
  if (!keys.length) {
    showToast('No API keys to test', true);
    return;
  }

  const btn = document.getElementById(`key-ping-btn-${pId}`);
  const summaryBox = document.getElementById(`key-ping-${pId}`);

  if (btn) {
    btn.innerText = '⏳...';
    btn.disabled = true;
  }
  keys.forEach((_, idx) => {
    const el = document.getElementById(`key-status-${pId}-${idx}`);
    if (el) {
      el.className = 'key-status is-pending';
      el.innerText = '⏳ Testing...';
      el.title = 'Testing API key (up to 60s)...';
    }
  });

  let completed = 0, okCount = 0;
  const updateSummary = () => {
    if (summaryBox) summaryBox.innerText = `${okCount}/${keys.length} active (${completed}/${keys.length} checked)`;
  };
  updateSummary();

  const keyPromises = keys.map((_, idx) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 62000);
    return fetch('/api/ui/test-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: pId, key_index: idx }),
      signal: controller.signal
    }).then(res => res.json()).then(data => {
      clearTimeout(timer);
      completed++;
      const el = document.getElementById(`key-status-${pId}-${idx}`);
      if (data && data.active) {
        okCount++;
        if (el) {
          el.className = 'key-status is-ok';
          el.innerText = data.label || '🟢 200 OK';
          el.title = data.model ? `Model: ${data.model}` : 'Active';
        }
      } else {
        if (el) {
          el.className = 'key-status is-err';
          el.innerText = data?.label || '🔴 Failed';
          el.title = data?.detail || data?.label || 'Failed';
        }
      }
      updateSummary();
    }).catch(() => {
      clearTimeout(timer);
      completed++;
      const el = document.getElementById(`key-status-${pId}-${idx}`);
      if (el) {
        el.className = 'key-status is-err';
        el.innerText = '🔴 Timeout / Error';
        el.title = 'Network error or 1 min timeout';
      }
      updateSummary();
    });
  });

  try {
    await Promise.all(keyPromises);
    if (summaryBox) summaryBox.innerText = `${okCount}/${keys.length} keys active`;
    showToast(`${p.name || pId} keys: ${okCount}/${keys.length} active`);
  } finally {
    if (btn) {
      btn.innerText = 'Test';
      btn.disabled = false;
    }
  }
}

function getFallbackPresets(pId) {
  const p = currentConfig?.providers?.[pId];
  const type = p?.type || '';
  if (type === 'openai') return ['openai/gpt-oss-120b', 'gpt-4o', 'gpt-4o-mini', 'o3-mini'];
  return ['gpt-5.6-sol', 'claude-3-5-sonnet-20241022', 'gemini-4-carbon', 'deepseek-chat', 'kimi-k3-1-pro'];
}

async function openModelsSelector(pId) {
  activeModalProvider = pId;
  onlyWorkingModelsFilter = false;
  modalTestRunId++;
  const modal = document.getElementById('models-modal');
  const title = document.getElementById('models-modal-title');
  const customInput = document.getElementById('custom-model-input');
  const filterInput = document.getElementById('model-filter-input');
  const container = document.getElementById('search-list-container');
  const summaryEl = document.getElementById('modal-models-summary');
  const testAllBtn = document.getElementById('modal-test-all-btn');
  const onlyBtn = document.getElementById('modal-only-working-btn');
  if (title) title.innerText = `MODELS: ${currentConfig.providers[pId]?.name || pId}`;
  if (customInput) customInput.value = '';
  if (filterInput) filterInput.value = '';
  if (summaryEl) summaryEl.innerText = '';
  if (testAllBtn) { testAllBtn.innerText = 'Test All'; testAllBtn.disabled = false; }
  if (onlyBtn) onlyBtn.classList.remove('is-filter-active');
  if (container) container.innerHTML = '<div style="padding:10px; color:var(--text-muted); text-align:center;">Discovering models...</div>';
  if (modal) modal.classList.add('active');

  const existing = currentConfig.providers[pId]?.models || [];
  const presets = getFallbackPresets(pId);

  try {
    const res = await fetch('/api/ui/test-models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: pId, discover_only: true })
    });
    const data = await res.json();
    const discovered = data.all_discovered || [];
    activeDiscoveredModels = Array.from(new Set([...existing, ...discovered, ...presets]));
  } catch (e) {
    activeDiscoveredModels = Array.from(new Set([...existing, ...presets]));
  }

  renderDiscoveredList(activeDiscoveredModels);

  // Auto-test discovered models with current server settings (all if <= 20, else top 12)
  const toAutoTest = activeDiscoveredModels.length <= 20
    ? activeDiscoveredModels
    : activeDiscoveredModels.slice(0, 12);
  if (toAutoTest.length > 0 && activeModalProvider === pId) {
    runModalModelsTest(pId, toAutoTest, false);
  }
}

function closeModelsModal() {
  modalTestRunId++;
  const modal = document.getElementById('models-modal');
  if (modal) modal.classList.remove('active');
}

function toggleOnlyWorkingFilter() {
  onlyWorkingModelsFilter = !onlyWorkingModelsFilter;
  const btn = document.getElementById('modal-only-working-btn');
  if (btn) btn.classList.toggle('is-filter-active', onlyWorkingModelsFilter);
  filterDiscoveredList();
}

function filterDiscoveredList() {
  const q = (document.getElementById('model-filter-input')?.value || '').toLowerCase().trim();
  let filtered = activeDiscoveredModels.filter(m => m.toLowerCase().includes(q));
  if (onlyWorkingModelsFilter && activeModalProvider) {
    filtered = filtered.filter(m => _getCachedModelStatus(activeModalProvider, m)?.state === 'ok');
  }
  renderDiscoveredList(filtered);
}

function _applyModalBadge(badgeEl, info) {
  if (!badgeEl) return;
  if (!info) {
    badgeEl.className = 'modal-model-status';
    badgeEl.innerText = 'Test';
    badgeEl.title = 'Click to test this model with your server settings';
    return;
  }
  if (info.state === 'pending') {
    badgeEl.className = 'modal-model-status is-pending';
    badgeEl.innerText = '⏳...';
    badgeEl.title = 'Testing model (up to 60s)...';
  } else if (info.state === 'ok') {
    badgeEl.className = 'modal-model-status is-ok';
    badgeEl.innerText = info.short || '🟢 200';
    badgeEl.title = `${info.status || '🟢 200 OK'} — click to re-test`;
  } else {
    badgeEl.className = 'modal-model-status is-err';
    badgeEl.innerText = info.short || '🔴 Fail';
    badgeEl.title = `${info.status || 'Failed'} — click to re-test`;
  }
}

function _updateModalRowBadge(pId, modelName) {
  if (activeModalProvider !== pId) return;
  const c = document.getElementById('search-list-container');
  if (!c) return;
  const rows = c.querySelectorAll('.search-row');
  const info = _getCachedModelStatus(pId, modelName);
  rows.forEach(r => {
    if (r.dataset.model === modelName) {
      _applyModalBadge(r.querySelector('.modal-model-status'), info);
    }
  });
}

function _pingSingleModalModel(pId, modelName) {
  _setCachedModelStatus(pId, modelName, { state: 'pending', short: '⏳...', status: 'Testing...' });
  _updateModalRowBadge(pId, modelName);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 62000);
  return fetch('/api/ui/test-models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: pId, model: modelName, discover_only: false }),
    signal: controller.signal
  }).then(res => res.json()).then(data => {
    clearTimeout(timer);
    const resObj = (data.models || [])[0];
    const ok = !!(resObj && resObj.active);
    const info = ok
      ? { state: 'ok', short: resObj.short || '🟢 200', status: resObj.status || '🟢 200 OK' }
      : { state: 'err', short: resObj?.short || '🔴 Fail', status: resObj?.status || '🔴 Failed' };
    _setCachedModelStatus(pId, modelName, info);
    if (onlyWorkingModelsFilter && activeModalProvider === pId) {
      filterDiscoveredList();
    } else {
      _updateModalRowBadge(pId, modelName);
    }
    const cardChip = document.getElementById(`chip-status-${pId}-${modelName}`);
    if (cardChip) {
      cardChip.innerHTML = ok ? '🟢' : '🔴';
      cardChip.title = info.status;
    }
    return ok;
  }).catch(() => {
    clearTimeout(timer);
    const info = { state: 'err', short: '🔴 Timeout', status: '🔴 Network error / Timeout' };
    _setCachedModelStatus(pId, modelName, info);
    if (onlyWorkingModelsFilter && activeModalProvider === pId) {
      filterDiscoveredList();
    } else {
      _updateModalRowBadge(pId, modelName);
    }
    return false;
  });
}

async function testSingleModalModel(pId, modelName) {
  await _pingSingleModalModel(pId, modelName);
  updateModalSummaryDisplay(pId);
}

function updateModalSummaryDisplay(pId) {
  const summaryEl = document.getElementById('modal-models-summary');
  if (!summaryEl || activeModalProvider !== pId) return;
  const list = activeFilteredModels.length ? activeFilteredModels : activeDiscoveredModels;
  let ok = 0, checked = 0;
  list.forEach(m => {
    const st = _getCachedModelStatus(pId, m);
    if (st && (st.state === 'ok' || st.state === 'err')) {
      checked++;
      if (st.state === 'ok') ok++;
    }
  });
  summaryEl.innerText = checked > 0
    ? `${ok}/${checked} working (${checked}/${list.length} checked)`
    : '';
}

async function runModalModelsTest(pId, modelsList, forceRetest=true) {
  if (!pId || !modelsList || !modelsList.length) return;
  const runId = ++modalTestRunId;
  const testAllBtn = document.getElementById('modal-test-all-btn');
  const summaryEl = document.getElementById('modal-models-summary');

  const targets = forceRetest
    ? [...modelsList]
    : modelsList.filter(m => {
        const st = _getCachedModelStatus(pId, m);
        return !st || st.state === 'pending';
      });

  if (!targets.length) {
    updateModalSummaryDisplay(pId);
    return;
  }

  targets.forEach(m => {
    _setCachedModelStatus(pId, m, { state: 'pending', short: '⏳...', status: 'Queued...' });
    _updateModalRowBadge(pId, m);
  });

  if (testAllBtn) {
    testAllBtn.disabled = true;
    testAllBtn.innerText = `⏳ 0/${targets.length}`;
  }

  let done = 0;
  let nextIdx = 0;
  const concurrency = Math.min(5, targets.length);

  const worker = async () => {
    while (nextIdx < targets.length) {
      if (runId !== modalTestRunId || activeModalProvider !== pId) return;
      const mdl = targets[nextIdx++];
      await _pingSingleModalModel(pId, mdl);
      done++;
      if (runId === modalTestRunId && activeModalProvider === pId) {
        if (testAllBtn) testAllBtn.innerText = `⏳ ${done}/${targets.length}`;
        updateModalSummaryDisplay(pId);
      }
    }
  };

  try {
    await Promise.all(Array.from({ length: concurrency }, worker));
  } finally {
    if (runId === modalTestRunId && activeModalProvider === pId) {
      if (testAllBtn) {
        testAllBtn.innerText = 'Test All';
        testAllBtn.disabled = false;
      }
      updateModalSummaryDisplay(pId);
    }
  }
}

function testVisibleModalModels() {
  if (!activeModalProvider) return;
  const list = activeFilteredModels.length ? activeFilteredModels : activeDiscoveredModels;
  runModalModelsTest(activeModalProvider, list, true);
}

function renderDiscoveredList(list) {
  activeFilteredModels = list || [];
  const c = document.getElementById('search-list-container');
  if (!c) return;
  if (!list || list.length === 0) {
    c.innerHTML = '<div style="padding:10px; color:var(--text-muted); text-align:center;">No matching models.</div>';
    return;
  }
  const pId = activeModalProvider;
  const p = currentConfig.providers[pId];
  const savedSet = new Set(p?.models || []);
  c.innerHTML = '';
  list.forEach(m => {
    const isAdded = savedSet.has(m);
    const row = document.createElement('div');
    row.className = 'search-row';
    row.dataset.model = m;

    const left = document.createElement('div');
    left.className = 'search-row-left';
    const nameEl = document.createElement('span');
    nameEl.className = 'search-row-name';
    nameEl.textContent = m;
    nameEl.title = m;
    left.appendChild(nameEl);

    const actions = document.createElement('div');
    actions.className = 'search-row-actions';

    const statusBadge = document.createElement('span');
    statusBadge.className = 'modal-model-status';
    _applyModalBadge(statusBadge, _getCachedModelStatus(pId, m));
    statusBadge.addEventListener('click', (e) => {
      e.stopPropagation();
      testSingleModalModel(pId, m);
    });
    actions.appendChild(statusBadge);

    const actionBtn = document.createElement('button');
    actionBtn.type = 'button';
    if (isAdded) {
      actionBtn.className = 'btn btn-xs btn-danger';
      actionBtn.textContent = 'Remove';
      actionBtn.addEventListener('click', () => openConfirmDeleteModel(pId, m, true));
    } else {
      actionBtn.className = 'btn btn-xs btn-primary';
      actionBtn.textContent = '+ Add';
      actionBtn.addEventListener('click', () => addSpecificModel(pId, m));
    }
    actions.appendChild(actionBtn);

    row.appendChild(left);
    row.appendChild(actions);
    c.appendChild(row);
  });
  updateModalSummaryDisplay(pId);
}

async function addSpecificModel(pId, modelName) {
  const res = await fetch('/api/ui/provider-models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: pId, action: 'add', model: modelName })
  });
  const data = await res.json();
  if (res.ok) {
    showToast(`Added ${modelName}`);
    currentConfig = data.config;
    renderLanes();
    filterDiscoveredList();
  }
}

async function removeModel(pId, modelName, fromModal=false) {
  const res = await fetch('/api/ui/provider-models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: pId, action: 'remove', model: modelName })
  });
  const data = await res.json();
  if (res.ok) {
    showToast(`Removed ${modelName}`);
    currentConfig = data.config;
    renderLanes();
    if (fromModal) filterDiscoveredList();
  }
}

async function addCustomModelManual() {
  const input = document.getElementById('custom-model-input');
  if (!input) return;
  const val = input.value.trim();
  if (!val) return;
  await addSpecificModel(activeModalProvider, val);
  input.value = '';
}

function setServerProto(type) {
  const hidden = document.getElementById('server-type');
  if (hidden) hidden.value = type;
  const btnAnthropic = document.getElementById('btn-proto-anthropic');
  const btnOpenai = document.getElementById('btn-proto-openai');
  if (btnAnthropic) btnAnthropic.classList.toggle('is-active', type === 'anthropic');
  if (btnOpenai) btnOpenai.classList.toggle('is-active', type === 'openai');
}

function setServerMode(mode) {
  const eff = (mode === 'normal') ? 'normal' : 'agentic';
  const hidden = document.getElementById('server-mode');
  if (hidden) hidden.value = eff;
  const btnAgentic = document.getElementById('btn-mode-agentic');
  const btnNormal = document.getElementById('btn-mode-normal');
  if (btnAgentic) btnAgentic.classList.toggle('is-active', eff === 'agentic');
  if (btnNormal) btnNormal.classList.toggle('is-active', eff === 'normal');
  const hint = document.getElementById('server-mode-hint');
  if (hint) {
    hint.innerText = eff === 'normal'
      ? 'Fast chat + interactive Q/A only (saves tokens)'
      : 'Full tools, Bash, File Edit & Q/A';
    hint.style.color = eff === 'normal' ? '#d29922' : '#79c0ff';
  }
}

function applyPromptPreset(presetKey) {
  const el = document.getElementById('server-custom-prompt');
  if (!el) return;
  if (presetKey === 'clear') {
    el.value = '';
    return;
  }
  const presets = {
    concise: 'Be extremely concise, direct, and token-efficient. Avoid filler text and output minimal surgical code changes only.',
    bengali: 'Answer clearly and concisely in Bengali. Keep technical terms, commands, and code snippets in English.'
  };
  el.value = presets[presetKey] || '';
}

const WORKFLOW_TEMPLATES = {
  role_pipeline: {
    defaultName: 'Duo Architect & Coder',
    defaultSlug: 'duo_architect_coder',
    members: [
      {
        role: 'architect',
        provHint: 'coarena',
        modelHint: 'gemini-4-carbon',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'You are the Lead Software Architect. Formulate a structured blueprint. Be concise, output a structured blueprint only without filler text.'
      },
      {
        role: 'coder',
        provHint: 'groq',
        modelHint: 'openai/gpt-oss-120b',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'You are the Senior Implementation Engineer. Execute the approved architectural plan with clean, complete code and necessary tool calls.'
      }
    ]
  },
  parallel_council: {
    defaultName: 'Supreme Judge Consensus',
    defaultSlug: 'supreme_judge_council',
    members: [
      {
        role: 'councilor_1',
        provHint: 'coarena',
        modelHint: 'gemini-4-carbon',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'Expert perspective 1: Deep reasoning & architectural rigor. Be concise, output a structured blueprint only without filler text.'
      },
      {
        role: 'councilor_2',
        provHint: 'groq',
        modelHint: 'openai/gpt-oss-120b',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'Expert perspective 2: Fast pragmatic engineering, algorithm optimization, and edge-case prevention.'
      },
      {
        role: 'judge',
        provHint: 'googlestudio',
        modelHint: 'models/gemini-3.5-flash-lite',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'You are Supreme Judge and Synthesizer. Review all candidate solutions above, eliminate discrepancies, combine strengths, and deliver the final authoritative, bug-free solution.'
      }
    ]
  },
  plan_execute_audit: {
    defaultName: 'Full Cycle Tri-Tier Team',
    defaultSlug: 'full_cycle_team',
    members: [
      {
        role: 'architect',
        provHint: 'coarena',
        modelHint: 'gemini-4-carbon',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'System Architect: Analyze requirements, outline components and safety invariants. Be concise, output a structured blueprint only without filler text.'
      },
      {
        role: 'builder',
        provHint: 'groq',
        modelHint: 'openai/gpt-oss-120b',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'Lead Builder: Implement complete, functional code following the architectural plan.'
      },
      {
        role: 'auditor',
        provHint: 'googlestudio',
        modelHint: 'models/gemini-3.5-flash-lite',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'Security & Quality Auditor: Rigorously audit the built code for edge cases, security flaws, and performance regressions; output the final verified version.'
      }
    ]
  },
  speculative_draft: {
    defaultName: 'Speculative Lightning Draft',
    defaultSlug: 'speculative_draft_team',
    members: [
      {
        role: 'fast_drafter',
        provHint: 'googlestudio',
        modelHint: 'models/gemini-3.5-flash-lite',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'Rapid Prototyper: Generate an immediate structural scaffold and pseudocode. Be concise, output a structured blueprint only without filler text.'
      },
      {
        role: 'deep_finisher',
        provHint: 'coarena',
        modelHint: 'gemini-4-carbon',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'Deep Reasoning Finisher: Take the rapid draft, complete all implementations, enforce production hardening, and produce the final polished response.'
      }
    ]
  },
  router_evaluator: {
    defaultName: 'Smart Dynamic Router Team',
    defaultSlug: 'dynamic_router_team',
    members: [
      {
        role: 'gatekeeper',
        provHint: 'googlestudio',
        modelHint: 'models/gemini-3.5-flash-lite',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'Complexity Gatekeeper: Classify user query complexity (1-10) and outline requirements. Be concise, output a structured blueprint only without filler text.'
      },
      {
        role: 'expert',
        provHint: 'groq',
        modelHint: 'openai/gpt-oss-120b',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'Domain Specialist: Deliver the complete authoritative solution tailored to the evaluated complexity.'
      }
    ]
  },
  worker_reviewer: {
    defaultName: 'Worker & Polisher Team',
    defaultSlug: 'worker_reviewer_team',
    members: [
      {
        role: 'worker',
        provHint: 'groq',
        modelHint: 'openai/gpt-oss-120b',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'Primary Worker: Draft initial complete response. Be concise, output a structured blueprint only without filler text.'
      },
      {
        role: 'reviewer',
        provHint: 'coarena',
        modelHint: 'gemini-4-carbon',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'Senior Reviewer: Polish wording, correct any technical inaccuracies, and present the final refined answer.'
      }
    ]
  }
};

function _resolveProviderAndModel(provHint, modelHint) {
  const providers = currentConfig?.providers || {};
  const pKeys = Object.keys(providers);
  let p = provHint && providers[provHint] ? provHint : (pKeys[0] || '');
  let models = providers[p]?.models || [];
  let m = modelHint && models.includes(modelHint) ? modelHint : (models[0] || '');
  return { provider: p, model: m };
}

function openTeamModal(tId=null) {
  const modal = document.getElementById('team-modal');
  const title = document.getElementById('team-modal-title');
  const editId = document.getElementById('team-edit-id');
  const slugInput = document.getElementById('team-slug');
  const nameInput = document.getElementById('team-name');
  const wfInput = document.getElementById('team-workflow');
  const listEl = document.getElementById('team-members-list');

  if (listEl) listEl.innerHTML = '';

  if (tId && currentConfig?.multi_agent_teams?.[tId]) {
    const t = currentConfig.multi_agent_teams[tId];
    if (title) title.innerText = '🤖 EDIT TEAM: ' + (t.name || tId);
    if (editId) editId.value = tId;
    if (slugInput) { slugInput.value = tId; slugInput.disabled = true; }
    if (nameInput) nameInput.value = t.name || '';
    if (wfInput) wfInput.value = t.workflow || 'role_pipeline';
    (t.members || []).forEach(m => addTeamMemberRow(m.role, m.provider, m.model, m.prompt, m.tokens || m.max_tokens, m.mode, m.recommended));
  } else {
    if (title) title.innerText = '🤖 BUILD MULTI-AGENT TEAM';
    if (editId) editId.value = '';
    if (slugInput) { slugInput.value = 'duo_architect_coder'; slugInput.disabled = false; }
    if (nameInput) nameInput.value = 'Duo Architect & Coder';
    if (wfInput) wfInput.value = 'role_pipeline';
    onTeamWorkflowChange('role_pipeline');
  }
  if (modal) modal.classList.add('active');
}

function closeTeamModal() {
  const modal = document.getElementById('team-modal');
  if (modal) modal.classList.remove('active');
}

function onTeamWorkflowChange(val) {
  const tmpl = WORKFLOW_TEMPLATES[val] || WORKFLOW_TEMPLATES.role_pipeline;
  const listEl = document.getElementById('team-members-list');
  const editId = document.getElementById('team-edit-id')?.value;
  const slugInput = document.getElementById('team-slug');
  const nameInput = document.getElementById('team-name');

  if (!listEl) return;
  listEl.innerHTML = '';

  tmpl.members.forEach(mDef => {
    const res = _resolveProviderAndModel(mDef.provHint, mDef.modelHint);
    addTeamMemberRow(mDef.role, res.provider, res.model, mDef.prompt, mDef.tokens, mDef.mode, mDef.recommended);
  });

  // If adding new team and user hasn't typed custom name/slug, set suggested defaults
  if (!editId) {
    if (nameInput && (!nameInput.value || Object.values(WORKFLOW_TEMPLATES).some(t => t.defaultName === nameInput.value))) {
      nameInput.value = tmpl.defaultName;
    }
    if (slugInput && (!slugInput.value || Object.values(WORKFLOW_TEMPLATES).some(t => t.defaultSlug === slugInput.value))) {
      slugInput.value = tmpl.defaultSlug;
    }
  }
}

function setMemberMode(btn, newMode) {
  const seg = btn.closest('.proto-segmented');
  const row = btn.closest('.team-member-row');
  if (!seg || !row) return;

  [...seg.children].forEach(b => b.classList.remove('is-active'));
  btn.classList.add('is-active');

  const hiddenInput = row.querySelector('.t-member-mode');
  if (hiddenInput) hiddenInput.value = newMode;

  const recMode = hiddenInput?.getAttribute('data-recommended') || 'agentic';
  const badge = row.querySelector('.t-mode-warning-badge');

  if (recMode === 'agentic' && newMode === 'normal') {
    // User disabled tools on a member that is supposed to execute tools/code!
    row.classList.add('is-mode-hazard');
    if (badge) {
      badge.style.display = 'inline-block';
      badge.style.color = '#ff7b72';
      badge.style.fontWeight = '700';
      badge.innerText = '⚠️ Tools Disabled: Cannot write files or execute bash!';
    }
  } else if (recMode === 'normal' && newMode === 'agentic') {
    // User enabled tools on a planner/councilor that only needs text
    row.classList.remove('is-mode-hazard');
    if (badge) {
      badge.style.display = 'inline-block';
      badge.style.color = '#d29922';
      badge.style.fontWeight = '600';
      badge.innerText = 'ℹ️ Agentic active: +10k tool tokens overhead';
    }
  } else {
    // Normal / Recommended state
    row.classList.remove('is-mode-hazard');
    if (badge) {
      badge.style.display = 'none';
      badge.innerText = '';
    }
  }
}

function renderPanelItemsHtml(models, pId, curModel) {
  if (!models || !models.length) {
    return '<div style="padding:6px; color:var(--text-muted); font-size:10px; text-align:center;">No models configured for this provider.</div>';
  }
  return models.map(m => {
    const cached = (typeof _getCachedModelStatus === 'function') ? _getCachedModelStatus(pId, m) : null;
    const isSelected = (m === curModel);
    const dot = cached ? (cached.state === 'ok' ? '🟢' : (cached.state === 'pending' ? '⏳' : '🔴')) : '⚪';
    const statusColor = cached ? (cached.state === 'ok' ? 'var(--success-text)' : (cached.state === 'pending' ? 'var(--text-muted)' : 'var(--danger-text)')) : 'var(--text-muted)';
    const shortStatus = cached ? (cached.short || cached.status || '') : 'Untested';
    const borderStyle = isSelected ? 'border-color:#58a6ff; background:#162438;' : 'border-color:#1f2d40; background:#0d141f;';
    return `
      <div class="t-panel-item" style="display:flex; justify-content:space-between; align-items:center; padding:5px 8px; border-radius:4px; border:1px solid; ${borderStyle} cursor:pointer; transition:all 0.12s ease;" onclick="selectMemberModelFromPanel(this, '${m.replace(/'/g, "\\'")}')" title="Click to select ${m}">
        <div style="display:flex; align-items:center; gap:6px; min-width:0; overflow:hidden;">
          <span style="font-size:10px;">${dot}</span>
          <span style="font-size:10.5px; font-family:var(--mono); color:#e6edf3; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${m}</span>
          ${isSelected ? '<span style="font-size:8.5px; background:#1f4277; color:#79c0ff; padding:1px 4px; border-radius:2px; font-weight:700;">SELECTED</span>' : ''}
        </div>
        <span style="font-size:9.5px; font-family:var(--mono); color:${statusColor}; white-space:nowrap; margin-left:6px; font-weight:600;">${shortStatus}</span>
      </div>
    `;
  }).join('');
}

function renderPanelItemsForRow(row, pId) {
  const panelList = row?.querySelector('.t-panel-list');
  const curModel = row?.querySelector('.t-member-model')?.value || '';
  const models = currentConfig?.providers?.[pId]?.models || [];
  if (panelList) {
    panelList.innerHTML = renderPanelItemsHtml(models, pId, curModel);
  }
}

function updateMemberDisplayChip(row, modelName) {
  const provSel = row?.querySelector('.t-member-prov');
  const pId = provSel?.value || '';
  const cached = (typeof _getCachedModelStatus === 'function') ? _getCachedModelStatus(pId, modelName) : null;
  const dotEl = row?.querySelector('.t-cur-dot');
  const nameEl = row?.querySelector('.t-cur-name');
  const latEl = row?.querySelector('.t-cur-latency');

  const dot = cached ? (cached.state === 'ok' ? '🟢' : (cached.state === 'pending' ? '⏳' : '🔴')) : '⚪';
  const color = cached ? (cached.state === 'ok' ? 'var(--success-text)' : (cached.state === 'pending' ? 'var(--text-muted)' : 'var(--danger-text)')) : 'var(--text-muted)';
  const latency = cached?.short || (cached ? (cached.state === 'ok' ? 'OK' : 'Fail') : '');

  if (dotEl) dotEl.innerText = dot;
  if (nameEl) nameEl.innerText = modelName;
  if (latEl) {
    latEl.innerText = latency;
    latEl.style.color = color;
  }
}

function selectMemberModelFromPanel(itemEl, modelName) {
  const row = itemEl.closest('.team-member-row');
  if (!row) return;
  const hiddenInput = row.querySelector('.t-member-model');
  if (hiddenInput) {
    hiddenInput.value = modelName;
  }
  const provSel = row.querySelector('.t-member-prov');
  const pId = provSel?.value || '';

  updateMemberDisplayChip(row, modelName);
  renderPanelItemsForRow(row, pId);

  // Auto-close on selection
  const panel = row.querySelector('.t-member-models-panel');
  if (panel) panel.style.display = 'none';

  showToast(`Selected model: ${modelName}`);
}

function toggleMemberModelsPanel(el) {
  const row = el.closest('.team-member-row');
  const panel = row?.querySelector('.t-member-models-panel');
  if (!panel) return;
  const isHidden = (panel.style.display === 'none' || !panel.style.display);
  // Close other open panels for clean UI
  document.querySelectorAll('.t-member-models-panel').forEach(p => {
    if (p !== panel) p.style.display = 'none';
  });
  panel.style.display = isHidden ? 'block' : 'none';
}

async function checkAllProviderModelsStatus(btn) {
  const row = btn.closest('.team-member-row');
  if (!row) return;
  const provSel = row.querySelector('.t-member-prov');
  const hiddenModel = row.querySelector('.t-member-model');
  const pId = provSel?.value;
  if (!pId) return;

  const models = currentConfig?.providers?.[pId]?.models || [];
  if (!models.length) {
    showToast(`No models configured for ${pId}`, true);
    return;
  }

  const panel = row.querySelector('.t-member-models-panel');
  const panelSummary = row.querySelector('.t-panel-summary');
  const btnText = btn.querySelector('.t-btn-text');

  if (panel) panel.style.display = 'block';

  if (btnText) btnText.innerText = 'Pinging...';
  btn.disabled = true;

  let completed = 0, okCount = 0;
  const updateProgress = () => {
    if (panelSummary) panelSummary.innerText = `MODELS STATUS (${okCount}/${models.length} ACTIVE - ${completed}/${models.length} CHECKED)`;
    if (btnText) btnText.innerText = `⏳ ${completed}/${models.length}`;
    renderPanelItemsForRow(row, pId);
    if (hiddenModel) updateMemberDisplayChip(row, hiddenModel.value);
  };

  const pingPromises = models.map(m => {
    _setCachedModelStatus(pId, m, { state: 'pending', short: '⏳...', status: 'Pinging...' });
    renderPanelItemsForRow(row, pId);

    return fetch('/api/ui/test-models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: pId, model: m, discover_only: false })
    }).then(res => res.json()).then(data => {
      completed++;
      const resObj = (data.models || [])[0];
      if (resObj && resObj.active) {
        okCount++;
        _setCachedModelStatus(pId, m, { state: 'ok', short: resObj.short || '🟢 200', status: resObj.status || '🟢 200 OK' });
      } else {
        const errMsg = resObj?.status || data.message || 'Failed';
        _setCachedModelStatus(pId, m, { state: 'err', short: resObj?.short || '🔴 Fail', status: errMsg });
      }
      updateProgress();
    }).catch(() => {
      completed++;
      _setCachedModelStatus(pId, m, { state: 'err', short: '🔴 Err', status: 'Network error / Timeout' });
      updateProgress();
    });
  });

  try {
    await Promise.all(pingPromises);
    if (panelSummary) panelSummary.innerText = `MODELS STATUS (${okCount}/${models.length} ACTIVE)`;
    if (btnText) btnText.innerText = `📊 ${okCount}/${models.length} OK`;
    showToast(`${currentConfig?.providers?.[pId]?.name || pId}: ${okCount}/${models.length} models active`);
  } finally {
    btn.disabled = false;
  }
}

async function testSingleMemberModel(btn) {
  checkAllProviderModelsStatus(btn);
}

async function testAllModalMembers() {
  const rows = [...document.querySelectorAll('.team-member-row')];
  if (!rows.length) return;
  const testBtn = document.getElementById('team-modal-test-all-btn');
  const summaryBox = document.getElementById('team-modal-ping-summary');
  if (testBtn) { testBtn.innerText = '⏳ Testing...'; testBtn.disabled = true; }
  if (summaryBox) {
    summaryBox.style.display = 'block';
    summaryBox.innerText = `Pinging ${rows.length} member models...`;
    summaryBox.style.color = 'var(--text-muted)';
  }

  let okCount = 0;
  const promises = rows.map(async row => {
    const provSel = row.querySelector('.t-member-prov');
    const hiddenModel = row.querySelector('.t-member-model');
    const pId = provSel?.value;
    const m = hiddenModel?.value;
    if (!pId || !m) return;

    try {
      const res = await fetch('/api/ui/test-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: pId, model: m, discover_only: false })
      });
      const data = await res.json();
      const resObj = (data.models || [])[0];
      if (resObj && resObj.active) {
        okCount++;
        const info = { state: 'ok', short: resObj.short || '🟢 200', status: resObj.status || '🟢 200 OK' };
        if (typeof _setCachedModelStatus === 'function') _setCachedModelStatus(pId, m, info);
      } else {
        const errMsg = resObj?.status || data.message || 'Failed';
        const info = { state: 'err', short: resObj?.short || '🔴 Fail', status: errMsg };
        if (typeof _setCachedModelStatus === 'function') _setCachedModelStatus(pId, m, info);
      }
      updateMemberDisplayChip(row, m);
      renderPanelItemsForRow(row, pId);
    } catch (err) {
      const info = { state: 'err', short: '🔴 Err', status: 'Network error / Timeout' };
      if (typeof _setCachedModelStatus === 'function') _setCachedModelStatus(pId, m, info);
      updateMemberDisplayChip(row, m);
      renderPanelItemsForRow(row, pId);
    }
  });

  try {
    await Promise.all(promises);
    if (summaryBox) {
      const isAllOk = okCount === rows.length;
      summaryBox.innerText = `${okCount}/${rows.length} models active (${isAllOk ? '🟢 Strict Ready' : '🔴 Strict Halted'})`;
      summaryBox.style.color = isAllOk ? 'var(--success-text)' : 'var(--danger-text)';
    }
    showToast(`Team modal test: ${okCount}/${rows.length} models active`);
  } finally {
    if (testBtn) { testBtn.innerText = '🧪 Test All'; testBtn.disabled = false; }
  }
}

function addTeamMemberRow(role='', provider='', model='', prompt='', tokens='', mode='', recommended='') {
  const listEl = document.getElementById('team-members-list');
  if (!listEl) return;
  const memberIndex = listEl.children.length + 1;
  const row = document.createElement('div');
  row.className = 'team-member-row';

  const providers = currentConfig?.providers || {};
  const pKeys = Object.keys(providers);

  const curProv = provider || pKeys[0] || '';
  const provModels = providers[curProv]?.models || [];
  const curModel = model || provModels[0] || '';

  // Determine mode and recommended mode
  const recMode = recommended || (memberIndex === 1 ? 'normal' : 'agentic');
  const curMode = mode || recMode;

  const isHazard = (recMode === 'agentic' && curMode === 'normal');
  if (isHazard) row.classList.add('is-mode-hazard');

  const provOpts = pKeys.map(k => `<option value="${k}" ${k === curProv ? 'selected' : ''}>${providers[k]?.name || k}</option>`).join('');

  const curCached = (typeof _getCachedModelStatus === 'function') ? _getCachedModelStatus(curProv, curModel) : null;
  const statusDot = curCached ? (curCached.state === 'ok' ? '🟢' : '🔴') : '⚪';
  const statusColor = curCached ? (curCached.state === 'ok' ? 'var(--success-text)' : 'var(--danger-text)') : 'var(--text-muted)';
  const curLatency = curCached?.short || (curCached ? (curCached.state === 'ok' ? 'OK' : 'Fail') : '');

  const itemsHtml = renderPanelItemsHtml(provModels, curProv, curModel);

  row.innerHTML = `
    <!-- Top row: Member badge & remove button -->
    <div style="display:flex; justify-content:space-between; align-items:center;">
      <span style="font-size:11px; font-weight:700; color:#d2a8ff; font-family:var(--mono);">MEMBER #${memberIndex}</span>
      <button type="button" class="btn btn-xs btn-danger" style="padding:2px 7px; font-size:10px;" onclick="this.closest('.team-member-row').remove(); reindexTeamMembers();">✕ Remove</button>
    </div>

    <!-- Role Name and Server Provider Grid -->
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:6px; min-width:0;">
      <div style="min-width:0;">
        <label style="font-size:10px; color:var(--text-muted); display:block; margin-bottom:2px;">Role Name</label>
        <input type="text" class="t-member-role" placeholder="e.g. architect, coder" value="${role || 'worker'}" style="width:100%; min-width:0; font-size:11.5px; padding:5px 8px; box-sizing:border-box;" required />
      </div>
      <div style="min-width:0;">
        <label style="font-size:10px; color:var(--text-muted); display:block; margin-bottom:2px;">Server Provider</label>
        <select class="t-member-prov" style="width:100%; min-width:0; font-size:11.5px; padding:5px 8px; box-sizing:border-box;" onchange="updateMemberModels(this)">${provOpts}</select>
      </div>
    </div>

    <!-- Assigned Model (Custom Dark UI) and Max Tokens Grid -->
    <div style="display:grid; grid-template-columns: 2fr 1fr; gap:6px; min-width:0;">
      <div style="min-width:0;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:3px;">
          <label style="font-size:10px; color:var(--text-muted);">Assigned Model</label>
          <button type="button" class="btn btn-xs t-member-all-status-btn" onclick="checkAllProviderModelsStatus(this)" style="padding:1px 7px; font-size:9.5px; height:20px; line-height:1; background:#182333; border:1px solid #2d3f58; color:#79c0ff; border-radius:3px;" title="Check status of all models for this provider">
            <span class="t-btn-icon">📊</span> <span class="t-btn-text">Test Models</span>
          </button>
        </div>

        <!-- Custom Model Trigger Chip -->
        <div class="t-member-model-display" onclick="toggleMemberModelsPanel(this)" style="display:flex; justify-content:space-between; align-items:center; padding:6px 9px; font-size:11px; font-family:var(--mono); background:#0a0f16; border:1px solid #233145; border-radius:4px; color:#f0f4f8; cursor:pointer; min-width:0; user-select:none;" title="Click to toggle models list">
          <div style="display:flex; align-items:center; gap:6px; min-width:0; overflow:hidden;">
            <span class="t-cur-dot" style="font-size:10px;">${statusDot}</span>
            <span class="t-cur-name" style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-weight:600;">${curModel}</span>
          </div>
          <div style="display:flex; align-items:center; gap:5px; flex-shrink:0;">
            <span class="t-cur-latency" style="font-size:9.5px; color:${statusColor}; font-weight:600;">${curLatency}</span>
            <span style="font-size:9.5px; color:var(--text-muted);">▾</span>
          </div>
        </div>
        <input type="hidden" class="t-member-model" value="${curModel}" />

        <!-- Custom Dark Models Panel (Collapsible dropdown on tap) -->
        <div class="t-member-models-panel" style="display:none; margin-top:4px; background:#080d14; border:1px solid #2a3a52; border-radius:4px; padding:6px; max-height:190px; overflow-y:auto;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px; border-bottom:1px solid #1c2738; padding-bottom:3px;">
            <span style="font-size:10px; font-weight:600; color:#79c0ff;" class="t-panel-summary">MODELS STATUS (${provModels.length} AVAILABLE)</span>
            <span style="font-size:9.5px; color:var(--text-muted); cursor:pointer;" onclick="toggleMemberModelsPanel(this)">✕ Close</span>
          </div>
          <div class="t-panel-list" style="display:flex; flex-direction:column; gap:3px;">
            ${itemsHtml}
          </div>
        </div>
      </div>
      <div style="min-width:0;">
        <label style="font-size:10px; color:var(--text-muted); display:block; margin-bottom:2px;" title="Leave empty for unlimited tokens">Max Tokens</label>
        <input type="number" class="t-member-tokens" placeholder="Unlimited" value="${tokens || ''}" min="100" max="128000" style="width:100%; min-width:0; font-size:11px; padding:6px 8px; font-family:var(--mono); box-sizing:border-box; background:#0a0f16; border:1px solid #233145; border-radius:4px; color:#f0f4f8;" />
      </div>
    </div>

    <!-- Engine Mode Segmented Control with Hazard Warning -->
    <div style="display:flex; flex-direction:column; gap:3px; min-width:0;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <label style="font-size:10px; color:var(--text-muted);">Engine Mode</label>
        <span class="t-mode-warning-badge" style="font-size:9.5px; ${isHazard ? 'display:inline-block; color:#ff7b72; font-weight:700;' : (recMode === 'normal' && curMode === 'agentic' ? 'display:inline-block; color:#d29922; font-weight:600;' : 'display:none;')}">
          ${isHazard ? '⚠️ Tools Disabled: Cannot write files or execute bash!' : (recMode === 'normal' && curMode === 'agentic' ? 'ℹ️ Agentic active: +10k tool tokens overhead' : '')}
        </span>
      </div>
      <div class="proto-segmented" style="height:28px;">
        <button type="button" class="proto-seg-btn ${curMode === 'agentic' ? 'is-active' : ''}" style="font-size:10.5px;" onclick="setMemberMode(this, 'agentic')">⚡ Agentic (Full Tools)</button>
        <button type="button" class="proto-seg-btn ${curMode === 'normal' ? 'is-active' : ''}" style="font-size:10.5px;" onclick="setMemberMode(this, 'normal')">💡 Normal (Saves ~10k Tok)</button>
      </div>
      <input type="hidden" class="t-member-mode" value="${curMode}" data-recommended="${recMode}" />
    </div>

    <!-- Role System Instructions -->
    <div style="min-width:0;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:2px;">
        <label style="font-size:10px; color:var(--text-muted);">Role System Instructions (Optional)</label>
        ${memberIndex === 1 ? '<span style="font-size:9.5px; color:#58a6ff; font-weight:600;" title="Hidden backend concise invariant guard is always active">⚡ Concise Guard Active</span>' : ''}
      </div>
      <textarea class="t-member-prompt" rows="2" placeholder="e.g. You are the Architect..." style="width:100%; min-width:0; font-size:11px; padding:5px 8px; color:#c9d1d9; background:var(--bg); border:1px solid var(--border); border-radius:4px; box-sizing:border-box; resize:vertical;">${prompt || ''}</textarea>
    </div>
  `;
  listEl.appendChild(row);
}

function reindexTeamMembers() {
  const listEl = document.getElementById('team-members-list');
  if (!listEl) return;
  [...listEl.children].forEach((row, idx) => {
    const badge = row.querySelector('span');
    if (badge) badge.innerText = `MEMBER #${idx + 1}`;
  });
}

function updateMemberModels(selProv) {
  const row = selProv.closest('.team-member-row');
  if (!row) return;
  const pId = selProv.value;
  const models = currentConfig?.providers?.[pId]?.models || [];
  const curModel = models[0] || '';
  const hiddenInput = row.querySelector('.t-member-model');
  if (hiddenInput) hiddenInput.value = curModel;

  const btnText = row.querySelector('.t-member-all-status-btn .t-btn-text');
  if (btnText) btnText.innerText = 'Test Models';

  const panelSummary = row.querySelector('.t-panel-summary');
  if (panelSummary) panelSummary.innerText = `MODELS STATUS (${models.length} AVAILABLE)`;

  updateMemberDisplayChip(row, curModel);
  renderPanelItemsForRow(row, pId);
}

async function saveTeam(e) {
  e.preventDefault();
  const slug = document.getElementById('team-slug').value.trim().toLowerCase();
  const name = document.getElementById('team-name').value.trim();
  const wf = document.getElementById('team-workflow').value;
  const rows = [...document.querySelectorAll('.team-member-row')];

  const members = rows.map(r => {
    const tokVal = r.querySelector('.t-member-tokens')?.value.trim();
    const tokNum = tokVal ? parseInt(tokVal, 10) : null;
    return {
      role: r.querySelector('.t-member-role')?.value.trim() || 'worker',
      provider: r.querySelector('.t-member-prov')?.value || '',
      model: r.querySelector('.t-member-model')?.value || '',
      mode: r.querySelector('.t-member-mode')?.value || 'agentic',
      recommended: r.querySelector('.t-member-mode')?.getAttribute('data-recommended') || 'agentic',
      tokens: (tokNum && tokNum > 0) ? tokNum : null,
      prompt: r.querySelector('.t-member-prompt')?.value.trim() || ''
    };
  }).filter(m => m.provider && m.model);

  if (!members.length) {
    showToast('Add at least one member', true);
    return;
  }

  try {
    const res = await fetch('/api/ui/multi-agent-teams', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'save',
        id: slug,
        name: name,
        workflow: wf,
        enabled: true,
        members: members
      })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Team '${name}' saved & synced to chat dropdown!`);
      closeTeamModal();
      currentConfig = data.config;
      renderTeamsLane();
    } else {
      showToast(data.message || 'Save failed', true);
    }
  } catch (err) {
    showToast('Network error saving team', true);
  }
}

function openServerModal(pId=null) {
  const modal = document.getElementById('server-modal');
  const title = document.getElementById('modal-title-text');
  const editId = document.getElementById('edit-id');
  const idInput = document.getElementById('server-id');
  const nameInput = document.getElementById('server-name');
  const baseInput = document.getElementById('server-base');
  const typeInput = document.getElementById('server-type');
  const modelInput = document.getElementById('server-default-model');
  const keyInput = document.getElementById('server-key');
  const hdrsInput = document.getElementById('server-custom-headers');
  const promptInput = document.getElementById('server-custom-prompt');

  if (pId && currentConfig?.providers[pId]) {
    const p = currentConfig.providers[pId];
    if (title) title.innerText = 'Edit ' + (p.name || pId);
    if (editId) editId.value = pId;
    if (idInput) { idInput.value = pId; idInput.disabled = true; }
    if (nameInput) nameInput.value = p.name || '';
    if (baseInput) baseInput.value = p.base_url || '';
    setServerProto(p.type || 'anthropic');
    setServerMode(p.mode || 'agentic');
    if (modelInput) modelInput.value = p.default_model || '';
    if (keyInput) { keyInput.value = ''; keyInput.placeholder = '(Retain keys)'; }
    if (hdrsInput) hdrsInput.value = p.custom_headers ? JSON.stringify(p.custom_headers) : '';
    if (promptInput) promptInput.value = p.custom_prompt || '';
  } else {
    if (title) title.innerText = 'Add Server';
    if (editId) editId.value = '';
    if (idInput) { idInput.value = ''; idInput.disabled = false; }
    if (nameInput) nameInput.value = '';
    if (baseInput) baseInput.value = '';
    setServerProto('anthropic');
    setServerMode('agentic');
    if (modelInput) modelInput.value = '';
    if (keyInput) { keyInput.value = ''; keyInput.placeholder = 'sk-...'; }
    if (hdrsInput) hdrsInput.value = '';
    if (promptInput) promptInput.value = '';
  }
  if (modal) modal.classList.add('active');
}

function closeServerModal() {
  const modal = document.getElementById('server-modal');
  if (modal) modal.classList.remove('active');
}

async function saveServer(e) {
  e.preventDefault();
  const sId = document.getElementById('server-id').value.trim().toLowerCase();
  const sName = document.getElementById('server-name').value.trim();
  const sBase = document.getElementById('server-base').value.trim();
  const sType = document.getElementById('server-type').value;
  const sMode = document.getElementById('server-mode')?.value || 'agentic';
  const sModel = document.getElementById('server-default-model').value.trim();
  const sKey = document.getElementById('server-key').value.trim();
  const sHdrs = document.getElementById('server-custom-headers')?.value.trim();
  const sPrompt = document.getElementById('server-custom-prompt')?.value.trim() || '';

  const payload = {
    id: sId,
    name: sName,
    base_url: sBase,
    type: sType,
    mode: sMode,
    default_model: sModel,
    models: [sModel],
    custom_prompt: sPrompt
  };
  if (sKey) payload.keys = [sKey];
  if (sHdrs) payload.custom_headers = sHdrs;

  const res = await fetch('/api/ui/providers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (res.ok) {
    showToast('Server saved');
    closeServerModal();
    currentConfig = data.config;
    renderLanes();
    renderDropdown();
  }
}

// Confirmation Modal before Deletion (100% Pure HTML Modal - Zero Browser Popups)
function openConfirmModal(titleText, bodyHtml, confirmBtnText, onConfirm) {
  const modal = document.getElementById('confirm-modal');
  const title = document.getElementById('confirm-modal-title');
  const body = document.getElementById('confirm-modal-body');
  const btn = document.getElementById('confirm-modal-btn');
  if (title) title.innerText = titleText;
  if (body) body.innerHTML = bodyHtml;
  if (btn) {
    btn.innerText = confirmBtnText;
    btn.onclick = () => {
      closeConfirmModal();
      onConfirm();
    };
  }
  if (modal) modal.classList.add('active');
}

function openConfirmDelete(pId) {
  const name = currentConfig?.providers?.[pId]?.name || pId;
  openConfirmModal('Delete Server', `Are you sure you want to delete server <strong>${name}</strong>?<br><span style="color:var(--text-muted); font-size:11px; margin-top:4px; display:inline-block;">You will have 10 seconds to undo this action.</span>`, 'Delete Server', () => startServerDeletion(pId));
}

function openConfirmDeleteKey(pId, index) {
  const name = currentConfig?.providers?.[pId]?.name || pId;
  openConfirmModal('Revoke API Key', `Are you sure you want to revoke <strong>Key #${index+1}</strong> from <strong>${name}</strong>?<br><span style="color:var(--text-muted); font-size:11px; margin-top:4px; display:inline-block;">You will have 10 seconds to undo this action.</span>`, 'Revoke Key', () => startKeyDeletion(pId, index));
}

function openConfirmDeleteModel(pId, modelName, fromModal=false) {
  const name = currentConfig?.providers?.[pId]?.name || pId;
  openConfirmModal('Remove Model', `Are you sure you want to remove model <strong>${modelName}</strong> from <strong>${name}</strong>?<br><span style="color:var(--text-muted); font-size:11px; margin-top:4px; display:inline-block;">You will have 10 seconds to undo this action.</span>`, 'Remove Model', () => startModelDeletion(pId, modelName, fromModal));
}

function openConfirmDeleteTeam(teamId) {
  const name = currentConfig?.multi_agent_teams?.[teamId]?.name || teamId;
  openConfirmModal(
    'Delete Multi-Agent Team',
    `Are you sure you want to delete team <strong>${name}</strong>?<br><span style="color:var(--text-muted); font-size:11px; margin-top:4px; display:inline-block;">You will have 10 seconds to undo this action.</span>`,
    'Delete Team',
    () => startTeamDeletion(teamId)
  );
}

function closeConfirmModal() {
  const modal = document.getElementById('confirm-modal');
  if (modal) modal.classList.remove('active');
}

// 10-Second Undo Deletion System (Unified for Servers, Keys, and Models)
let pendingDeletion = null;
let undoCountdownTimer = null;
let undoProgressInterval = null;

function startServerDeletion(pId) {
  if (pendingDeletion) commitPendingDeletion();
  const pObj = currentConfig?.providers?.[pId];
  if (!pObj) return;

  const serverName = pObj.name || pId;
  const isRouted = currentConfig.routed_providers?.includes(pId);
  const routedIndex = isRouted ? currentConfig.routed_providers.indexOf(pId) : -1;
  const unroutedIndex = !isRouted ? currentConfig.unrouted_providers?.indexOf(pId) : -1;

  pendingDeletion = {
    type: 'server',
    pId: pId,
    name: serverName,
    data: JSON.parse(JSON.stringify(pObj)),
    isRouted: isRouted,
    routedIndex: routedIndex,
    unroutedIndex: unroutedIndex
  };

  delete currentConfig.providers[pId];
  if (currentConfig.routed_providers) currentConfig.routed_providers = currentConfig.routed_providers.filter(x => x !== pId);
  if (currentConfig.unrouted_providers) currentConfig.unrouted_providers = currentConfig.unrouted_providers.filter(x => x !== pId);
  renderLanes();
  renderDropdown();

  showUndoToast(`Deleted '${serverName}'`);
}

function startKeyDeletion(pId, index) {
  if (pendingDeletion) commitPendingDeletion();
  const pObj = currentConfig?.providers?.[pId];
  if (!pObj || !pObj.keys || pObj.keys[index] === undefined) return;

  const keyVal = pObj.keys[index];
  pendingDeletion = {
    type: 'key',
    pId: pId,
    index: index,
    keyVal: keyVal
  };

  pObj.keys.splice(index, 1);
  renderLanes();

  showUndoToast(`Revoked Key #${index+1}`);
}

function startModelDeletion(pId, modelName, fromModal=false) {
  if (pendingDeletion) commitPendingDeletion();
  const pObj = currentConfig?.providers?.[pId];
  if (!pObj || !pObj.models) return;

  const prevModels = [...pObj.models];
  pendingDeletion = {
    type: 'model',
    pId: pId,
    modelName: modelName,
    fromModal: fromModal,
    prevModels: prevModels
  };

  pObj.models = pObj.models.filter(m => m !== modelName);
  renderLanes();
  if (fromModal) filterDiscoveredList();

  showUndoToast(`Removed model '${modelName}'`);
}

function startTeamDeletion(teamId) {
  if (pendingDeletion) commitPendingDeletion();
  const teamObj = currentConfig?.multi_agent_teams?.[teamId];
  if (!teamObj) return;

  const teamName = teamObj.name || teamId;
  pendingDeletion = {
    type: 'team',
    teamId: teamId,
    name: teamName,
    data: JSON.parse(JSON.stringify(teamObj))
  };

  delete currentConfig.multi_agent_teams[teamId];
  renderTeamsLane();
  showUndoToast(`Deleted team '${teamName}'`);
}

function showUndoToast(msg) {
  const toast = document.getElementById('undo-toast');
  const msgEl = document.getElementById('undo-toast-msg');
  const bar = document.getElementById('undo-progress-bar');
  if (!toast || !msgEl || !bar) return;

  msgEl.innerText = msg;
  toast.classList.remove('expiring');
  toast.classList.add('show');
  bar.style.width = '100%';

  const durationMs = 10000;
  const startTime = Date.now();

  if (undoProgressInterval) clearInterval(undoProgressInterval);
  undoProgressInterval = setInterval(() => {
    const elapsed = Date.now() - startTime;
    const remainingPct = Math.max(0, 100 - (elapsed / durationMs) * 100);
    bar.style.width = remainingPct + '%';

    if (elapsed >= 7500) {
      toast.classList.add('expiring');
    }

    if (elapsed >= durationMs) {
      clearInterval(undoProgressInterval);
      undoProgressInterval = null;
    }
  }, 100);

  if (undoCountdownTimer) clearTimeout(undoCountdownTimer);
  undoCountdownTimer = setTimeout(() => {
    commitPendingDeletion();
  }, durationMs);
}

function hideUndoToast() {
  const toast = document.getElementById('undo-toast');
  if (toast) {
    toast.classList.remove('show');
    toast.classList.remove('expiring');
  }
  if (undoProgressInterval) {
    clearInterval(undoProgressInterval);
    undoProgressInterval = null;
  }
  if (undoCountdownTimer) {
    clearTimeout(undoCountdownTimer);
    undoCountdownTimer = null;
  }
}

function triggerUndoAction() {
  if (!pendingDeletion) return;
  const item = pendingDeletion;
  pendingDeletion = null;
  hideUndoToast();

  if (item.type === 'server') {
    currentConfig.providers[item.pId] = item.data;
    const pool = item.isRouted ? currentConfig.routed_providers : currentConfig.unrouted_providers;
    if (pool) {
      const idx = item.isRouted ? item.routedIndex : item.unroutedIndex;
      idx >= 0 ? pool.splice(idx, 0, item.pId) : pool.push(item.pId);
    }
    renderLanes();
    renderDropdown();
    showToast(`↺ Restored '${item.name}'`);
    saveDomOrderAndSync();
  } else if (item.type === 'key') {
    const pObj = currentConfig?.providers?.[item.pId];
    if (pObj) {
      if (!pObj.keys) pObj.keys = [];
      pObj.keys.splice(item.index, 0, item.keyVal);
      renderLanes();
    }
    showToast(`↺ Restored Key #${item.index+1}`);
  } else if (item.type === 'model') {
    const pObj = currentConfig?.providers?.[item.pId];
    if (pObj) {
      pObj.models = item.prevModels;
      renderLanes();
      if (item.fromModal) filterDiscoveredList();
    }
    showToast(`↺ Restored '${item.modelName}'`);
  } else if (item.type === 'team') {
    if (!currentConfig.multi_agent_teams) currentConfig.multi_agent_teams = {};
    currentConfig.multi_agent_teams[item.teamId] = item.data;
    renderTeamsLane();
    showToast(`↺ Restored Team '${item.name}'`);
  }
}

async function commitPendingDeletion() {
  if (!pendingDeletion) return;
  const item = pendingDeletion;
  pendingDeletion = null;
  hideUndoToast();

  try {
    let url, method = 'DELETE', body;
    if (item.type === 'server') {
      url = '/api/ui/providers';
      body = { provider: item.pId };
    } else if (item.type === 'key') {
      url = '/api/ui/keys';
      body = { provider: item.pId, index: item.index };
    } else if (item.type === 'model') {
      url = '/api/ui/provider-models';
      method = 'POST';
      body = { provider: item.pId, action: 'remove', model: item.modelName };
    } else if (item.type === 'team') {
      url = '/api/ui/multi-agent-teams';
      method = 'POST';
      body = { action: 'delete', id: item.teamId };
    }
    const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json();
    if (res.ok) {
      currentConfig = data.config;
      renderLanes();
      if (item.type === 'server') renderDropdown();
      if (item.type === 'model' && item.fromModal) filterDiscoveredList();
    }
  } catch (err) {
    showToast('Error completing deletion', true);
  }
}

function deleteServer(pId) {
  openConfirmDelete(pId);
}

// ===== LIVE LOGS MODAL =====
function openLogsModal() {
  const modal = document.getElementById('logs-modal');
  if (modal) modal.classList.add('active');
  fetchLogs();
  toggleLogsAutoRefresh();
}

function closeLogsModal() {
  const modal = document.getElementById('logs-modal');
  if (modal) modal.classList.remove('active');
  if (logsRefreshTimer) {
    clearInterval(logsRefreshTimer);
    logsRefreshTimer = null;
  }
}

function toggleLogsAutoRefresh() {
  if (logsRefreshTimer) {
    clearInterval(logsRefreshTimer);
    logsRefreshTimer = null;
  }
  const cb = document.getElementById('logs-auto-refresh');
  const modal = document.getElementById('logs-modal');
  if (cb && cb.checked && modal && modal.classList.contains('active')) {
    logsRefreshTimer = setInterval(fetchLogs, 3000);
  }
}

async function fetchLogs() {
  const pre = document.getElementById('logs-viewer-pre');
  const cdPill = document.getElementById('logs-cooldown-pill');
  const hideStatus = document.getElementById('logs-hide-status')?.checked ? '1' : '0';
  try {
    const res = await fetch(`/api/ui/logs?lines=80&hide_status=${hideStatus}`);
    const data = await res.json();
    if (res.ok && pre) {
      const lines = data.lines || [];
      pre.textContent = lines.length ? lines.join('\n') : '(No log entries yet)';
      pre.scrollTop = pre.scrollHeight;
    }
    if (cdPill) {
      const cds = data.cooldowns || [];
      cdPill.innerText = cds.length ? `Cooldowns: ${cds.length}` : 'Cooldowns: 0';
      cdPill.style.color = cds.length ? '#d29922' : 'var(--text-muted)';
    }
  } catch (err) {
    if (pre) pre.textContent = '[Error fetching logs]';
  }
}

// ===== BACKUP / RESTORE MODAL =====
function openBackupModal() {
  const modal = document.getElementById('backup-modal');
  const ta = document.getElementById('backup-json-input');
  const fi = document.getElementById('backup-file-input');
  if (ta) ta.value = '';
  if (fi) fi.value = '';
  if (modal) modal.classList.add('active');
}

function closeBackupModal() {
  const modal = document.getElementById('backup-modal');
  if (modal) modal.classList.remove('active');
}

function exportConfigBackup() {
  if (!currentConfig) {
    showToast('Config not loaded yet', true);
    return;
  }
  const includeKeys = document.getElementById('backup-include-keys')?.checked !== false;
  const clone = JSON.parse(JSON.stringify(currentConfig));
  if (!includeKeys && clone.providers) {
    Object.values(clone.providers).forEach(p => { p.keys = []; });
  }
  const jsonStr = JSON.stringify(clone, null, 2);
  const blob = new Blob([jsonStr], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const dateStr = new Date().toISOString().slice(0, 10);
  a.href = url;
  a.download = `claude-router-backup-${dateStr}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  showToast(includeKeys ? 'Backup exported (with keys)' : 'Backup exported (without keys)');
}

function handleBackupFileSelect(e) {
  const file = e.target?.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    const ta = document.getElementById('backup-json-input');
    if (ta) ta.value = String(reader.result || '');
    showToast(`Loaded ${file.name} — tap Restore Config`);
  };
  reader.readAsText(file);
}

async function importConfigBackup() {
  const raw = (document.getElementById('backup-json-input')?.value || '').trim();
  if (!raw) {
    showToast('Paste backup JSON or choose a file first', true);
    return;
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    showToast('Invalid JSON format', true);
    return;
  }
  try {
    const res = await fetch('/api/ui/config-import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config: parsed })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || 'Restore failed', true);
      return;
    }
    currentConfig = data.config;
    renderLanes();
    renderDropdown();
    renderRecoveryToggle();
    closeBackupModal();
    showToast(data.message || 'Config restored');
  } catch (err) {
    showToast('Error restoring config', true);
  }
}

// Auto-blur focused input on Enter / Done on mobile keyboard
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && e.target && e.target.tagName === 'INPUT' && e.target.type !== 'submit') {
    e.target.blur();
  }
});

