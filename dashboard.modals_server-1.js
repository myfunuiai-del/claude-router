// dashboard.modals_server-1.js - Server Configuration Modal, Logs Modal, and Backup/Restore
// Modularized per gemini.md Rule 2 (Limit 400-500 lines)

let logsRefreshTimer = null;
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
  const rpmInput = document.getElementById('server-rpm');
  const maxReqInput = document.getElementById('server-max-requests');
  const winHoursInput = document.getElementById('server-window-hours');
  const rpmLabel = document.getElementById('label-rpm-status');
  const winLabel = document.getElementById('label-window-status');

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

    const rl = p.rate_limit || {};
    if (rpmInput) {
      rpmInput.value = (rl.rpm && rl.rpm > 0) ? rl.rpm : '';
      if (rpmLabel) {
        rpmLabel.innerText = rpmInput.value ? `${rpmInput.value} RPM` : 'Unlimited';
        rpmLabel.style.color = rpmInput.value ? '#79c0ff' : '#56d364';
      }
    }
    if (maxReqInput) {
      maxReqInput.value = (rl.max_requests && rl.max_requests > 0) ? rl.max_requests : '';
      if (winLabel) {
        winLabel.innerText = maxReqInput.value ? `${maxReqInput.value} reqs` : 'Unlimited';
        winLabel.style.color = maxReqInput.value ? '#79c0ff' : '#56d364';
      }
    }
    if (winHoursInput) {
      winHoursInput.value = (rl.window_hours && rl.window_hours > 0) ? rl.window_hours : 1;
    }
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
    if (rpmInput) rpmInput.value = '';
    if (maxReqInput) maxReqInput.value = '';
    if (winHoursInput) winHoursInput.value = 1;
    if (rpmLabel) { rpmLabel.innerText = 'Unlimited'; rpmLabel.style.color = '#56d364'; }
    if (winLabel) { winLabel.innerText = 'Unlimited'; winLabel.style.color = '#56d364'; }
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
  const sRpm = parseInt(document.getElementById('server-rpm')?.value.trim() || '', 10);
  const sMaxReq = parseInt(document.getElementById('server-max-requests')?.value.trim() || '', 10);
  const sWinHours = parseFloat(document.getElementById('server-window-hours')?.value.trim() || '1') || 1;

  const payload = {
    id: sId,
    name: sName,
    base_url: sBase,
    type: sType,
    mode: sMode,
    default_model: sModel,
    models: [sModel],
    custom_prompt: sPrompt,
    rate_limit: {
      rpm: (!isNaN(sRpm) && sRpm > 0) ? sRpm : null,
      max_requests: (!isNaN(sMaxReq) && sMaxReq > 0) ? sMaxReq : null,
      window_hours: sWinHours
    }
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

function onRpmInput(el) {
  const lbl = document.getElementById('label-rpm-status');
  const val = parseInt(el.value, 10);
  if (lbl) {
    lbl.innerText = (!isNaN(val) && val > 0) ? `${val} RPM` : 'Unlimited';
    lbl.style.color = (!isNaN(val) && val > 0) ? '#79c0ff' : '#56d364';
  }
}

function onWindowReqInput(el) {
  const lbl = document.getElementById('label-window-status');
  const val = parseInt(el.value, 10);
  if (lbl) {
    lbl.innerText = (!isNaN(val) && val > 0) ? `${val} reqs` : 'Unlimited';
    lbl.style.color = (!isNaN(val) && val > 0) ? '#79c0ff' : '#56d364';
  }
}

function toggleUnlimitedRpm() {
  const input = document.getElementById('server-rpm');
  if (input) {
    input.value = '';
    onRpmInput(input);
  }
}

function toggleUnlimitedWindow() {
  const input = document.getElementById('server-max-requests');
  if (input) {
    input.value = '';
    onWindowReqInput(input);
  }
}

// Auto-blur focused input on Enter / Done on mobile keyboard
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && e.target && e.target.tagName === 'INPUT' && e.target.type !== 'submit') {
    e.target.blur();
  }
});

