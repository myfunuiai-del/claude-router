// ========================================================
// C-ROUTER FOX-MECHA SANDBOX PUPPET & WARDROBE ENGINE
// Fully Dynamic Multi-Action & Prop Sandbox:
// 1. Interactive Activities:
//    - Fishing (মাছ ধরা / বড়শি ফেলা + জল থেকে মাছ তুলে দেখানো)
//    - Spider-Man (স্পাইডারম্যান স্যুট + কব্জি থেকে জাল ছোঁড়া)
//    - Wizard / Magic (জাদুকরের টুপি + জাদুর কাঠি ঘুরিয়ে আলো জ্বালানো)
//    - Astronaut / Space (মহাকাশের হেলমেট + রকেট ফায়ার উড়ে বেড়ানো)
//    - Detective (গোয়েন্দার ম্যাগনিফাইং গ্লাস দিয়ে ফ্লোর খোঁজাখুঁজি)
//    - Gamer / Music (হেডফোন + গিটার / বুমবক্স বাজাচ্ছে)
//    - Tea / Coffee (চা/কফি কাপে চুমুক)
//    - Rain / Umbrella (ছাতা খুলে বৃষ্টি থেকে বাঁচা)
// 2. Wearable Wardrobe & Costumes (wizard, astronaut, spiderman, hoodie, cape, cap, sunglasses, headphones, tie, scarf)
// 3. Dynamic Teleportation & Safe In-App Navigation (routes, live, usage, teams, servers)
// 4. Undress back to original default state!
// ========================================================

(function() {
  const PROPS_LIBRARY = {
    // Food & Drinks
    burger: `<svg viewBox="0 0 24 24" width="20" height="20">
      <path d="M3 10 C3 5 21 5 21 10 Z" fill="#e0a96d"/>
      <rect x="2" y="11" width="20" height="3" rx="1.5" fill="#56d364"/>
      <rect x="3" y="14" width="18" height="3.5" rx="1.5" fill="#8f1d24"/>
      <path d="M4 18 C4 21 20 21 20 18 Z" fill="#e0a96d"/>
    </svg>`,
    icecream: `<svg viewBox="0 0 24 24" width="20" height="20">
      <circle cx="12" cy="8" r="6" fill="#ff7b72"/>
      <polygon points="7,10 17,10 12,22" fill="#d4a373"/>
    </svg>`,
    juice: `<svg viewBox="0 0 24 24" width="18" height="22">
      <polygon points="5,6 19,6 17,21 7,21" fill="#ffb703"/>
      <line x1="12" y1="2" x2="15" y2="8" stroke="#ffffff" stroke-width="2"/>
    </svg>`,
    tea: `<svg viewBox="0 0 24 24" width="20" height="20">
      <path d="M4 8 L18 8 L16 18 L6 18 Z" fill="#ffffff" stroke="#c9d6e4"/>
      <path d="M18 10 C21 10 21 14 17 15" fill="none" stroke="#ffffff" stroke-width="2"/>
      <path d="M8 5 Q10 2 8 0" fill="none" stroke="#ffd166" stroke-width="1.2" opacity="0.8"/>
      <path d="M13 5 Q15 2 13 0" fill="none" stroke="#ffd166" stroke-width="1.2" opacity="0.8"/>
    </svg>`,

    // Activities & Toys
    fishing_rod: `<svg viewBox="0 0 36 48" width="32" height="42" class="fox-fishing-rod-svg">
      <path d="M4 42 L26 8" stroke="#d4a373" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="4" y1="36" x2="6" y2="44" stroke="#8c2f00" stroke-width="3"/>
      <path class="fox-fishing-line" d="M26 8 Q34 24 28 38" fill="none" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="2,2"/>
      <path d="M28 38 C28 42 24 42 24 39" fill="none" stroke="#94a3b8" stroke-width="1.4"/>
    </svg>`,
    fish: `<svg viewBox="0 0 24 16" width="22" height="15" class="fox-wiggle-fish">
      <path d="M2 8 Q12 0 20 8 Q12 16 2 8 Z" fill="#38bdf8"/>
      <polygon points="20,8 25,3 25,13" fill="#0284c7"/>
      <circle cx="6" cy="6" r="1.5" fill="#ffffff"/>
      <circle cx="6" cy="6" r="0.8" fill="#000000"/>
    </svg>`,
    web_shot: `<svg viewBox="0 0 46 36" width="42" height="32" class="fox-web-blast-svg">
      <path d="M2 18 Q16 12 30 4 M2 18 Q20 18 42 18 M2 18 Q16 24 30 32" stroke="#ffffff" stroke-width="1.4" fill="none"/>
      <path d="M14 14 Q20 18 14 22" fill="none" stroke="#ffffff" stroke-width="1"/>
      <path d="M24 9 Q32 18 24 27" fill="none" stroke="#ffffff" stroke-width="1.2"/>
      <path d="M34 5 Q44 18 34 31" fill="none" stroke="#ffffff" stroke-width="1.3"/>
    </svg>`,
    magnifier: `<svg viewBox="0 0 26 26" width="24" height="24">
      <circle cx="10" cy="10" r="7" fill="none" stroke="#ffd166" stroke-width="2.5"/>
      <circle cx="10" cy="10" r="5" fill="#58a6ff" opacity="0.3"/>
      <line x1="15" y1="15" x2="23" y2="23" stroke="#e0a96d" stroke-width="3.5" stroke-linecap="round"/>
    </svg>`,
    wand: `<svg viewBox="0 0 24 24" width="22" height="22">
      <line x1="3" y1="21" x2="18" y2="6" stroke="#ffd166" stroke-width="2.5" stroke-linecap="round"/>
      <polygon points="18,3 21,7 24,5 21,1" fill="#f72585"/>
      <circle cx="21" cy="4" r="3" fill="#4cc9f0" opacity="0.8"/>
    </svg>`,
    rocket: `<svg viewBox="0 0 24 28" width="22" height="26">
      <path d="M12 2 C7 7 6 18 6 18 L18 18 C18 18 17 7 12 2 Z" fill="#e63946"/>
      <circle cx="12" cy="10" r="2.5" fill="#48cae4"/>
      <polygon points="4,16 6,18 2,22" fill="#457b9d"/>
      <polygon points="20,16 18,18 22,22" fill="#457b9d"/>
      <polygon points="9,18 12,24 15,18" fill="#f77f00"/>
    </svg>`,
    guitar: `<svg viewBox="0 0 26 26" width="24" height="24">
      <ellipse cx="9" cy="17" rx="7" ry="5" fill="#e76f51" transform="rotate(-30 9 17)"/>
      <line x1="12" y1="14" x2="23" y2="3" stroke="#e9c46a" stroke-width="2.5" stroke-linecap="round"/>
      <circle cx="9" cy="17" r="2" fill="#264653"/>
    </svg>`,
    boombox: `<svg viewBox="0 0 24 20" width="22" height="18">
      <rect x="2" y="6" width="20" height="12" rx="2" fill="#30363d" stroke="#58a6ff"/>
      <path d="M6 6 L6 2 L18 2 L18 6" fill="none" stroke="#58a6ff" stroke-width="1.5"/>
      <circle cx="7" cy="12" r="3" fill="#ff7b72"/>
      <circle cx="17" cy="12" r="3" fill="#ff7b72"/>
    </svg>`,
    umbrella: `<svg viewBox="0 0 24 24" width="22" height="22">
      <path d="M2 13 C2 6 22 6 22 13 Z" fill="#58a6ff"/>
      <line x1="12" y1="13" x2="12" y2="21" stroke="#ffffff" stroke-width="2"/>
      <path d="M12 21 C12 23 9 23 9 21" fill="none" stroke="#ffffff" stroke-width="2"/>
    </svg>`,
    balloon: `<svg viewBox="0 0 20 26" width="18" height="24">
      <circle cx="10" cy="9" r="8" fill="#ff4d6d"/>
      <polygon points="9,17 11,17 10,19" fill="#ff4d6d"/>
      <path d="M10 19 Q7 22 10 25" fill="none" stroke="#e6edf3" stroke-width="1.2"/>
    </svg>`,
    wrench: `<svg viewBox="0 0 22 22" width="18" height="18">
      <path d="M14 2 L20 8 L16 12 L10 6 Z" fill="#8b949e"/>
      <line x1="10" y1="10" x2="3" y2="17" stroke="#8b949e" stroke-width="3.5" stroke-linecap="round"/>
    </svg>`,

    // Costumes & Outfits (পোশাক ও কস্টিউম)
    spiderman: `<svg viewBox="0 0 32 32" width="30" height="30" class="fox-spiderman-suit-svg">
      <path d="M6 6 Q16 2 26 6 L29 28 L3 28 Z" fill="#e63946" stroke="#1d3557" stroke-width="1.2"/>
      <path d="M3 18 L9 28 L3 28 Z" fill="#1d3557"/>
      <path d="M29 18 L23 28 L29 28 Z" fill="#1d3557"/>
      <line x1="16" y1="4" x2="16" y2="28" stroke="#111" stroke-width="0.8"/>
      <line x1="6" y1="12" x2="26" y2="12" stroke="#111" stroke-width="0.8"/>
      <line x1="4" y1="20" x2="28" y2="20" stroke="#111" stroke-width="0.8"/>
      <polygon points="16,13 14,16 18,16" fill="#111111"/>
      <polygon points="16,19 13,16 19,16" fill="#111111"/>
    </svg>`,
    wizard: `<svg viewBox="0 0 34 32" width="32" height="30">
      <!-- Pointed starry wizard hat -->
      <polygon points="17,1 7,20 27,20" fill="#4361ee"/>
      <ellipse cx="17" cy="20" rx="14" ry="4" fill="#3a0ca3"/>
      <polygon points="17,8 18,10 20,10 18,12 19,14 17,12 15,14 16,12 14,10 16,10" fill="#ffd166"/>
    </svg>`,
    astronaut: `<svg viewBox="0 0 32 32" width="30" height="30">
      <!-- Golden bubble space helmet visor -->
      <circle cx="16" cy="14" r="12" fill="#edf2f4" stroke="#8d99ae" stroke-width="1.5"/>
      <ellipse cx="16" cy="14" rx="9" ry="7" fill="#f77f00" stroke="#fcbf49" stroke-width="1.2"/>
      <ellipse cx="14" cy="12" rx="4" ry="2" fill="#ffffff" opacity="0.6"/>
    </svg>`,
    sunglasses: `<svg viewBox="0 0 26 12" width="26" height="12">
      <rect x="1" y="2" width="10" height="7" rx="2" fill="#0d1117" stroke="#30363d"/>
      <rect x="15" y="2" width="10" height="7" rx="2" fill="#0d1117" stroke="#30363d"/>
      <line x1="11" y1="4" x2="15" y2="4" stroke="#8b949e" stroke-width="1.5"/>
    </svg>`,
    scarf: `<svg viewBox="0 0 28 14" width="26" height="13">
      <path d="M2 3 Q14 11 26 3 Q24 9 14 10 Q4 9 2 3 Z" fill="#e63946"/>
      <rect x="16" y="8" width="5" height="10" rx="1.5" fill="#e63946"/>
    </svg>`,
    cap: `<svg viewBox="0 0 32 14" width="30" height="13">
      <path d="M6 10 C6 2 24 2 24 10 Z" fill="#1d3557"/>
      <path d="M4 10 L28 10 L30 13 L2 13 Z" fill="#457b9d"/>
    </svg>`,
    tie: `<svg viewBox="0 0 12 24" width="11" height="22">
      <polygon points="4,2 8,2 7,5 5,5" fill="#e63946"/>
      <polygon points="5,5 7,5 9,18 6,22 3,18" fill="#e63946"/>
    </svg>`,
    headphones: `<svg viewBox="0 0 32 28" width="30" height="26">
      <path d="M3 14 C3 4 29 4 29 14" fill="none" stroke="#00f5d4" stroke-width="3"/>
      <rect x="1" y="11" width="5" height="11" rx="2.5" fill="#7b2cbf"/>
      <rect x="26" y="11" width="5" height="11" rx="2.5" fill="#7b2cbf"/>
    </svg>`,
    cape: `<svg viewBox="0 0 32 36" width="32" height="36">
      <path d="M5 2 Q16 8 27 2 L31 34 Q16 28 1 34 Z" fill="#9d0208" opacity="0.9"/>
    </svg>`,
    hoodie: `<svg viewBox="0 0 32 30" width="30" height="28">
      <path d="M5 8 C5 1 27 1 27 8 L29 26 L3 26 Z" fill="#2b2d42" opacity="0.85"/>
      <path d="M12 10 L16 18 L20 10" fill="none" stroke="#ef233c" stroke-width="2"/>
    </svg>`
  };

  const CLOTHES_KEYS = ['sunglasses', 'scarf', 'cap', 'tie', 'headphones', 'cape', 'hoodie', 'spiderman', 'wizard', 'astronaut'];

  let activePropEl = null;
  let activeActionTimeout = null;
  let currentOutfitEls = {};

  function ensurePuppetLayer() {
    const bot = document.getElementById('crouter-bot');
    if (!bot) return null;
    let layer = bot.querySelector('.fox-puppet-layer');
    if (!layer) {
      layer = document.createElement('div');
      layer.className = 'fox-puppet-layer';
      bot.appendChild(layer);
    }
    return layer;
  }

  function triggerPoofParticles(x, y) {
    const layer = ensurePuppetLayer();
    if (!layer) return;
    for (let i = 0; i < 8; i++) {
      const p = document.createElement('div');
      p.className = 'fox-poof-particle';
      const angle = (i / 8) * Math.PI * 2;
      const dist = 14 + Math.random() * 10;
      p.style.setProperty('--px', `${Math.cos(angle) * dist}px`);
      p.style.setProperty('--py', `${Math.sin(angle) * dist}px`);
      p.style.left = `${x}px`;
      p.style.top = `${y}px`;
      layer.appendChild(p);
      setTimeout(() => p.remove(), 480);
    }
  }

  // Safe Navigation - Guides and teleports user to parts of crouter without modifying/deleting anything
  window.foxNavigateTo = function(target) {
    if (!target || target === 'none') return;
    const t = target.toLowerCase();

    if (typeof window.closeFoxBrain === 'function') {
      setTimeout(() => window.closeFoxBrain(), 600);
    }

    if (t === 'live' || t === 'stats') {
      if (typeof window.switchMainTab === 'function') window.switchMainTab('live');
      if (typeof window.updateBottomBar === 'function') window.updateBottomBar('live');
    } else if (t === 'usage' || t === 'quotas') {
      if (typeof window.switchMainTab === 'function') window.switchMainTab('usage');
      if (typeof window.updateBottomBar === 'function') window.updateBottomBar('usage');
    } else if (t === 'teams') {
      if (typeof window.switchMainTab === 'function') window.switchMainTab('console');
      if (typeof window.switchMobileLane === 'function') window.switchMobileLane('multiagent');
      if (typeof window.updateBottomBar === 'function') window.updateBottomBar('teams');
    } else if (t === 'routes') {
      if (typeof window.switchMainTab === 'function') window.switchMainTab('console');
      if (typeof window.switchMobileLane === 'function') window.switchMobileLane('routed');
      if (typeof window.updateBottomBar === 'function') window.updateBottomBar('routes');
    } else if (t === 'servers' || t === 'standby') {
      if (typeof window.switchMainTab === 'function') window.switchMainTab('console');
      if (typeof window.switchMobileLane === 'function') window.switchMobileLane('unrouted');
    } else if (t === 'add_server') {
      if (typeof window.openServerModal === 'function') {
        setTimeout(() => window.openServerModal(), 700);
      }
    }
  };

  window.undressFoxToDefault = function() {
    const layer = ensurePuppetLayer();
    for (let key in currentOutfitEls) {
      if (currentOutfitEls[key]) {
        currentOutfitEls[key].remove();
      }
    }
    currentOutfitEls = {};
    if (layer) {
      triggerPoofParticles(17, 24);
    }
  };

  window.executeFoxSandboxAction = function(actionObj) {
    if (!actionObj || typeof actionObj !== 'object') return;
    const bot = document.getElementById('crouter-bot');
    const layer = ensurePuppetLayer();
    if (!bot || !layer) return;

    const propName = (actionObj.prop || 'none').toLowerCase();
    const motion = (actionObj.motion || 'none').toLowerCase();
    const navigate = (actionObj.navigate || 'none').toLowerCase();

    // 0. Safe In-App Navigation (Teleport)
    if (navigate !== 'none' && typeof window.foxNavigateTo === 'function') {
      window.foxNavigateTo(navigate);
    }

    // 1. Remove Clothes / Undress back to original default body
    if (motion === 'remove' || propName === 'remove' || motion === 'undress') {
      window.undressFoxToDefault();
      bot.className = 'crouter-bot is-sitting';
      return;
    }

    // 2. Wear Outfits (Spiderman, Wizard, Astronaut, Hoodie, Cap, etc.)
    if (CLOTHES_KEYS.includes(propName) && (motion === 'wear' || motion === 'none' || motion === 'spiderman' || motion === 'magic' || motion === 'fly')) {
      if (currentOutfitEls[propName]) {
        currentOutfitEls[propName].remove();
      }
      const clothDiv = document.createElement('div');
      clothDiv.className = 'fox-prop fox-outfit';
      clothDiv.innerHTML = PROPS_LIBRARY[propName];

      if (propName === 'sunglasses') {
        clothDiv.style.left = '4px'; clothDiv.style.top = '11px';
      } else if (propName === 'cap') {
        clothDiv.style.left = '2px'; clothDiv.style.top = '-8px';
      } else if (propName === 'wizard') {
        clothDiv.style.left = '1px'; clothDiv.style.top = '-16px';
      } else if (propName === 'astronaut') {
        clothDiv.style.left = '2px'; clothDiv.style.top = '-2px';
      } else if (propName === 'headphones') {
        clothDiv.style.left = '2px'; clothDiv.style.top = '2px';
      } else if (propName === 'scarf') {
        clothDiv.style.left = '4px'; clothDiv.style.top = '20px';
      } else if (propName === 'tie') {
        clothDiv.style.left = '12px'; clothDiv.style.top = '24px';
      } else if (propName === 'cape') {
        clothDiv.style.left = '1px'; clothDiv.style.top = '15px';
      } else if (propName === 'hoodie' || propName === 'spiderman') {
        clothDiv.style.left = '2px'; clothDiv.style.top = '12px';
      }

      layer.appendChild(clothDiv);
      currentOutfitEls[propName] = clothDiv;
      triggerPoofParticles(17, 20);

      if (motion !== 'spiderweb' && motion !== 'magic' && motion !== 'fly') {
        return;
      }
    }

    // 3. Clear temporary action & props
    if (activeActionTimeout) {
      clearTimeout(activeActionTimeout);
      activeActionTimeout = null;
    }
    bot.className = 'crouter-bot is-sitting';
    if (activePropEl) {
      activePropEl.remove();
      activePropEl = null;
    }

    const vanishTime = Math.max(3000, Math.min(12000, actionObj.vanish_after_ms || 4500));

    // SPECIAL 1: FISHING (মাছ ধরা)
    if (motion === 'fishing' || propName === 'fishing_rod') {
      bot.classList.add('action-fishing');
      const rodDiv = document.createElement('div');
      rodDiv.className = 'fox-prop fox-fishing-assembly';
      rodDiv.innerHTML = PROPS_LIBRARY.fishing_rod;
      rodDiv.style.left = '16px'; rodDiv.style.top = '8px';
      layer.appendChild(rodDiv);
      activePropEl = rodDiv;

      setTimeout(() => {
        if (!rodDiv.parentNode) return;
        const fishDiv = document.createElement('div');
        fishDiv.className = 'fox-prop fox-caught-fish';
        fishDiv.innerHTML = PROPS_LIBRARY.fish;
        fishDiv.style.left = '24px'; fishDiv.style.top = '28px';
        rodDiv.appendChild(fishDiv);
        triggerPoofParticles(28, 32);
      }, 1600);
    }
    // SPECIAL 2: SPIDER-MAN WEB THROW (জাল ছোঁড়া)
    else if (motion === 'spiderweb' || propName === 'web_shot') {
      if (!currentOutfitEls['spiderman']) {
        const suitDiv = document.createElement('div');
        suitDiv.className = 'fox-prop fox-outfit';
        suitDiv.innerHTML = PROPS_LIBRARY.spiderman;
        suitDiv.style.left = '2px'; suitDiv.style.top = '12px';
        layer.appendChild(suitDiv);
        currentOutfitEls['spiderman'] = suitDiv;
      }
      bot.classList.add('action-spiderweb');
      const webDiv = document.createElement('div');
      webDiv.className = 'fox-prop fox-web-projectile';
      webDiv.innerHTML = PROPS_LIBRARY.web_shot;
      webDiv.style.left = '22px'; webDiv.style.top = '12px';
      layer.appendChild(webDiv);
      activePropEl = webDiv;
      triggerPoofParticles(24, 20);
    }
    // SPECIAL 3: WIZARD MAGIC (জাদু খেলা / কাঠি ঘুরিয়ে ফুলকি ছিটানো)
    else if (motion === 'magic' || propName === 'wand') {
      if (!currentOutfitEls['wizard']) {
        const wizHat = document.createElement('div');
        wizHat.className = 'fox-prop fox-outfit';
        wizHat.innerHTML = PROPS_LIBRARY.wizard;
        wizHat.style.left = '1px'; wizHat.style.top = '-16px';
        layer.appendChild(wizHat);
        currentOutfitEls['wizard'] = wizHat;
      }
      bot.classList.add('action-magic');
      const wandDiv = document.createElement('div');
      wandDiv.className = 'fox-prop fox-magic-wand';
      wandDiv.innerHTML = PROPS_LIBRARY.wand;
      wandDiv.style.left = '18px'; wandDiv.style.top = '12px';
      layer.appendChild(wandDiv);
      activePropEl = wandDiv;
      triggerPoofParticles(24, 12);
    }
    // SPECIAL 4: ASTRONAUT ROCKET FLY (রকেটে মহাশূন্যে ওড়া)
    else if (motion === 'fly' || propName === 'rocket') {
      if (!currentOutfitEls['astronaut']) {
        const astroHelm = document.createElement('div');
        astroHelm.className = 'fox-prop fox-outfit';
        astroHelm.innerHTML = PROPS_LIBRARY.astronaut;
        astroHelm.style.left = '2px'; astroHelm.style.top = '-2px';
        layer.appendChild(astroHelm);
        currentOutfitEls['astronaut'] = astroHelm;
      }
      bot.classList.add('action-rocket-fly');
      triggerPoofParticles(17, 36);
    }
    // SPECIAL 5: DETECTIVE SEARCH (ম্যাগনিফাইং গ্লাস দিয়ে তল্লাশি)
    else if (motion === 'investigate' || propName === 'magnifier') {
      bot.classList.add('action-investigate');
      const magDiv = document.createElement('div');
      magDiv.className = 'fox-prop fox-magnifier-prop';
      magDiv.innerHTML = PROPS_LIBRARY.magnifier;
      magDiv.style.left = '16px'; magDiv.style.top = '22px';
      layer.appendChild(magDiv);
      activePropEl = magDiv;
    }
    // SPECIAL 6: GUITAR ROCKSTAR (গিটার বাজিয়ে কনসার্ট)
    else if (motion === 'guitar' || propName === 'guitar') {
      bot.classList.add('action-rockstar');
      const gDiv = document.createElement('div');
      gDiv.className = 'fox-prop fox-guitar-prop';
      gDiv.innerHTML = PROPS_LIBRARY.guitar;
      gDiv.style.left = '8px'; gDiv.style.top = '16px';
      layer.appendChild(gDiv);
      activePropEl = gDiv;
    }
    // DYNAMIC AI GENERATED SVG (যেকোনো অজানা নতুন জিনিস AI নিজে তৈরি করলে সরাসরি রেন্ডার)
    else if (actionObj.svg && typeof actionObj.svg === 'string' && actionObj.svg.includes('<svg')) {
      const propDiv = document.createElement('div');
      propDiv.className = 'fox-prop fox-dynamic-ai-svg';
      propDiv.innerHTML = actionObj.svg;
      propDiv.style.left = '14px';
      propDiv.style.top = '16px';
      propDiv.style.transform = 'scale(0) translateY(10px)';
      layer.appendChild(propDiv);
      activePropEl = propDiv;
      triggerPoofParticles(20, 24);
      requestAnimationFrame(() => {
        propDiv.style.transform = 'scale(1) translateY(0)';
      });
    }
    // STANDARD TEMPORARY PROPS
    else if (propName !== 'none' && PROPS_LIBRARY[propName]) {
      const propDiv = document.createElement('div');
      propDiv.className = 'fox-prop';
      propDiv.innerHTML = PROPS_LIBRARY[propName];

      if (propName === 'umbrella') {
        propDiv.style.left = '-6px'; propDiv.style.top = '-16px';
      } else if (propName === 'balloon') {
        propDiv.style.left = '22px'; propDiv.style.top = '-18px';
      } else if (propName === 'tea') {
        propDiv.style.left = '16px'; propDiv.style.top = '20px';
      } else {
        propDiv.style.left = '16px'; propDiv.style.top = '22px';
      }

      propDiv.style.transform = 'scale(0) translateY(10px)';
      layer.appendChild(propDiv);
      activePropEl = propDiv;

      requestAnimationFrame(() => {
        propDiv.style.transform = 'scale(1) translateY(0)';
      });
    }

    // Standard & Emotional Body Expressions (ফুল বডি না বদলে নিখুঁত অভিনয়)
    if (motion === 'eat') bot.classList.add('action-eat');
    else if (motion === 'dance') bot.classList.add('action-dance');
    else if (motion === 'flip') bot.classList.add('action-flip');
    else if (motion === 'sleep') bot.classList.add('action-sleep');
    else if (motion === 'wave') bot.classList.add('is-waving');
    else if (motion === 'angry') bot.classList.add('action-angry');
    else if (motion === 'scared') bot.classList.add('action-scared');
    else if (motion === 'cry') bot.classList.add('action-cry');
    else if (motion === 'hide') bot.classList.add('action-hide');
    else if (motion === 'jump') bot.classList.add('action-jump');
    else if (motion === 'fall') bot.classList.add('action-fall');

    // Auto-vanish temporary item
    activeActionTimeout = setTimeout(() => {
      if (activePropEl) {
        triggerPoofParticles(parseInt(activePropEl.style.left || '15', 10), parseInt(activePropEl.style.top || '15', 10));
        activePropEl.style.transform = 'scale(0) rotate(20deg)';
        activePropEl.style.opacity = '0';
        setTimeout(() => {
          if (activePropEl) {
            activePropEl.remove();
            activePropEl = null;
          }
        }, 360);
      }
      bot.className = 'crouter-bot is-sitting';
      activeActionTimeout = null;
    }, vanishTime);
  };
})();
