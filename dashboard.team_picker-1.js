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
