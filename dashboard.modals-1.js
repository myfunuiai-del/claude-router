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
    (t.members || []).forEach(m => addTeamMemberRow(m.role, m.provider, m.model, m.prompt));
  } else {
    if (title) title.innerText = '🤖 BUILD MULTI-AGENT TEAM';
    if (editId) editId.value = '';
    if (slugInput) { slugInput.value = ''; slugInput.disabled = false; }
    if (nameInput) nameInput.value = '';
    if (wfInput) wfInput.value = 'role_pipeline';
    // Defaults: Member 1 Planner + Member 2 Coder
    addTeamMemberRow('planner', 'coarena', 'gemini-4-carbon', 'Architect / Planner');
    addTeamMemberRow('coder', 'groq', 'openai/gpt-oss-120b', 'Implementation / Coder');
  }
  if (modal) modal.classList.add('active');
}

function closeTeamModal() {
  const modal = document.getElementById('team-modal');
  if (modal) modal.classList.remove('active');
}

function onTeamWorkflowChange(val) {
  const listEl = document.getElementById('team-members-list');
  if (!listEl) return;
  // If user selected parallel council and has < 3 members, auto suggest Councilor 1, 2 + Judge
  if (val === 'parallel_council' && listEl.children.length < 3) {
    listEl.innerHTML = '';
    addTeamMemberRow('councilor_1', 'coarena', 'gemini-4-carbon', 'Expert perspective 1: Deep reasoning & architecture');
    addTeamMemberRow('councilor_2', 'groq', 'openai/gpt-oss-120b', 'Expert perspective 2: Fast algorithmic & code implementation');
    addTeamMemberRow('judge', 'googlestudio', 'models/gemini-3.5-flash-lite', 'Supreme Judge: Compare both candidates, eliminate flaws, and synthesize the ultimate solution');
  }
}

function addTeamMemberRow(role='', provider='', model='', prompt='') {
  const listEl = document.getElementById('team-members-list');
  if (!listEl) return;
  const memberIndex = listEl.children.length + 1;
  const row = document.createElement('div');
  row.className = 'team-member-row';
  row.style.cssText = 'background:#0d1520; border:1px solid #2b3d56; border-left:3px solid #8957e5; border-radius:6px; padding:10px; display:flex; flex-direction:column; gap:8px;';

  const providers = currentConfig?.providers || {};
  const pKeys = Object.keys(providers);

  const curProv = provider || pKeys[0] || '';
  const provModels = providers[curProv]?.models || [];
  const curModel = model || provModels[0] || '';

  const provOpts = pKeys.map(k => `<option value="${k}" ${k === curProv ? 'selected' : ''}>${providers[k]?.name || k}</option>`).join('');
  const modelOpts = provModels.map(m => `<option value="${m}" ${m === curModel ? 'selected' : ''}>${m}</option>`).join('');

  row.innerHTML = `
    <!-- Top row: Member badge & remove button -->
    <div style="display:flex; justify-content:space-between; align-items:center;">
      <span style="font-size:11px; font-weight:700; color:#d2a8ff; font-family:var(--mono);">MEMBER #${memberIndex}</span>
      <button type="button" class="btn btn-xs btn-danger" style="padding:1px 6px; font-size:10.5px;" onclick="this.closest('.team-member-row').remove(); reindexTeamMembers();">✕ Remove</button>
    </div>

    <!-- Field 1: Role -->
    <div>
      <label style="font-size:10px; color:var(--text-muted); display:block; margin-bottom:2px;">Role Name</label>
      <input type="text" class="t-member-role" placeholder="e.g. planner, coder, reviewer" value="${role || 'worker'}" style="width:100%; font-size:11.5px; padding:6px 8px;" required />
    </div>

    <!-- Field 2 & 3: Server Provider and Model (Clean 2-Column Grid) -->
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
      <div>
        <label style="font-size:10px; color:var(--text-muted); display:block; margin-bottom:2px;">Server Provider</label>
        <select class="t-member-prov" style="width:100%; font-size:11.5px; padding:6px 8px;" onchange="updateMemberModels(this)">${provOpts}</select>
      </div>
      <div>
        <label style="font-size:10px; color:var(--text-muted); display:block; margin-bottom:2px;">Assigned Model</label>
        <select class="t-member-model" style="width:100%; font-size:11.5px; padding:6px 8px;">${modelOpts}</select>
      </div>
    </div>

    <!-- Field 4: Role Prompt -->
    <div>
      <label style="font-size:10px; color:var(--text-muted); display:block; margin-bottom:2px;">Role System Instructions (Optional)</label>
      <input type="text" class="t-member-prompt" placeholder="e.g. You are the Architect. Analyze and write a clean plan." value="${prompt || ''}" style="width:100%; font-size:11px; padding:5px 8px; color:#c9d1d9;" />
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
  const selModel = row?.querySelector('.t-member-model');
  if (!selModel) return;
  const pId = selProv.value;
  const models = currentConfig?.providers?.[pId]?.models || [];
  selModel.innerHTML = models.map(m => `<option value="${m}">${m}</option>`).join('');
}

async function saveTeam(e) {
  e.preventDefault();
  const slug = document.getElementById('team-slug').value.trim().toLowerCase();
  const name = document.getElementById('team-name').value.trim();
  const wf = document.getElementById('team-workflow').value;
  const rows = [...document.querySelectorAll('.team-member-row')];

  const members = rows.map(r => ({
    role: r.querySelector('.t-member-role')?.value.trim() || 'worker',
    provider: r.querySelector('.t-member-prov')?.value || '',
    model: r.querySelector('.t-member-model')?.value || '',
    prompt: r.querySelector('.t-member-prompt')?.value.trim() || ''
  })).filter(m => m.provider && m.model);

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

