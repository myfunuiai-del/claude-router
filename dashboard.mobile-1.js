/**
 * C-Router Mobile Navigation, Drawer, Radial Dial & Bottom Sheet Controller
 * Zero-Feature-Loss Mobile Ergonomics Layer
 */

let activeMobileLane = 'routed';

// Side Drawer Controls
function openMobileDrawer() {
  syncMobileDashboardUI();
  const drawer = document.getElementById('mobile-drawer');
  const backdrop = document.getElementById('mobile-drawer-backdrop');
  if (drawer && backdrop) {
    drawer.classList.add('is-open');
    backdrop.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  }
}

function closeMobileDrawer() {
  const drawer = document.getElementById('mobile-drawer');
  const backdrop = document.getElementById('mobile-drawer-backdrop');
  if (drawer && backdrop) {
    drawer.classList.remove('is-open');
    backdrop.classList.remove('is-open');
    document.body.style.overflow = '';
  }
}

// Mobile Pill Tab & Lane Switcher
function switchMobileLane(lane) {
  activeMobileLane = lane || 'routed';
  try { localStorage.setItem('crouter_active_lane', activeMobileLane); } catch (e) {}

  // Update Pill Tabs
  document.querySelectorAll('.mobile-pill-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.lane === activeMobileLane);
  });

  // Update Drawer Nav Active
  const navMap = {
    routed: 'drawer-nav-routed',
    unrouted: 'drawer-nav-unrouted',
    multiagent: 'drawer-nav-teams'
  };
  document.querySelectorAll('.drawer-nav-item').forEach(el => el.classList.remove('active'));
  if (navMap[activeMobileLane]) {
    const activeNav = document.getElementById(navMap[activeMobileLane]);
    if (activeNav) activeNav.classList.add('active');
  }

  // Toggle visibility classes (CSS only applies these on mobile <= 768px)
  const laneRouted = document.getElementById('lane-routed');
  const laneUnrouted = document.getElementById('lane-unrouted');
  const laneTeams = document.getElementById('lane-multiagent');
  const lockPanel = document.getElementById('account-lock-panel');
  const keyPanel = document.getElementById('quick-key-panel');

  if (laneRouted) laneRouted.classList.toggle('mobile-lane-active', activeMobileLane === 'routed');
  if (laneUnrouted) laneUnrouted.classList.toggle('mobile-lane-active', activeMobileLane === 'unrouted');
  if (laneTeams) laneTeams.classList.toggle('mobile-lane-active', activeMobileLane === 'multiagent');
  if (lockPanel) lockPanel.classList.toggle('mobile-lane-active', activeMobileLane === 'lock');
  if (keyPanel) keyPanel.classList.toggle('mobile-lane-active', activeMobileLane === 'keys');
}

// Close all open modals & overlays cleanly before switching views/actions
function closeAllOverlaysAndModals() {
  closeRadialDial();
  closeMobileDrawer();
  closeServerBottomSheet();

  const closeFns = [
    'closeServerModal',
    'closeTeamModal',
    'closeLogsModal',
    'closeBackupModal',
    'closeModelsModal',
    'closeTraceModal',
    'closePlaygroundModal',
    'closeRedirectionModal',
    'closeAccountModelPicker'
  ];
  closeFns.forEach(fn => {
    if (typeof window[fn] === 'function') {
      try { window[fn](); } catch (e) {}
    }
  });
}

// Unified Radial Action Handler (always closes previous modal/page first)
function handleRadialAction(action) {
  closeAllOverlaysAndModals();

  if (action === 'key') {
    if (typeof window.switchMainTab === 'function') window.switchMainTab('console');
    switchMobileLane('keys');
    updateBottomBar('routes');
    focusQuickKeyInput();
  } else if (action === 'server') {
    if (typeof window.openServerModal === 'function') window.openServerModal();
  } else if (action === 'lock') {
    if (typeof window.switchMainTab === 'function') window.switchMainTab('console');
    switchMobileLane('lock');
    updateBottomBar('routes');
    const lockPanel = document.getElementById('account-lock-panel');
    if (lockPanel) lockPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else if (action === 'logs') {
    if (typeof window.openLogsModal === 'function') window.openLogsModal();
  }
}

// Radial Speed Dial Controls
function toggleRadialDial() {
  const wrap = document.getElementById('radial-dial-wrap');
  const btn = document.getElementById('radial-fab-btn');
  const backdrop = document.getElementById('radial-backdrop');
  if (!wrap || !btn) return;

  if (wrap.classList.contains('is-open')) {
    closeRadialDial();
  } else {
    wrap.classList.add('is-open');
    btn.classList.add('is-active');
    if (backdrop) backdrop.classList.add('is-open');
  }
}

function closeRadialDial() {
  const wrap = document.getElementById('radial-dial-wrap');
  const btn = document.getElementById('radial-fab-btn');
  const backdrop = document.getElementById('radial-backdrop');
  if (wrap) wrap.classList.remove('is-open');
  if (btn) btn.classList.remove('is-active');
  if (backdrop) backdrop.classList.remove('is-open');
}

// Bottom Bar Active Item Switcher
function updateBottomBar(tabName) {
  document.querySelectorAll('.bottom-bar-item').forEach(el => el.classList.remove('active'));
  if (tabName === 'routes' || tabName === 'console') {
    const target = (activeMobileLane === 'multiagent') ? 'bottom-bar-teams' : 'bottom-bar-routes';
    const el = document.getElementById(target);
    if (el) el.classList.add('active');
  } else if (tabName === 'teams') {
    const el = document.getElementById('bottom-bar-teams');
    if (el) el.classList.add('active');
  } else if (tabName === 'live') {
    const el = document.getElementById('bottom-bar-live');
    if (el) el.classList.add('active');
  } else if (tabName === 'usage') {
    const el = document.getElementById('bottom-bar-usage');
    if (el) el.classList.add('active');
  }
}

// Quick Key Focus Helper
function focusQuickKeyInput() {
  setTimeout(() => {
    const input = document.getElementById('new-key-val');
    if (input) {
      input.focus();
      input.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, 80);
}

// Sync Mobile Header, Summary Card, Counts & Drawer Switches with Live State
function syncMobileDashboardUI() {
  const activeServer = document.getElementById('active-server');
  const activeModel = document.getElementById('active-model');
  const activeAccount = document.getElementById('active-account');

  const hdrServer = document.getElementById('mobile-header-server');
  const hdrModel = document.getElementById('mobile-header-model');
  const hdrModelBox = document.getElementById('mobile-header-model-box');
  const sumModel = document.getElementById('mobile-sum-model');
  const sumAccount = document.getElementById('mobile-sum-account');

  if (hdrServer && activeServer) hdrServer.textContent = activeServer.textContent || 'None';
  if (sumModel && activeModel) sumModel.textContent = activeModel.textContent || 'None';
  if (sumAccount && activeAccount) sumAccount.textContent = activeAccount.textContent || '#1';
  if (hdrModel && activeModel) {
    const modelText = (activeModel.textContent || 'None').trim();
    if (hdrModel.textContent !== modelText) {
      hdrModel.classList.remove('is-marquee');
      hdrModel.textContent = modelText;
    }
    if (hdrModelBox) {
      requestAnimationFrame(() => {
        hdrModel.classList.remove('is-marquee');
        hdrModelBox.classList.remove('has-marquee');
        if (hdrModel.scrollWidth > hdrModelBox.clientWidth - 8) {
          hdrModel.classList.add('is-marquee');
          hdrModelBox.classList.add('has-marquee');
        }
      });
    }
  }

  // Sync Recovery
  const recBtn = document.getElementById('recovery-toggle-btn');
  const recOn = recBtn ? recBtn.classList.contains('is-on') : true;
  const sumRec = document.getElementById('mobile-sum-recovery');
  const drwRec = document.getElementById('drawer-switch-recovery');
  if (sumRec) {
    sumRec.textContent = recOn ? 'ACTIVE' : 'OFF';
    sumRec.classList.toggle('is-off', !recOn);
  }
  if (drwRec) drwRec.classList.toggle('is-on', recOn);

  // Sync Signature
  const sigBtn = document.getElementById('signature-toggle-btn');
  const sigOn = sigBtn ? sigBtn.classList.contains('is-on') : true;
  const drwSig = document.getElementById('drawer-switch-signature');
  if (drwSig) drwSig.classList.toggle('is-on', sigOn);

  // Sync Account Lock
  const lockBtn = document.getElementById('account-lock-toggle-btn');
  const lockOn = lockBtn ? lockBtn.classList.contains('is-on') : false;
  const drwLock = document.getElementById('drawer-switch-lock');
  if (drwLock) drwLock.classList.toggle('is-on', lockOn);

  // Sync Counts from currentConfig if available
  if (typeof currentConfig !== 'undefined' && currentConfig) {
    const routedCount = (currentConfig.routed_providers || []).length;
    const standbyCount = (currentConfig.unrouted_providers || []).length;
    const teamsCount = Object.keys(currentConfig.multi_agent_teams || {}).length;

    const elDR = document.getElementById('drawer-count-routed');
    const elDS = document.getElementById('drawer-count-standby');
    const elDT = document.getElementById('drawer-count-teams');
    const elPS = document.getElementById('mobile-pill-standby-count');
    const elPT = document.getElementById('mobile-pill-teams-count');

    if (elDR) elDR.textContent = routedCount;
    if (elDS) elDS.textContent = standbyCount;
    if (elDT) elDT.textContent = teamsCount;
    if (elPS) elPS.textContent = standbyCount;
    if (elPT) elPT.textContent = teamsCount;
  }
}

// Bottom Sheet Controller (SVG Demo 3 Style)
let currentSheetServerId = null;

function openServerBottomSheet(serverId) {
  currentSheetServerId = serverId;
  const p = (typeof currentConfig !== 'undefined' && currentConfig && currentConfig.providers)
    ? currentConfig.providers[serverId]
    : null;
  const routedList = (typeof currentConfig !== 'undefined' && currentConfig && currentConfig.routed_providers)
    ? currentConfig.routed_providers
    : [];
  const isRouted = routedList.includes(serverId);
  const prioIndex = routedList.indexOf(serverId);
  const isEnabled = p ? (p.enabled !== false) : true;

  const sheet = document.getElementById('server-bottom-sheet');
  const backdrop = document.getElementById('server-bottom-sheet-backdrop');
  const nameEl = document.getElementById('sheet-server-name');
  const subEl = document.getElementById('sheet-server-subtitle');
  const avatarEl = document.getElementById('sheet-server-avatar');
  const statusEl = document.getElementById('sheet-metric-status');
  const protoEl = document.getElementById('sheet-metric-proto');
  const countsEl = document.getElementById('sheet-metric-counts');
  const laneIcon = document.getElementById('sheet-lane-icon');
  const laneText = document.getElementById('sheet-lane-text');
  const btnUp = document.getElementById('sheet-btn-move-up');
  const btnDown = document.getElementById('sheet-btn-move-down');

  if (nameEl) nameEl.textContent = (p && p.name) ? p.name : serverId;
  if (subEl) {
    subEl.textContent = isRouted
      ? `Priority #${prioIndex + 1} · Active Pipeline`
      : 'Standby / On-Demand Pool';
  }
  if (avatarEl) avatarEl.textContent = isRouted ? '⚡' : '💤';

  if (statusEl) {
    statusEl.textContent = isEnabled ? (isRouted ? 'LIVE' : 'IDLE') : 'OFF';
    statusEl.className = 'sheet-metric-val ' + (isEnabled ? (isRouted ? 'is-green' : 'is-blue') : 'is-red');
  }
  if (protoEl) protoEl.textContent = (p && p.type) ? p.type.toUpperCase() : 'ANTHROPIC';
  if (countsEl) {
    const mLen = (p && p.models) ? p.models.length : 0;
    const kLen = (p && p.keys) ? p.keys.length : 0;
    countsEl.textContent = `${mLen} / ${kLen}`;
  }

  if (laneIcon && laneText) {
    if (isRouted) {
      laneIcon.textContent = '💤';
      laneText.textContent = 'Demote to Standby Pool';
    } else {
      laneIcon.textContent = '⚡';
      laneText.textContent = 'Promote to Active Pipeline';
    }
  }

  if (btnUp) btnUp.disabled = !isRouted || prioIndex <= 0;
  if (btnDown) btnDown.disabled = !isRouted || prioIndex >= routedList.length - 1;

  if (sheet && backdrop) {
    sheet.classList.add('is-open');
    backdrop.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  }
}

function closeServerBottomSheet() {
  currentSheetServerId = null;
  const sheet = document.getElementById('server-bottom-sheet');
  const backdrop = document.getElementById('server-bottom-sheet-backdrop');
  if (sheet) sheet.classList.remove('is-open');
  if (backdrop) backdrop.classList.remove('is-open');
  document.body.style.overflow = '';
}

function sheetAction(action) {
  const id = currentSheetServerId;
  closeServerBottomSheet();
  if (!id) return;

  switch (action) {
    case 'moveUp':
      if (typeof window.moveCardUp === 'function') window.moveCardUp(id);
      break;
    case 'moveDown':
      if (typeof window.moveCardDown === 'function') window.moveCardDown(id);
      break;
    case 'test':
      if (typeof window.testModels === 'function') {
        const card = document.getElementById(`server-card-${id}`);
        if (card && !card.classList.contains('expanded')) card.classList.add('expanded');
        window.testModels(id);
      }
      break;
    case 'toggleLane':
      if (typeof window.moveLaneQuick === 'function') window.moveLaneQuick(id);
      break;
    case 'edit':
      if (typeof window.openServerModal === 'function') window.openServerModal(id);
      break;
    case 'delete':
      if (typeof window.openConfirmDelete === 'function') window.openConfirmDelete(id);
      break;
  }
}

// Initialize hooks and observers once DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  const originalSwitch = window.switchMainTab;
  if (typeof originalSwitch === 'function') {
    window.switchMainTab = function(tabName) {
      try { localStorage.setItem('crouter_active_tab', tabName); } catch (e) {}
      originalSwitch(tabName);
      updateBottomBar(tabName);
    };
  }

  // Observe key status elements to keep mobile UI synced automatically
  const observeIds = ['active-server', 'active-model', 'active-account', 'recovery-toggle-btn', 'signature-toggle-btn', 'account-lock-toggle-btn'];
  const observer = new MutationObserver(() => syncMobileDashboardUI());
  observeIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) observer.observe(el, { childList: true, attributes: true, subtree: true, characterData: true });
  });

  // Restore last active tab & mobile lane across page reloads
  let savedTab = 'console';
  let savedLane = 'routed';
  try {
    savedTab = localStorage.getItem('crouter_active_tab') || 'console';
    savedLane = localStorage.getItem('crouter_active_lane') || 'routed';
  } catch (e) {}

  switchMobileLane(savedLane);
  if (typeof window.switchMainTab === 'function') {
    window.switchMainTab(savedTab);
  } else {
    updateBottomBar(savedTab === 'console' ? (savedLane === 'multiagent' ? 'teams' : 'routes') : savedTab);
  }
  syncMobileDashboardUI();
});

// Close overlays on ESC
window.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    closeMobileDrawer();
    closeRadialDial();
    closeServerBottomSheet();
  }
});

// Horizontal Swipe Navigation between Mobile Pill Tabs (Pipelines <-> Standby <-> Multi-Agent <-> Keys & Lock)
(function initMobileTabSwipe() {
  const LANE_ORDER = ['routed', 'unrouted', 'multiagent', 'lock', 'keys'];
  let touchStartX = 0;
  let touchStartY = 0;
  let touchValid = false;

  document.addEventListener('touchstart', function(e) {
    if (window.innerWidth > 768) return;
    if (!e.touches || e.touches.length !== 1) return;

    const viewConsole = document.getElementById('view-console');
    if (!viewConsole || viewConsole.style.display === 'none') return;

    // Ignore if any overlay/modal is open
    if (document.querySelector('.modal.active, .mobile-drawer.is-open, .mobile-bottom-sheet.is-open, .radial-dial-wrap.is-open')) {
      touchValid = false;
      return;
    }

    // Ignore touches on drag handles, inputs, selects, or horizontal pill strip itself
    const target = e.target;
    if (target && target.closest('.drag-handle, input, select, textarea, .mobile-pill-tabs, .sticky-bottom-bar')) {
      touchValid = false;
      return;
    }

    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
    touchValid = true;
  }, { passive: true });

  document.addEventListener('touchend', function(e) {
    if (!touchValid || !e.changedTouches || e.changedTouches.length !== 1) return;
    touchValid = false;

    const dx = e.changedTouches[0].clientX - touchStartX;
    const dy = e.changedTouches[0].clientY - touchStartY;

    // Require clear horizontal swipe (at least 55px and clearly more horizontal than vertical)
    if (Math.abs(dx) < 55 || Math.abs(dx) < Math.abs(dy) * 1.6) return;

    const currentIdx = LANE_ORDER.indexOf(activeMobileLane);
    if (currentIdx === -1) return;

    const nextIdx = dx < 0 ? currentIdx + 1 : currentIdx - 1;
    if (nextIdx < 0 || nextIdx >= LANE_ORDER.length) return;

    const nextLane = LANE_ORDER[nextIdx];
    switchMobileLane(nextLane);
    updateBottomBar(nextLane === 'multiagent' ? 'teams' : 'routes');

    const activePill = document.querySelector(`.mobile-pill-tab[data-lane="${nextLane}"]`);
    if (activePill) {
      activePill.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    }
  }, { passive: true });
})();

// ========================================================
// C-ROUTER CUTE INTERACTIVE ROBOT CONTROLLER (60FPS GPU)
// ========================================================
(function initCrouterBot() {
  const TAB_IDS = {
    routes: 'bottom-bar-routes',
    live: 'bottom-bar-live',
    teams: 'bottom-bar-teams',
    usage: 'bottom-bar-usage'
  };

  let currentTab = 'routes';
  let currentX = 0;
  let currentY = 0;
  let animFrameId = null;
  let animToken = 0;

  function getTabCenterX(tabKey) {
    const bar = document.getElementById('sticky-bottom-bar');
    const tabEl = document.getElementById(TAB_IDS[tabKey] || TAB_IDS.routes);
    if (!bar || !tabEl) return 45;
    const barRect = bar.getBoundingClientRect();
    const tabRect = tabEl.getBoundingClientRect();
    return (tabRect.left - barRect.left) + (tabRect.width / 2);
  }

  function setBotTransform(x, y) {
    currentX = x;
    currentY = y;
    const bot = document.getElementById('crouter-bot');
    if (bot) {
      bot.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;
    }
  }

  function setBotState(state) {
    const bot = document.getElementById('crouter-bot');
    if (!bot) return;
    bot.classList.remove('is-sitting', 'is-standing', 'is-walking', 'is-igniting', 'is-flying', 'is-teetering', 'is-falling', 'is-flying-back', 'is-turn-side', 'is-turn-squish', 'is-turn-unsquish');
    if (state) bot.classList.add(state);
  }

  // mode: 'walk', 'easeIn', 'thrust' (swaying jetpack flight), 'hover' (1s floating bob), 'land'
  function animateSegment(fromX, toX, fromY, toY, duration, mode, token) {
    return new Promise(resolve => {
      const start = performance.now();
      const steps = Math.max(1, Math.round(duration / 360));
      function step(now) {
        if (token !== animToken) { resolve(false); return; }
        const t = Math.min(1, (now - start) / duration);
        let prog = t;
        let swayY = 0;

        if (mode === 'walk') {
          prog = t + 0.025 * Math.sin(t * steps * Math.PI * 2);
          prog = Math.max(0, Math.min(1, prog));
        } else if (mode === 'easeIn') {
          prog = t * t * t;
        } else if (mode === 'hover') {
          // Gentle floating up-and-down bob in mid-air
          swayY = Math.sin(t * Math.PI * 4) * 5.5;
        } else if (mode === 'thrust') {
          // Smooth jetpack acceleration + realistic swaying/bobbing arc in air
          prog = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
          swayY = Math.sin(t * Math.PI * 3) * 4.5 - Math.sin(t * Math.PI) * 6;
        } else if (mode === 'land') {
          prog = 1 - Math.pow(1 - t, 3);
        } else {
          prog = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        }

        const x = fromX + (toX - fromX) * prog;
        const y = fromY + (toY - fromY) * prog + swayY;
        setBotTransform(x, y);
        if (t < 1) {
          animFrameId = requestAnimationFrame(step);
        } else {
          resolve(true);
        }
      }
      animFrameId = requestAnimationFrame(step);
    });
  }

  async function moveBotToTab(targetTab) {
    const bot = document.getElementById('crouter-bot');
    if (!bot || !TAB_IDS[targetTab]) return;

    const bar = document.getElementById('sticky-bottom-bar');
    if (!bar || bar.getBoundingClientRect().width === 0) return;

    const targetX = getTabCenterX(targetTab);
    if (Math.abs(targetX - currentX) < 4 && Math.abs(currentY) < 4) {
      currentTab = targetTab;
      setBotState('is-sitting');
      return;
    }

    currentTab = targetTab;
    const token = ++animToken;
    if (animFrameId) cancelAnimationFrame(animFrameId);

    const goingRight = targetX > currentX;
    const barW = bar.clientWidth || 390;
    const centerX = barW / 2;
    const gapHalf = 46;
    const totalDist = Math.abs(targetX - currentX);
    const crossesCenter = (currentX < centerX && targetX > centerX) || (currentX > centerX && targetX < centerX);

    // Case 1: Already in mid-air or below screen -> never teleport! Smoothly fly from (currentX, currentY)
    if (Math.abs(currentY) > 4) {
      bot.classList.toggle('face-left', !goingRight);
      setBotState(currentY > 10 ? 'is-flying-back' : 'is-flying');
      const peakY = crossesCenter ? -46 : -34;
      const okFly = await animateSegment(currentX, targetX, currentY, peakY, Math.max(480, totalDist * 2.8), 'thrust', token);
      if (!okFly) return;
      bot.classList.remove('face-left');
      setBotState('is-standing');
      const okLand = await animateSegment(currentX, targetX, currentY, 0, 280, 'land', token);
      if (!okLand) return;
      await new Promise(r => setTimeout(r, 220));
      if (token !== animToken) return;
      setBotState('is-sitting');
      return;
    }

    // 1. Stand up
    setBotState('is-standing');
    await new Promise(r => setTimeout(r, 150));
    if (token !== animToken) return;

    // 2. Turn left or right toward target
    bot.classList.toggle('face-left', !goingRight);
    const useJetpack = crossesCenter || totalDist > 120;

    if (useJetpack) {
      // Walk slowly step-by-step up to launch point if crossing center
      if (crossesCenter) {
        const edgeBefore = goingRight ? (centerX - gapHalf) : (centerX + gapHalf);
        if ((goingRight && currentX < edgeBefore) || (!goingRight && currentX > edgeBefore)) {
          setBotState('is-walking');
          const dWalk1 = Math.abs(edgeBefore - currentX);
          const ok1 = await animateSegment(currentX, edgeBefore, currentY, 0, Math.max(280, dWalk1 * 10), 'walk', token);
          if (!ok1) return;
        }
      }

      // Compute overshoot landing spot
      const overshootPx = Math.min(34, Math.max(20, totalDist * 0.14));
      let landX = goingRight ? (targetX + overshootPx) : (targetX - overshootPx);
      landX = Math.max(22, Math.min(barW - 22, landX));
      if (goingRight && targetX > centerX) landX = Math.max(centerX + gapHalf, landX);
      if (!goingRight && targetX < centerX) landX = Math.min(centerX - gapHalf, landX);

      // Phase A: 1-second preparation reaction & thruster ignition on ground
      setBotState('is-igniting');
      await new Promise(r => setTimeout(r, 900));
      if (token !== animToken) return;

      // Phase B: Slow vertical liftoff
      setBotState('is-flying');
      const peakY = crossesCenter ? -46 : -34;
      const okLift = await animateSegment(currentX, currentX, currentY, peakY, 380, 'easeIn', token);
      if (!okLift) return;

      // Phase C: 1-second mid-air floating hover bob in place
      const okHover = await animateSegment(currentX, currentX, currentY, peakY, 950, 'hover', token);
      if (!okHover) return;

      // Phase D: Realistic swaying jetpack flight across distance (overshooting target!)
      const cruiseEndX = landX - (goingRight ? 8 : -8);
      const cruiseDist = Math.abs(cruiseEndX - currentX);
      const okCruise = await animateSegment(currentX, cruiseEndX, currentY, peakY, Math.max(460, Math.min(780, cruiseDist * 3.1)), 'thrust', token);
      if (!okCruise) return;

      // Phase E: Smooth touchdown to ground
      const okLand = await animateSegment(currentX, landX, currentY, 0, 260, 'land', token);
      if (!okLand) return;

      // Phase F: Turn around & walk slowly back step-by-step to exact tab!
      if (Math.abs(targetX - currentX) > 3) {
        bot.classList.toggle('face-left', targetX < currentX);
        setBotState('is-walking');
        const dBack = Math.abs(targetX - currentX);
        const okBack = await animateSegment(currentX, targetX, currentY, 0, Math.max(280, dBack * 11), 'walk', token);
        if (!okBack) return;
      }
    } else {
      // Short distance on same side: walk slowly step-by-step
      setBotState('is-walking');
      const ok = await animateSegment(currentX, targetX, currentY, 0, Math.max(340, totalDist * 10.5), 'walk', token);
      if (!ok) return;
    }

    // 4. Face front & sit down on active tab with dangling legs
    bot.classList.remove('face-left');
    setBotState('is-sitting');
  }

  window.triggerBotReaction = function() {
    const bot = document.getElementById('crouter-bot');
    if (!bot) return;
    bot.classList.remove('is-dropping', 'is-waving');
    void bot.offsetWidth;
    bot.classList.add('is-dropping', 'is-waving');
    setTimeout(() => bot.classList.remove('is-dropping', 'is-waving'), 980);
  };

  window.triggerBotClap = function() {
    const bot = document.getElementById('crouter-bot');
    if (!bot || !bot.classList.contains('is-sitting')) return;
    bot.classList.remove('is-clapping');
    void bot.offsetWidth;
    bot.classList.add('is-clapping');
    setTimeout(() => bot.classList.remove('is-clapping'), 1000);
  };

  // Periodic friendly one-hand Hi-Five wave while sitting idle
  setInterval(() => {
    const bot = document.getElementById('crouter-bot');
    if (bot && bot.classList.contains('is-sitting') && !bot.classList.contains('is-clapping') && !isDoingFallSequence) {
      bot.classList.remove('is-waving');
      void bot.offsetWidth;
      bot.classList.add('is-waving');
      setTimeout(() => bot.classList.remove('is-waving'), 980);
    }
  }, 8500);

  // Clap automatically on Save / OK / Done / Add / Confirm actions
  document.addEventListener('click', (e) => {
    const btn = e.target && e.target.closest('button, input[type="submit"]');
    if (!btn) return;
    const txt = (btn.textContent || btn.value || '').trim().toLowerCase();
    if (/\b(save|ok|done|confirm|apply|add|export|import)\b/.test(txt)) {
      setTimeout(() => window.triggerBotClap(), 180);
    }
  });

  // Hook into updateBottomBar so any tab click or swipe moves the bot
  const origUpdateBottomBar = window.updateBottomBar;
  window.updateBottomBar = function(tabName) {
    if (typeof origUpdateBottomBar === 'function') origUpdateBottomBar(tabName);
    let mapped = 'routes';
    if (tabName === 'live') mapped = 'live';
    else if (tabName === 'teams' || (tabName === 'console' && activeMobileLane === 'multiagent')) mapped = 'teams';
    else if (tabName === 'usage') mapped = 'usage';
    moveBotToTab(mapped);
  };

  // Dramatic teeter ("aa pore gelam!") -> fast fall -> slow back-view jetpack rise -> realistic smooth turn -> soft stand -> sit
  let isDoingFallSequence = false;
  let lastKbFallTime = 0;

  async function triggerKeyboardFallAndReturn() {
    const bot = document.getElementById('crouter-bot');
    const bar = document.getElementById('sticky-bottom-bar');
    const now = Date.now();
    if (!bot || !bar || bar.getBoundingClientRect().width === 0 || isDoingFallSequence) return;
    if (now - lastKbFallTime < 1500) return;
    lastKbFallTime = now;

    // 60% chance to fall off-screen; 40% chance to catch balance with a cute wobble!
    if (Math.random() >= 0.60) {
      window.triggerBotReaction();
      return;
    }

    isDoingFallSequence = true;
    const token = ++animToken;
    if (animFrameId) cancelAnimationFrame(animFrameId);
    bot.classList.remove('face-left');

    // 1. Teeter & wobble on edge ("aa pore gelam pore gelam!")
    setBotState('is-teetering');
    await new Promise(r => setTimeout(r, 1200));
    if (token !== animToken) { isDoingFallSequence = false; return; }

    // 2. Drop fast off the bottom of the screen!
    setBotState('is-falling');
    const okFall = await animateSegment(currentX, currentX, currentY, 165, 380, 'easeIn', token);
    if (!okFall) { isDoingFallSequence = false; return; }

    await new Promise(r => setTimeout(r, 240));
    if (token !== animToken) { isDoingFallSequence = false; return; }

    // 3. Fly UP SLOWLY showing BACK VIEW + jetpack fire, hovering slightly above tab
    setBotState('is-flying-back');
    const okReturn = await animateSegment(currentX, currentX, 165, -24, 1400, 'land', token);
    if (!okReturn) { isDoingFallSequence = false; return; }

    // 4. Realistic smooth turn above the tab: Back -> Side -> Front
    bot.classList.add('is-turn-squish');
    await new Promise(r => setTimeout(r, 160));
    if (token !== animToken) { isDoingFallSequence = false; return; }

    setBotState('is-turn-side');
    bot.classList.add('is-turn-unsquish');
    await new Promise(r => setTimeout(r, 180));
    if (token !== animToken) { isDoingFallSequence = false; return; }

    bot.classList.remove('is-turn-unsquish');
    bot.classList.add('is-turn-squish');
    await new Promise(r => setTimeout(r, 160));
    if (token !== animToken) { isDoingFallSequence = false; return; }

    // 5. Face front, descend softly onto the ledge, and stand gently
    setBotState('is-standing');
    bot.classList.add('is-turn-unsquish');
    const okTouchdown = await animateSegment(currentX, currentX, -24, 0, 320, 'land', token);
    bot.classList.remove('is-turn-unsquish');
    if (!okTouchdown) { isDoingFallSequence = false; return; }

    await new Promise(r => setTimeout(r, 320));
    isDoingFallSequence = false;
    if (token !== animToken) return;
    setBotState('is-sitting');
  }

  // When keyboard closes and the bottom bar drops back down, bot floats & flies gently back onto the active tab
  async function triggerKeyboardCloseFlySettle() {
    const bot = document.getElementById('crouter-bot');
    const bar = document.getElementById('sticky-bottom-bar');
    if (!bot || !bar || bar.getBoundingClientRect().width === 0 || isDoingFallSequence) return;

    isDoingFallSequence = true;
    const token = ++animToken;
    if (animFrameId) cancelAnimationFrame(animFrameId);
    bot.classList.remove('face-left');

    const targetX = getTabCenterX(currentTab);
    setBotState('is-flying');
    // Pop up into mid-air as the bar drops away, then sway-fly down to sit
    const okUp = await animateSegment(currentX, currentX, currentY, -38, 280, 'land', token);
    if (!okUp) { isDoingFallSequence = false; return; }

    const okHover = await animateSegment(currentX, targetX, -38, -28, 520, 'thrust', token);
    if (!okHover) { isDoingFallSequence = false; return; }

    setBotState('is-standing');
    const okSettle = await animateSegment(currentX, targetX, -28, 0, 320, 'land', token);
    if (!okSettle) { isDoingFallSequence = false; return; }

    await new Promise(r => setTimeout(r, 240));
    isDoingFallSequence = false;
    if (token !== animToken) return;
    setBotState('is-sitting');
  }

  document.addEventListener('focusin', (e) => {
    if (window.innerWidth > 768) return;
    const tag = e.target && e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') {
      triggerKeyboardFallAndReturn();
    }
  });

  if (window.visualViewport) {
    let lastH = window.visualViewport.height;
    const syncBarToKeyboard = () => {
      const bar = document.getElementById('sticky-bottom-bar');
      const radial = document.getElementById('radial-dial-wrap');
      const vv = window.visualViewport;
      const kbOffset = Math.max(0, Math.round(window.innerHeight - vv.height - vv.offsetTop));
      if (bar) bar.style.bottom = kbOffset + 'px';
      if (radial) radial.style.bottom = `calc(var(--mobile-bottom-height) + 8px + ${kbOffset}px)`;

      if (lastH - vv.height > 100) {
        triggerKeyboardFallAndReturn();
      } else if (vv.height - lastH > 100) {
        triggerKeyboardCloseFlySettle();
      }
      lastH = vv.height;
    };
    window.visualViewport.addEventListener('resize', syncBarToKeyboard);
    window.visualViewport.addEventListener('scroll', syncBarToKeyboard);
  }

  window.addEventListener('resize', () => {
    if (isDoingFallSequence) return;
    moveBotToTab(currentTab);
  });

  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
      let initTab = 'routes';
      try {
        const sTab = localStorage.getItem('crouter_active_tab') || 'console';
        const sLane = localStorage.getItem('crouter_active_lane') || 'routed';
        if (sTab === 'live') initTab = 'live';
        else if (sTab === 'usage') initTab = 'usage';
        else if (sLane === 'multiagent') initTab = 'teams';
      } catch (e) {}
      currentTab = initTab;
      currentX = getTabCenterX(initTab);
      setBotTransform(currentX, 0);
      setBotState('is-sitting');
    }, 60);
  });
})();

// ========================================================
// GLOBAL CUSTOM MOBILE <SELECT> PICKER SHEET
// ========================================================
(function initCustomSelectSheet() {
  let activeSelectEl = null;

  window.closeCustomSelectSheet = function() {
    activeSelectEl = null;
    const sheet = document.getElementById('custom-select-sheet');
    const backdrop = document.getElementById('custom-select-backdrop');
    if (sheet) sheet.classList.remove('is-open');
    if (backdrop) backdrop.classList.remove('is-open');
  };

  window.filterCustomSelectOptions = function(query) {
    const q = (query || '').trim().toLowerCase();
    document.querySelectorAll('#custom-select-list .custom-select-option').forEach(btn => {
      const txt = (btn.dataset.label || '').toLowerCase();
      btn.style.display = (!q || txt.includes(q)) ? 'flex' : 'none';
    });
  };

  function openCustomSelectSheet(selectEl) {
    activeSelectEl = selectEl;
    const sheet = document.getElementById('custom-select-sheet');
    const backdrop = document.getElementById('custom-select-backdrop');
    const titleEl = document.getElementById('custom-select-title');
    const searchEl = document.getElementById('custom-select-search');
    const listEl = document.getElementById('custom-select-list');
    if (!sheet || !backdrop || !listEl) return;

    const opts = Array.from(selectEl.options || []);
    if (titleEl) {
      const lbl = selectEl.getAttribute('aria-label') || selectEl.getAttribute('title') || 'Select Option';
      titleEl.textContent = lbl;
    }

    if (searchEl) {
      searchEl.value = '';
      searchEl.style.display = opts.length > 6 ? 'block' : 'none';
    }

    listEl.innerHTML = '';
    opts.forEach(opt => {
      if (opt.disabled && !opt.value) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'custom-select-option' + (opt.value === selectEl.value ? ' is-selected' : '');
      btn.dataset.label = opt.textContent || opt.value;
      btn.innerHTML = `<span>${opt.textContent}</span>${opt.value === selectEl.value ? '<span class="custom-select-check">✓</span>' : ''}`;
      btn.onclick = () => {
        selectEl.value = opt.value;
        selectEl.dispatchEvent(new Event('change', { bubbles: true }));
        closeCustomSelectSheet();
      };
      listEl.appendChild(btn);
    });

    sheet.classList.add('is-open');
    backdrop.classList.add('is-open');
  }

  // Intercept native <select> taps on mobile to show custom dark sheet instead
  document.addEventListener('mousedown', function(e) {
    if (window.innerWidth > 768) return;
    const sel = e.target && e.target.closest('select');
    if (!sel || sel.disabled || sel.classList.contains('no-custom-select')) return;
    e.preventDefault();
    openCustomSelectSheet(sel);
  });
})();
