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

