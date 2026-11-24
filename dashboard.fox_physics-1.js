// ========================================================
// C-ROUTER FOX-MECHA INTERACTIVE DRAG, GRAVITY PHYSICS &
// MULTI-STAGE JETPACK LANDING ENGINE
// ========================================================
(function initFoxPhysicsEngine() {
  const DRAG_THRESHOLD_PX = 6;
  let isDragging = false;
  let hasMovedBeyondThreshold = false;
  let activePointerId = null;
  let startClientX = 0;
  let startClientY = 0;
  let lastClientX = 0;
  let lastClientY = 0;
  let lastMoveTime = 0;
  let smoothVx = 0;
  let smoothVy = 0;

  let curRelX = 48;
  let curRelY = 0;
  let grabOffsetX = 0;
  let grabOffsetY = 0;

  let flightToken = 0;
  let flightRafId = null;
  let suppressNextClickUntil = 0;
  let sparkTimer = 0;

  const PHYSICS_CLASSES = [
    'is-dragged',
    'is-drag-up',
    'is-drag-down',
    'is-zero-g',
    'is-jetpack-hover',
    'is-jetpack-dive',
    'is-jetpack-brake',
    'is-soft-land'
  ];

  function getBot() {
    return document.getElementById('crouter-bot');
  }

  function getBarRect() {
    const bar = document.getElementById('sticky-bottom-bar');
    if (bar && bar.getBoundingClientRect().width > 0) {
      return bar.getBoundingClientRect();
    }
    return { left: 0, top: window.innerHeight - 60, width: window.innerWidth };
  }

  function screenToRel(sx, sy) {
    const barRect = getBarRect();
    return {
      x: sx - barRect.left,
      y: sy - (barRect.top - 33)
    };
  }

  function relToScreen(rx, ry) {
    const barRect = getBarRect();
    return {
      x: barRect.left + rx,
      y: (barRect.top - 33) + ry
    };
  }

  function clampRelToViewport(rx, ry) {
    const barRect = getBarRect();
    const minSx = 22;
    const maxSx = Math.max(40, window.innerWidth - 22);
    const minSy = 18;
    const maxSy = Math.max(60, window.innerHeight - 36);
    const sx = Math.max(minSx, Math.min(maxSx, barRect.left + rx));
    const sy = Math.max(minSy, Math.min(maxSy, (barRect.top - 33) + ry));
    return {
      x: sx - barRect.left,
      y: sy - (barRect.top - 33)
    };
  }

  function clearPhysicsClasses(bot) {
    if (!bot) return;
    PHYSICS_CLASSES.forEach(c => bot.classList.remove(c));
    const svg = bot.querySelector('.bot-svg');
    if (svg) {
      svg.style.transform = '';
      svg.style.transition = '';
    }
  }

  function applyPosition(rx, ry) {
    curRelX = rx;
    curRelY = ry;
    const bridge = window.__foxBotBridge;
    if (bridge && typeof bridge.setBotTransform === 'function') {
      bridge.setBotTransform(rx, ry);
    } else {
      const bot = getBot();
      if (!bot) return;
      if (bot.parentElement !== document.body) document.body.appendChild(bot);
      const sc = relToScreen(rx, ry);
      bot.style.transform = `translate3d(${sc.x.toFixed(1)}px, ${sc.y.toFixed(1)}px, 0)`;
    }
  }

  function setNativeState(state) {
    const bridge = window.__foxBotBridge;
    if (bridge && typeof bridge.setBotState === 'function') {
      bridge.setBotState(state);
    } else {
      const bot = getBot();
      if (!bot) return;
      bot.classList.remove('is-sitting', 'is-standing', 'is-settling', 'is-rising', 'is-walking', 'is-igniting', 'is-flying', 'is-teetering', 'is-falling', 'is-flying-back');
      if (state) bot.classList.add(state);
    }
  }

  function getActiveTabTargetX() {
    const bridge = window.__foxBotBridge;
    if (bridge && typeof bridge.getActiveTabX === 'function') {
      return bridge.getActiveTabX();
    }
    const activeItem = document.querySelector('.bottom-bar-item.active');
    const barRect = getBarRect();
    if (activeItem) {
      const r = activeItem.getBoundingClientRect();
      return (r.left - barRect.left) + r.width / 2;
    }
    return 48;
  }

  function spawnJetpackSparks(bot, count, intensity) {
    if (!bot) return;
    let layer = bot.querySelector('.fox-puppet-layer');
    if (!layer) {
      layer = document.createElement('div');
      layer.className = 'fox-puppet-layer';
      bot.appendChild(layer);
    }
    for (let i = 0; i < count; i++) {
      const sp = document.createElement('div');
      sp.className = 'fox-jet-spark';
      const spreadX = (Math.random() - 0.5) * (12 * intensity);
      const dropY = 14 + Math.random() * (18 * intensity);
      const startX = 12 + Math.random() * 10;
      sp.style.left = `${startX}px`;
      sp.style.top = `34px`;
      sp.style.setProperty('--jx', `${spreadX.toFixed(1)}px`);
      sp.style.setProperty('--jy', `${dropY.toFixed(1)}px`);
      if (intensity > 1.2) {
        sp.style.background = Math.random() > 0.4 ? '#fff3a1' : '#58a6ff';
      }
      layer.appendChild(sp);
      setTimeout(() => sp.remove(), 380);
    }
  }

  function cancelFlight() {
    flightToken++;
    if (flightRafId) {
      cancelAnimationFrame(flightRafId);
      flightRafId = null;
    }
    const bridge = window.__foxBotBridge;
    if (bridge) bridge.isPhysicsActive = false;
  }

  function animatePhase(durationMs, token, onFrame) {
    return new Promise(resolve => {
      const start = performance.now();
      function tick(now) {
        if (token !== flightToken) { resolve(false); return; }
        const t = Math.min(1, (now - start) / durationMs);
        onFrame(t, now);
        if (t < 1) {
          flightRafId = requestAnimationFrame(tick);
        } else {
          resolve(true);
        }
      }
      flightRafId = requestAnimationFrame(tick);
    });
  }

  function waitMs(ms, token) {
    return new Promise(resolve => {
      setTimeout(() => resolve(token === flightToken), ms);
    });
  }

  // ========================================================
  // MULTI-STAGE GRAVITY & JETPACK RECOVERY SEQUENCE
  // ========================================================
  async function runJetpackRecoverySequence() {
    const bot = getBot();
    if (!bot) return;
    const token = ++flightToken;
    const bridge = window.__foxBotBridge;
    if (bridge) bridge.isPhysicsActive = true;

    const svg = bot.querySelector('.bot-svg');
    const startX = curRelX;
    const startY = curRelY;
    const targetX = getActiveTabTargetX();

    // Short hop if released very close to the bottom bar
    const isHighDrop = startY < -28;

    if (isHighDrop) {
      // ------------------------------------------------------
      // PHASE 1: ZERO-GRAVITY FLOAT (~1.0s)
      // Floats weightlessly in mid-air, lies back horizontally,
      // and wiggles arms & legs cutely!
      // ------------------------------------------------------
      clearPhysicsClasses(bot);
      setNativeState(null);
      bot.classList.remove('face-left');
      bot.classList.add('is-zero-g');

      const okZeroG = await animatePhase(1020, token, (t) => {
        // Weightless sinusoidal hover right where released
        const floatY = Math.sin(t * Math.PI * 2.2) * 5.5 - Math.sin(t * Math.PI) * 4;
        const driftX = Math.sin(t * Math.PI * 1.6) * 3.5;
        applyPosition(startX + driftX, startY + floatY);
      });
      if (!okZeroG) return;

      // ------------------------------------------------------
      // PHASE 2: JETPACK IGNITION + LATERAL SWAY (~1.15s)
      // Twin-nozzle jetpack fires up from his back!
      // Doesn't drop immediately — hovers & shifts slightly
      // left and right from the jetpack thrust!
      // ------------------------------------------------------
      const hoverOriginX = curRelX;
      const hoverOriginY = curRelY;
      clearPhysicsClasses(bot);
      setNativeState('is-flying-back');
      bot.classList.add('is-jetpack-hover');
      spawnJetpackSparks(bot, 7, 1.15);

      const swayDir = targetX >= hoverOriginX ? 1 : -1;
      const okIgnite = await animatePhase(1150, token, (t, now) => {
        // Gentle lateral sway left-right from jetpack thrust
        const swayX = Math.sin(t * Math.PI * 2.5) * 18 * swayDir;
        const bobY = -Math.sin(t * Math.PI) * 10 + Math.sin(t * Math.PI * 4) * 3.5;
        const clamped = clampRelToViewport(hoverOriginX + swayX, hoverOriginY + bobY);
        applyPosition(clamped.x, clamped.y);
        if (svg) {
          const tilt = Math.cos(t * Math.PI * 2.5) * 10 * swayDir;
          svg.style.transform = `rotate(${tilt.toFixed(1)}deg)`;
        }
        if (now - sparkTimer > 110) {
          sparkTimer = now;
          spawnJetpackSparks(bot, 2, 1.0);
        }
      });
      if (!okIgnite) return;

      // ------------------------------------------------------
      // PHASE 3: SLOW INITIAL DESCENT (~0.55s)
      // Begins descending slowly while aligning horizontally
      // toward the active tab.
      // ------------------------------------------------------
      const p3StartX = curRelX;
      const p3StartY = curRelY;
      const brakeHoverY = Math.min(-42, p3StartY * 0.25);
      const slowEndY = p3StartY + (brakeHoverY - p3StartY) * 0.28;
      const slowEndX = p3StartX + (targetX - p3StartX) * 0.45;

      const okSlow = await animatePhase(560, token, (t, now) => {
        const ease = t * t * (3 - 2 * t);
        const nx = p3StartX + (slowEndX - p3StartX) * ease + Math.sin(t * Math.PI * 2) * 5;
        const ny = p3StartY + (slowEndY - p3StartY) * ease;
        applyPosition(nx, ny);
        if (svg) {
          const bank = Math.max(-14, Math.min(14, (targetX - p3StartX) * 0.06));
          svg.style.transform = `rotate(${(bank * (1 - t * 0.3)).toFixed(1)}deg)`;
        }
        if (now - sparkTimer > 120) {
          sparkTimer = now;
          spawnJetpackSparks(bot, 2, 0.9);
        }
      });
      if (!okSlow) return;

      // ------------------------------------------------------
      // PHASE 4: FAST DIVE (~0.42s)
      // Accelerates rapidly downward toward the active tab!
      // ------------------------------------------------------
      const p4StartX = curRelX;
      const p4StartY = curRelY;
      bot.classList.remove('is-jetpack-hover');
      bot.classList.add('is-jetpack-dive');

      const okDive = await animatePhase(420, token, (t, now) => {
        // Fast accelerating curve down
        const easeY = Math.pow(t, 2.1);
        const easeX = 1 - Math.pow(1 - t, 2);
        const nx = p4StartX + (targetX - p4StartX) * easeX;
        const ny = p4StartY + (brakeHoverY - p4StartY) * easeY;
        applyPosition(nx, ny);
        if (svg) {
          svg.style.transform = `scaleY(${(1 + t * 0.08).toFixed(3)}) scaleX(${(1 - t * 0.04).toFixed(3)})`;
        }
        if (now - sparkTimer > 95) {
          sparkTimer = now;
          spawnJetpackSparks(bot, 1, 0.7);
        }
      });
      if (!okDive) return;

      // ------------------------------------------------------
      // PHASE 5: BRAKING HOVER ABOVE ACTIVE TAB (~0.58s)
      // Fires bright reverse thrust right above the active tab,
      // slowing down smoothly to a gentle touchdown!
      // ------------------------------------------------------
      const p5StartX = curRelX;
      const p5StartY = curRelY;
      bot.classList.remove('is-jetpack-dive');
      bot.classList.add('is-jetpack-brake');
      spawnJetpackSparks(bot, 8, 1.5);

      const okBrake = await animatePhase(580, token, (t, now) => {
        // Cubic ease-out: fast deceleration -> super slow near 0
        const easeOut = 1 - Math.pow(1 - t, 3);
        const nx = p5StartX + (targetX - p5StartX) * easeOut;
        const ny = p5StartY + (0 - p5StartY) * easeOut;
        applyPosition(nx, ny);
        if (svg) {
          // Slight compression from braking thrust
          const compress = Math.sin(t * Math.PI) * 0.06;
          svg.style.transform = `scaleY(${(1 - compress).toFixed(3)}) scaleX(${(1 + compress * 0.7).toFixed(3)})`;
        }
        if (now - sparkTimer > 80 && t < 0.85) {
          sparkTimer = now;
          spawnJetpackSparks(bot, 3, 1.45);
        }
      });
      if (!okBrake) return;
    } else {
      // Short low-altitude jetpack hop directly to active tab
      clearPhysicsClasses(bot);
      setNativeState('is-flying-back');
      bot.classList.add('is-jetpack-brake');
      spawnJetpackSparks(bot, 5, 1.1);
      const okHop = await animatePhase(440, token, (t) => {
        const ease = 1 - Math.pow(1 - t, 3);
        const arcY = -Math.sin(t * Math.PI) * 26;
        const nx = startX + (targetX - startX) * ease;
        const ny = startY * (1 - ease) + arcY;
        applyPosition(nx, ny);
      });
      if (!okHop) return;
    }

    // ------------------------------------------------------
    // PHASE 6: SOFT TOUCHDOWN -> STAND UP -> SIT ON ACTIVE TAB
    // ------------------------------------------------------
    clearPhysicsClasses(bot);
    applyPosition(targetX, 0);
    setNativeState('is-standing');
    bot.classList.add('is-soft-land');

    if (!(await waitMs(440, token))) return;
    bot.classList.remove('is-soft-land');

    // Follow native settling -> sitting rules on the active tab!
    setNativeState('is-settling');
    if (!(await waitMs(460, token))) return;

    setNativeState('is-sitting');
    if (bridge) bridge.isPhysicsActive = false;
  }

  // ========================================================
  // POINTER / TOUCH DRAG HANDLERS
  // ========================================================
  function onPointerDown(e) {
    const bot = getBot();
    if (!bot) return;
    if (e.button !== undefined && e.button !== 0) return;

    activePointerId = e.pointerId !== undefined ? e.pointerId : 'mouse';
    isDragging = true;
    hasMovedBeyondThreshold = false;
    startClientX = e.clientX;
    startClientY = e.clientY;
    lastClientX = e.clientX;
    lastClientY = e.clientY;
    lastMoveTime = performance.now();
    smoothVx = 0;
    smoothVy = 0;

    // Read current visual position of Fox on screen
    const rect = bot.getBoundingClientRect();
    const curScreenX = rect.left + rect.width / 2;
    const curScreenY = rect.top;
    const rel = screenToRel(curScreenX, curScreenY);
    curRelX = rel.x;
    curRelY = rel.y;

    grabOffsetX = curScreenX - e.clientX;
    grabOffsetY = curScreenY - e.clientY;

    if (bot.setPointerCapture && e.pointerId !== undefined) {
      try { bot.setPointerCapture(e.pointerId); } catch (err) {}
    }
  }

  function onPointerMove(e) {
    if (!isDragging) return;
    if (activePointerId !== 'mouse' && e.pointerId !== undefined && e.pointerId !== activePointerId) return;

    const bot = getBot();
    if (!bot) return;

    const dxTotal = e.clientX - startClientX;
    const dyTotal = e.clientY - startClientY;

    if (!hasMovedBeyondThreshold) {
      if (Math.hypot(dxTotal, dyTotal) < DRAG_THRESHOLD_PX) return;
      hasMovedBeyondThreshold = true;

      // Cancel any ongoing native walk/fly or previous jetpack flight
      cancelFlight();
      const bridge = window.__foxBotBridge;
      if (bridge) {
        if (typeof bridge.cancelAnim === 'function') bridge.cancelAnim();
        bridge.isPhysicsActive = true;
      }

      clearPhysicsClasses(bot);
      setNativeState(null);
      bot.classList.remove('face-left');
      bot.classList.add('is-dragged');
    }

    if (e.cancelable) e.preventDefault();

    const now = performance.now();
    const dt = Math.max(8, now - lastMoveTime);
    const instVx = ((e.clientX - lastClientX) / dt) * 16;
    const instVy = ((e.clientY - lastClientY) / dt) * 16;
    smoothVx = smoothVx * 0.65 + instVx * 0.35;
    smoothVy = smoothVy * 0.65 + instVy * 0.35;
    lastClientX = e.clientX;
    lastClientY = e.clientY;
    lastMoveTime = now;

    // Update position clamped to viewport
    const desiredScreenX = e.clientX + grabOffsetX;
    const desiredScreenY = e.clientY + grabOffsetY;
    const rel = screenToRel(desiredScreenX, desiredScreenY);
    const clamped = clampRelToViewport(rel.x, rel.y);
    applyPosition(clamped.x, clamped.y);

    // Apply live gravity/inertia physics deformation!
    const svg = bot.querySelector('.bot-svg');
    if (svg) {
      const tiltDeg = Math.max(-28, Math.min(28, -smoothVx * 1.45));
      // Pulling up stretches Fox slightly (gravity pulls legs down); pushing down compresses slightly (air resistance)
      const stretchY = Math.max(0.91, Math.min(1.11, 1 - smoothVy * 0.008));
      const stretchX = 1 / Math.sqrt(stretchY);
      svg.style.transition = 'transform 0.06s linear';
      svg.style.transform = `rotate(${tiltDeg.toFixed(1)}deg) scaleX(${stretchX.toFixed(3)}) scaleY(${stretchY.toFixed(3)})`;
    }

    // Toggle directional gravity limb classes (upward pull vs downward drop)
    if (smoothVy < -1.2) {
      bot.classList.add('is-drag-up');
      bot.classList.remove('is-drag-down');
    } else if (smoothVy > 1.2) {
      bot.classList.add('is-drag-down');
      bot.classList.remove('is-drag-up');
    } else {
      bot.classList.remove('is-drag-up', 'is-drag-down');
    }
  }

  function onPointerUp(e) {
    if (!isDragging) return;
    if (activePointerId !== 'mouse' && e.pointerId !== undefined && e.pointerId !== activePointerId) return;

    const bot = getBot();
    isDragging = false;
    activePointerId = null;

    if (bot && bot.releasePointerCapture && e.pointerId !== undefined) {
      try { bot.releasePointerCapture(e.pointerId); } catch (err) {}
    }

    if (!hasMovedBeyondThreshold) return;

    // Suppress the synthetic click so tapping/chat doesn't fire after dragging
    suppressNextClickUntil = performance.now() + 350;
    hasMovedBeyondThreshold = false;

    // Kick off the Zero-G -> Jetpack -> Slow/Fast Descent -> Brake -> Stand -> Sit sequence!
    runJetpackRecoverySequence();
  }

  function attachFoxDragListeners() {
    const bot = getBot();
    if (!bot || bot.dataset.foxPhysicsBound === '1') return;
    bot.dataset.foxPhysicsBound = '1';
    bot.style.touchAction = 'none';

    bot.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('pointermove', onPointerMove, { passive: false });
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);

    // Block click propagation right after a drag
    bot.addEventListener('click', (e) => {
      if (performance.now() < suppressNextClickUntil) {
        e.stopImmediatePropagation();
        e.preventDefault();
      }
    }, true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attachFoxDragListeners);
  } else {
    attachFoxDragListeners();
  }
})();
