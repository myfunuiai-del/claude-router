// dashboard.teams-1.js - Multi-Agent Teams Lane rendering, status testing, and power toggles
// Modularized per gemini.md Rule 2 (Limit 400-500 lines)

function renderTeamsLane() {
  const cTeams = document.getElementById('container-multiagent');
  const countEl = document.getElementById('count-multiagent');
  if (!cTeams) return;
  cTeams.innerHTML = '';
  const teams = currentConfig.multi_agent_teams || {};
  const teamList = Object.values(teams);
  if (countEl) countEl.innerText = `${teamList.length} Teams`;

  if (teamList.length === 0) {
    cTeams.innerHTML = '<div class="lane-empty">No mix teams yet — tap + Add to build your first Multi-Agent orchestra</div>';
    return;
  }

  teamList.forEach(t => {
    const card = document.createElement('div');
    const isEn = t.enabled !== false;
    card.className = `server-card${isEn ? '' : ' server-off'}`;
    card.id = `team-card-${t.id}`;

    const membersHtml = (t.members || []).map((m, idx) => {
      const pObj = currentConfig.providers?.[m.provider] || {};
      const pName = pObj.name || m.provider;
      const mName = (m.model || '').split('/').pop();
      const role = m.role || `step_${idx+1}`;
      const mMode = m.mode || (idx === 0 ? 'normal' : 'agentic');
      const modeIcon = mMode === 'agentic' ? '⚡' : '💡';
      const modeColor = mMode === 'agentic' ? '#79c0ff' : '#f2cc60';
      const cached = (typeof _getCachedModelStatus === 'function') ? _getCachedModelStatus(m.provider, m.model) : null;
      const initialStatus = cached ? (cached.state === 'ok' ? '🟢' : '🔴') : '';
      const initialTitle = cached ? (cached.status || '') : '';
      return `<span class="chip" style="font-size:10px;"><strong style="color:#d2a8ff;">${role}:</strong> ${pName} (${mName}) <span class="chip-status" id="team-member-status-${t.id}-${idx}" title="${initialTitle}">${initialStatus}</span><span class="member-mode-glow-btn is-${mMode}" title="Mode: ${mMode === 'agentic' ? '⚡ Agentic (Full Tools)' : '💡 Normal (Saves tokens)'} — Tap to switch" onclick="event.stopPropagation(); toggleTeamMemberMode('${t.id}', ${idx})">${modeIcon}</span></span>`;
    }).join(' ');

    card.innerHTML = `
      <div class="server-card-top" style="cursor:default;">
        <div class="server-card-header-row">
          <div class="server-card-title-group">
            <span class="prio-tag" style="background:rgba(137, 87, 229, 0.25); color:#d2a8ff; border:1px solid rgba(137, 87, 229, 0.6);">TEAM</span>
            <span class="server-name" style="color:#fff;">${t.name || t.id}</span>
            <span class="server-proto" style="background:#241b35; color:#d2a8ff; border-color:#8957e555;">${t.workflow || 'pipeline'}</span>
          </div>
          <div class="server-header-right" style="display:flex; flex-direction:column; align-items:flex-end; gap:5px;">
            <button type="button" class="power-toggle ${isEn ? 'is-on' : 'is-off'}" onclick="toggleTeamPower('${t.id}')">
              <span class="power-dot"></span>
              <span class="power-label">${isEn ? 'ON' : 'OFF'}</span>
            </button>
            <button type="button" class="btn btn-xs" id="team-test-btn-${t.id}" style="padding:1px 8px; font-size:10px;" onclick="testTeamMembers('${t.id}')">
              🧪 Test
            </button>
          </div>
        </div>
        <div class="server-card-controls-row" style="margin-top:6px;">
          <div class="server-card-left-tags" style="flex-wrap:wrap; gap:4px;">
            <span style="font-size:10px; font-family:var(--mono); color:#d2a8ff; background:#1e1430; padding:2px 6px; border-radius:4px; border:1px solid #58338f; cursor:pointer;" onclick="copyDirectRoute('multiagent')" title="Copy route">
              📋 /multiagent
            </span>
            ${membersHtml}
          </div>
          <div class="server-card-btn-group">
            <button class="btn btn-xs" onclick="openTeamModal('${t.id}')">✏️ Edit</button>
            <button class="safe-delete-btn" onclick="deleteTeam('${t.id}')">🗑️</button>
          </div>
        </div>
        <div class="ping-summary" id="team-ping-${t.id}" style="margin-top:4px;"></div>
      </div>
    `;
    cTeams.appendChild(card);
  });
}

async function testTeamMembers(tId) {
  const team = currentConfig?.multi_agent_teams?.[tId];
  if (!team) return;
  const members = team.members || [];
  if (!members.length) {
    showToast('No members configured in team', true);
    return;
  }

  const btn = document.getElementById(`team-test-btn-${tId}`);
  const summaryBox = document.getElementById(`team-ping-${tId}`);

  if (btn) {
    btn.innerText = '⏳...';
    btn.disabled = true;
  }

  members.forEach((m, idx) => {
    const el = document.getElementById(`team-member-status-${tId}-${idx}`);
    if (el) {
      el.innerHTML = '⏳';
      el.title = 'Testing member...';
    }
  });

  let completed = 0, okCount = 0;
  const updateSummary = () => {
    if (summaryBox) summaryBox.innerText = `${okCount}/${members.length} active (${completed}/${members.length} checked)`;
  };
  updateSummary();

  const pingPromises = members.map((m, idx) => {
    const pId = m.provider;
    const model = m.model;
    const el = document.getElementById(`team-member-status-${tId}-${idx}`);

    return fetch('/api/ui/test-models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: pId, model: model, discover_only: false })
    }).then(res => res.json()).then(data => {
      completed++;
      const resObj = (data.models || [])[0];
      if (resObj && resObj.active) {
        okCount++;
        if (typeof _setCachedModelStatus === 'function') {
          _setCachedModelStatus(pId, model, { state: 'ok', short: resObj.short || '🟢 200', status: resObj.status || '🟢 200 OK' });
        }
        if (el) { el.innerHTML = '🟢'; el.title = resObj.status || '🟢 200 OK'; }
      } else {
        if (typeof _setCachedModelStatus === 'function') {
          _setCachedModelStatus(pId, model, { state: 'err', short: resObj?.short || '🔴 Fail', status: resObj?.status || 'Failed' });
        }
        if (el) { el.innerHTML = '🔴'; el.title = resObj?.status || 'Failed'; }
      }
      updateSummary();
    }).catch(() => {
      completed++;
      if (typeof _setCachedModelStatus === 'function') {
        _setCachedModelStatus(pId, model, { state: 'err', short: '🔴 Err', status: 'Network error / Timeout' });
      }
      if (el) { el.innerHTML = '🔴'; el.title = 'Network error / Timeout'; }
      updateSummary();
    });
  });

  try {
    await Promise.all(pingPromises);
    if (summaryBox) {
      const isAllOk = okCount === members.length;
      summaryBox.innerText = `${okCount}/${members.length} active (${isAllOk ? '🟢 Strict Ready' : '🔴 Strict Halted'})`;
      summaryBox.style.color = isAllOk ? 'var(--success-text)' : 'var(--danger-text)';
    }
    showToast(`${team.name || tId}: ${okCount}/${members.length} members active`);
  } finally {
    if (btn) {
      btn.innerText = '🧪 Test';
      btn.disabled = false;
    }
  }
}

async function toggleTeamPower(teamId) {
  try {
    const res = await fetch('/api/ui/multi-agent-teams', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'toggle', id: teamId })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message);
      currentConfig = data.config;
      renderTeamsLane();
    }
  } catch (e) {
    showToast('Failed to toggle team', true);
  }
}

function deleteTeam(teamId) {
  openConfirmDeleteTeam(teamId);
}

async function toggleTeamMemberMode(tId, memberIndex) {
  const team = currentConfig?.multi_agent_teams?.[tId];
  if (!team || !team.members || !team.members[memberIndex]) return;

  const m = team.members[memberIndex];
  const curMode = m.mode || (memberIndex === 0 ? 'normal' : 'agentic');
  const newMode = (curMode === 'agentic') ? 'normal' : 'agentic';
  m.mode = newMode;

  try {
    const res = await fetch('/api/ui/multi-agent-teams', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'save',
        id: team.id,
        name: team.name,
        workflow: team.workflow,
        enabled: team.enabled !== false,
        members: team.members
      })
    });
    const data = await res.json();
    if (res.ok) {
      currentConfig = data.config;
      renderTeamsLane();
      const modeLabel = newMode === 'agentic' ? '⚡ Agentic' : '💡 Normal';
      showToast(`${team.name || tId} ➔ ${m.role || `Step #${memberIndex+1}`}: switched to ${modeLabel}`);
    } else {
      // Revert in memory if failed
      m.mode = curMode;
      showToast(data.message || 'Failed to switch member mode', true);
    }
  } catch (e) {
    m.mode = curMode;
    showToast(`Error switching mode: ${e.message}`, true);
  }
}
