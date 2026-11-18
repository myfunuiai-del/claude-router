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
