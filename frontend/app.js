/**
 * Dread Eater — Single Page Application
 * No build step, no framework. Pure vanilla JS.
 */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
  currentScreen: 'dump',
  energyLevel: null,          // 'sleepy' | 'okay' | 'awake'
  todayStep: null,
  lastShrunkFrom: null,       // step ID before shrink, for undo
  config: { model: '', system_prompt: '', available_models: [] },
  ollamaOnline: false,
};

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------
const API = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  },
  async post(path, body = {}) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  },
  async put(path, body = {}) {
    const r = await fetch(path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  },
  async del(path) {
    const r = await fetch(path, { method: 'DELETE' });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  },
};

// ---------------------------------------------------------------------------
// Toast notifications
// ---------------------------------------------------------------------------
function toast(msg, type = 'info', durationMs = 3500) {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => {
    el.classList.add('fade-out');
    el.addEventListener('animationend', () => el.remove());
  }, durationMs);
}

// ---------------------------------------------------------------------------
// Mascot state controller
// ---------------------------------------------------------------------------
const sloth = {
  wrapper: null,
  bubble: null,

  init() {
    this.wrapper = document.getElementById('sloth-wrapper');
    this.bubble = document.getElementById('mascot-bubble');
  },

  setState(s) {
    // s: 'idle' | 'sleepy' | 'clap' | 'shrug'
    if (!this.wrapper) return;
    this.wrapper.classList.remove('state-sleepy', 'state-clap', 'state-shrug');
    if (s !== 'idle') {
      this.wrapper.classList.add(`state-${s}`);
      // Auto-revert after animation
      if (s === 'clap' || s === 'shrug') {
        setTimeout(() => this.wrapper.classList.remove(`state-${s}`), 2200);
      }
    }
  },

  say(msg) {
    if (!this.bubble || !msg) return;
    this.bubble.textContent = `"${msg}"`;
    this.bubble.style.display = 'block';
    this.bubble.style.animation = 'none';
    // Trigger reflow to re-run animation
    void this.bubble.offsetWidth;
    this.bubble.style.animation = '';
  },
};

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------
function navigate(screenId) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.screen === screenId);
  });
  const screen = document.getElementById(`screen-${screenId}`);
  if (screen) screen.classList.add('active');
  state.currentScreen = screenId;
  if (screenId === 'today') loadTodayScreen();
  if (screenId === 'wins')  loadWinsScreen();
  if (screenId === 'settings') loadSettingsScreen();
}

// ---------------------------------------------------------------------------
// Health / status bar
// ---------------------------------------------------------------------------
async function refreshStatus() {
  try {
    const h = await API.get('/api/health');
    state.ollamaOnline = h.ollama_alive;
    const dot = document.getElementById('status-dot');
    const label = document.getElementById('status-label');
    if (dot) dot.className = `status-dot ${h.ollama_alive ? 'online' : 'offline'}`;
    if (label) label.textContent = h.ollama_alive ? h.model : 'Ollama offline';
  } catch {
    const dot = document.getElementById('status-dot');
    if (dot) dot.className = 'status-dot offline';
  }
}

// ---------------------------------------------------------------------------
// DUMP SCREEN
// ---------------------------------------------------------------------------
function initDumpScreen() {
  const form = document.getElementById('dump-form');
  const taskInput = document.getElementById('task-input');
  const ctxInput = document.getElementById('context-input');
  const ctxToggle = document.getElementById('ctx-toggle');
  const ctxArea = document.getElementById('ctx-area');
  const submitBtn = document.getElementById('dump-submit');
  const resultEl = document.getElementById('dump-result');

  ctxToggle.addEventListener('click', () => {
    const open = ctxArea.style.display !== 'none';
    ctxArea.style.display = open ? 'none' : 'block';
    ctxToggle.textContent = open
      ? '+ Paste context (email, letter, form…)'
      : '− Hide context';
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const raw = taskInput.value.trim();
    if (!raw) { toast('Please describe the task first!', 'error'); return; }

    setButtonLoading(submitBtn, true);
    resultEl.innerHTML = '';
    sloth.say('Sniffing out the dreaded bits… hang on! 🦥');

    try {
      const data = await API.post('/api/tasks', {
        raw_text: raw,
        context_text: ctxInput.value.trim() || null,
      });
      renderTaskResult(data, resultEl);
      sloth.say(data.mascot_message || 'Look at that! Already one step closer. 🦥');
      toast('Task analysed! Check your ladder below.', 'success');
    } catch (err) {
      toast(`Error: ${err.message}`, 'error');
      sloth.say('Uh-oh… even sloths trip sometimes. Try again? 🌿');
    } finally {
      setButtonLoading(submitBtn, false);
    }
  });
}

function renderTaskResult(data, container) {
  const dreadClass = data.dread_score <= 3 ? 'dread-low' : data.dread_score <= 6 ? 'dread-mid' : 'dread-high';
  const artifactsHtml = renderArtifacts(data.prepared_artifacts);
  const ladderHtml = (data.ladder || []).map((s, i) => `
    <li class="ladder-item">
      <span class="ladder-idx">${i + 1}</span>
      <span>${escHtml(s.description)} <span class="text-muted text-small">(~${s.duration_min} min)</span></span>
    </li>`).join('');

  const mlfNote = data.is_medical_legal_financial ? `
    <div class="mlf-disclaimer">
      ⚠️ <span>The drafts below are not professional medical, legal, or financial advice.
      They are writing prompts only — please consult a qualified professional for important decisions.</span>
    </div>` : '';

  container.innerHTML = `
    <div class="card result-card mt-md">
      <div class="flex gap-sm" style="align-items:center;margin-bottom:12px;flex-wrap:wrap">
        <span class="section-title">Analysis</span>
        <span class="dread-badge ${dreadClass}">😰 Dread ${data.dread_score}/10</span>
      </div>
      <p style="color:var(--text-secondary);font-size:0.9rem;margin-bottom:16px">
        <strong style="color:var(--text-primary)">Why it feels hard:</strong> ${escHtml(data.dread_reason)}
      </p>
      <div style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.25);border-radius:8px;padding:12px 16px;margin-bottom:16px">
        <span class="section-title" style="color:var(--green-soft);font-size:0.75rem">⚡ Tiniest first step (&lt;2 min)</span>
        <p style="margin-top:6px;font-weight:600;color:var(--text-primary)">${escHtml(data.first_step)}</p>
      </div>
      ${ladderHtml ? `<span class="section-title">Micro-steps ladder</span><ul class="ladder-list mt-sm">${ladderHtml}</ul>` : ''}
      ${artifactsHtml}
      ${mlfNote}
      <div class="btn-row mt-md">
        <button class="btn btn-primary w-full" onclick="navigate('today')">
          <span class="btn-label">👉 Go to Today's Step</span>
        </button>
      </div>
    </div>`;
}

function renderArtifacts(artifacts) {
  if (!artifacts || artifacts.length === 0) return '';
  const tabs = artifacts.map((a, i) => `
    <button class="artifact-tab ${i === 0 ? 'active' : ''}"
            onclick="selectArtifact(${i})"
            id="art-tab-${i}">
      ${artifactIcon(a.type)} ${escHtml(a.title)}
    </button>`).join('');

  const panels = artifacts.map((a, i) => `
    <div id="art-panel-${i}" class="artifact-content" style="${i > 0 ? 'display:none' : ''}">
${escHtml(a.content)}
    </div>`).join('');

  return `
    <div class="mt-md">
      <span class="section-title">📄 Ready-to-use Drafts</span>
      <div class="artifact-tabs mt-sm">${tabs}</div>
      ${panels}
      <button class="btn btn-ghost text-small mt-sm" onclick="copyArtifact()">📋 Copy to clipboard</button>
    </div>`;
}

window.selectArtifact = function(idx) {
  document.querySelectorAll('.artifact-tab').forEach((t, i) =>
    t.classList.toggle('active', i === idx));
  document.querySelectorAll('.artifact-content').forEach((p, i) =>
    p.style.display = i === idx ? 'block' : 'none');
};

window.copyArtifact = function() {
  const visible = document.querySelector('.artifact-content:not([style*="display:none"])');
  if (!visible) return;
  navigator.clipboard.writeText(visible.textContent.trim())
    .then(() => toast('Copied to clipboard!', 'success'))
    .catch(() => toast('Copy failed — select the text manually.', 'error'));
};

function artifactIcon(type) {
  const icons = { email_draft: '📧', checklist: '☑️', phone_script: '📞', outline: '📝' };
  return icons[type] || '📄';
}

// ---------------------------------------------------------------------------
// TODAY SCREEN
// ---------------------------------------------------------------------------
async function loadTodayScreen() {
  const container = document.getElementById('today-content');
  container.innerHTML = `<div class="card skeleton" style="height:200px"></div>`;

  try {
    const data = await API.get('/api/today');
    renderTodayScreen(data, container);
  } catch (err) {
    container.innerHTML = `<div class="card"><p class="text-muted text-center">Could not load today's step: ${escHtml(err.message)}</p></div>`;
  }
}

function renderTodayScreen(data, container) {
  state.todayStep = data.step;
  state.energyLevel = data.energy_level;

  // Offline banner
  const offlineBanner = data.ollama_offline_note ? `
    <div class="offline-banner">
      <span style="font-size:1.5rem">🦥</span>
      <p>${escHtml(data.ollama_offline_note)}</p>
      <button class="btn btn-ghost" onclick="retryArtifacts()" id="retry-arts-btn">
        <span class="btn-label">Retry Drafts</span><span class="btn-spinner"></span>
      </button>
    </div>` : '';

  // Energy picker
  const energyPicker = `
    <div class="card">
      <span class="section-title">How's your energy today?</span>
      <div class="energy-picker mt-md">
        <button class="energy-btn ${data.energy_level === 'sleepy' ? 'selected' : ''}"
                id="energy-sleepy" onclick="setEnergy('sleepy')">😴 Sleepy</button>
        <button class="energy-btn ${data.energy_level === 'okay' ? 'selected' : ''}"
                id="energy-okay" onclick="setEnergy('okay')">🙂 Okay</button>
        <button class="energy-btn ${data.energy_level === 'awake' ? 'selected' : ''}"
                id="energy-awake" onclick="setEnergy('awake')">⚡ Awake</button>
      </div>
    </div>`;

  // Step card
  let stepCard = '';
  if (data.step) {
    const s = data.step;
    const undoLink = s.is_shrunken && state.lastShrunkFrom
      ? `<span class="undo-shrink-link" onclick="undoShrink('${state.lastShrunkFrom}')">↩ Undo shrink</span>`
      : '';

    stepCard = `
      <div class="card today-step-card" id="today-step-card">
        <div class="text-small text-muted" style="margin-bottom:8px">
          ${escHtml(s.task_raw_text || '')}
        </div>
        <p style="font-size:1.2rem;font-weight:600;color:var(--text-primary);line-height:1.5;margin-bottom:8px">
          ${escHtml(s.description)}
        </p>
        <div class="step-duration-badge">⏱ ~${s.duration_min} min${s.is_shrunken ? ' · <em>shrunk step</em>' : ''}</div>
        ${undoLink}
        <div class="step-actions">
          <button class="btn btn-success" id="btn-done" onclick="markDone('${s.id}')">
            <span class="btn-label">✅ Done!</span><span class="btn-spinner"></span>
          </button>
          <button class="btn btn-warning" id="btn-shrink" onclick="shrinkStep('${s.id}')">
            <span class="btn-label">🔪 Too big, shrink it</span><span class="btn-spinner"></span>
          </button>
          <button class="btn btn-ghost" id="btn-snooze" onclick="snoozeStep('${s.id}')">
            <span class="btn-label">💤 Not today</span><span class="btn-spinner"></span>
          </button>
        </div>
      </div>`;

    if (data.step.mascot_message) {
      sloth.say(data.step.mascot_message);
    }
    if (data.energy_level === 'sleepy') sloth.setState('sleepy');
    else sloth.setState('idle');
  } else {
    stepCard = `
      <div class="card text-center" style="padding:40px">
        <div style="font-size:3rem;margin-bottom:16px">🎉</div>
        <h2 style="font-family:Outfit,sans-serif;font-size:1.4rem;margin-bottom:8px">
          All caught up!
        </h2>
        <p class="text-muted">No pending steps. Add a new dreaded task or enjoy the peace. 🦥</p>
        <button class="btn btn-primary mt-md" onclick="navigate('dump')">
          + Add a dreaded task
        </button>
      </div>`;
    sloth.say('All done! Even sloths need rest sometimes. 🌿');
  }

  container.innerHTML = `${offlineBanner}${energyPicker}${stepCard}`;
}

window.setEnergy = async function(level) {
  try {
    await API.post('/api/today/energy', { energy_level: level });
    state.energyLevel = level;
    ['sleepy','okay','awake'].forEach(l => {
      document.getElementById(`energy-${l}`)?.classList.toggle('selected', l === level);
    });
    if (level === 'sleepy') sloth.setState('sleepy');
    else sloth.setState('idle');
    // Reload step for new energy level
    await loadTodayScreen();
  } catch (err) {
    toast(`Could not set energy: ${err.message}`, 'error');
  }
};

window.markDone = async function(stepId) {
  const btn = document.getElementById('btn-done');
  setButtonLoading(btn, true);
  try {
    const res = await API.post(`/api/steps/${stepId}/done`);
    sloth.setState('clap');
    sloth.say(res.mascot_message || 'YES! One tiny step devoured! 🦥');
    toast('Step marked done! 🎉', 'success');
    setTimeout(() => loadTodayScreen(), 1500);
  } catch (err) {
    toast(`Error: ${err.message}`, 'error');
    setButtonLoading(btn, false);
  }
};

window.snoozeStep = async function(stepId) {
  const btn = document.getElementById('btn-snooze');
  setButtonLoading(btn, true);
  try {
    const res = await API.post(`/api/steps/${stepId}/snooze`);
    sloth.setState('shrug');
    sloth.say(res.mascot_message);
    toast(`Snoozed until tomorrow. No guilt! 🌿`, 'info');
    setTimeout(() => loadTodayScreen(), 1200);
  } catch (err) {
    toast(`Error: ${err.message}`, 'error');
    setButtonLoading(btn, false);
  }
};

window.shrinkStep = async function(stepId) {
  const btn = document.getElementById('btn-shrink');
  setButtonLoading(btn, true);
  sloth.say('Thinking of the tiniest possible crumbs… 🦥');
  try {
    const res = await API.post(`/api/steps/${stepId}/shrink`);
    state.lastShrunkFrom = res.undo_token;
    toast(`Shrunk into ${res.remaining_steps.length + 1} tiny pieces!`, 'success');
    sloth.say('There. Much more bite-sized now! 🌿');
    await loadTodayScreen();
  } catch (err) {
    toast(`Could not shrink: ${err.message}`, 'error');
  } finally {
    setButtonLoading(btn, false);
  }
};

window.undoShrink = async function(originalStepId) {
  try {
    await API.post(`/api/steps/${originalStepId}/undo-shrink`);
    state.lastShrunkFrom = null;
    toast('Original step restored.', 'info');
    await loadTodayScreen();
  } catch (err) {
    toast(`Could not undo: ${err.message}`, 'error');
  }
};

window.retryArtifacts = async function() {
  const btn = document.getElementById('retry-arts-btn');
  if (btn) setButtonLoading(btn, true);
  try {
    const res = await API.post('/api/retry-artifacts');
    toast(`Drafts generated for ${res.updated} task(s)!`, 'success');
    await loadTodayScreen();
  } catch (err) {
    toast(`Retry failed: ${err.message}`, 'error');
    if (btn) setButtonLoading(btn, false);
  }
};

// ---------------------------------------------------------------------------
// WINS SCREEN
// ---------------------------------------------------------------------------
async function loadWinsScreen() {
  const container = document.getElementById('wins-content');
  container.innerHTML = `<div class="card skeleton" style="height:200px"></div>`;
  try {
    const data = await API.get('/api/wins');
    renderWinsScreen(data, container);
  } catch (err) {
    container.innerHTML = `<div class="card"><p class="text-muted text-center">Could not load wins: ${escHtml(err.message)}</p></div>`;
  }
}

function renderWinsScreen(data, container) {
  const counter = `
    <div class="wins-header">
      <h2 style="font-family:Outfit,sans-serif;font-size:1.5rem;font-weight:800;
                 background:linear-gradient(135deg,var(--green),var(--amber));
                 -webkit-background-clip:text;-webkit-text-fill-color:transparent">
        🏆 Wall of Sloth Wins
      </h2>
      <div class="wins-counter">
        <strong>${data.total_wins}</strong> steps crushed ·
        <strong>${data.fully_finished_tasks}</strong> task${data.fully_finished_tasks !== 1 ? 's' : ''} fully finished
      </div>
    </div>`;

  if (data.wins.length === 0) {
    container.innerHTML = `${counter}
      <div class="empty-state">
        <div style="font-size:3rem">🦥</div>
        <p>No wins yet — your first tiny step is waiting on the Today screen!</p>
      </div>`;
    return;
  }

  const cards = data.wins.map(w => {
    const date = w.completed_at ? new Date(w.completed_at + 'Z').toLocaleDateString() : '';
    return `
      <div class="win-card">
        <div class="win-task-name">${escHtml(w.task_raw_text)}</div>
        <div class="win-description">✅ ${escHtml(w.description)}</div>
        ${w.mascot_message ? `<div class="win-mascot">"${escHtml(w.mascot_message)}"</div>` : ''}
        <div class="win-date">${date}</div>
      </div>`;
  }).join('');

  container.innerHTML = `${counter}<div class="wins-grid">${cards}</div>`;
}

// ---------------------------------------------------------------------------
// SETTINGS SCREEN
// ---------------------------------------------------------------------------
async function loadSettingsScreen() {
  try {
    const cfg = await API.get('/api/config');
    state.config = cfg;
    renderSettingsScreen(cfg);
  } catch (err) {
    document.getElementById('settings-content').innerHTML =
      `<div class="card"><p class="text-muted">Could not load settings: ${escHtml(err.message)}</p></div>`;
  }
}

function renderSettingsScreen(cfg) {
  const modelOptions = cfg.available_models.map(m =>
    `<option value="${escHtml(m)}" ${m === cfg.model ? 'selected' : ''}>${escHtml(m)}</option>`
  ).join('');

  document.getElementById('settings-content').innerHTML = `
    <!-- Model -->
    <div class="card">
      <span class="card-title">🤖 Ollama Model</span>
      <div class="settings-group mt-md">
        <label for="model-select">Active model</label>
        <select id="model-select">
          ${modelOptions || `<option value="${escHtml(cfg.model)}">${escHtml(cfg.model)}</option>`}
        </select>
        <button class="btn btn-primary" id="save-model-btn" onclick="saveModel()">
          <span class="btn-label">Save model</span><span class="btn-spinner"></span>
        </button>
      </div>
    </div>

    <!-- System prompt -->
    <div class="card">
      <span class="card-title">🎭 Mascot Personality</span>
      <p class="text-muted text-small mt-sm">
        Edit Slothy's system prompt to change personality, step-sizing rules, or tone.
      </p>
      <div class="settings-group mt-md">
        <label for="prompt-input">System prompt</label>
        <textarea id="prompt-input" rows="8">${escHtml(cfg.system_prompt)}</textarea>
        <button class="btn btn-primary" id="save-prompt-btn" onclick="savePrompt()">
          <span class="btn-label">Save prompt</span><span class="btn-spinner"></span>
        </button>
      </div>
    </div>

    <!-- Data management -->
    <div class="card">
      <span class="card-title">📁 Data Management</span>
      <p class="text-muted text-small mt-sm">
        All your data lives in a local SQLite file. Nothing is ever sent anywhere.
      </p>
      <div class="btn-row mt-md">
        <a href="/api/export" download="dread_eater_export.json" class="btn btn-ghost">
          ⬇️ Export everything
        </a>
      </div>
    </div>

    <!-- Danger zone -->
    <div class="settings-danger-zone">
      <span class="card-title" style="color:var(--red-soft)">⚠️ Danger Zone</span>
      <p class="text-muted text-small mt-sm">
        Permanently deletes all tasks, steps, and history. This cannot be undone.
      </p>
      <button class="btn btn-danger mt-md" onclick="wipeEverything()">
        🗑️ Wipe everything
      </button>
    </div>`;
}

window.saveModel = async function() {
  const btn = document.getElementById('save-model-btn');
  const model = document.getElementById('model-select')?.value;
  if (!model) return;
  setButtonLoading(btn, true);
  try {
    await API.put('/api/config', { model });
    toast('Model saved!', 'success');
  } catch (err) {
    toast(`Error: ${err.message}`, 'error');
  } finally {
    setButtonLoading(btn, false);
  }
};

window.savePrompt = async function() {
  const btn = document.getElementById('save-prompt-btn');
  const system_prompt = document.getElementById('prompt-input')?.value;
  setButtonLoading(btn, true);
  try {
    await API.put('/api/config', { system_prompt });
    toast('System prompt saved!', 'success');
  } catch (err) {
    toast(`Error: ${err.message}`, 'error');
  } finally {
    setButtonLoading(btn, false);
  }
};

window.wipeEverything = async function() {
  if (!confirm('This will permanently delete ALL tasks, steps, and history. Are you absolutely sure?')) return;
  const confirm2 = prompt('Type DELETE to confirm:');
  if (confirm2 !== 'DELETE') { toast('Wipe cancelled.', 'info'); return; }
  try {
    await API.post('/api/wipe', { confirm: 'WIPE_EVERYTHING' });
    toast('Everything wiped. Fresh start! 🦥', 'success');
    sloth.say('Clean slate! Even sloths start fresh sometimes. 🌿');
    navigate('dump');
  } catch (err) {
    toast(`Wipe failed: ${err.message}`, 'error');
  }
};

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function escHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function setButtonLoading(btn, loading) {
  if (!btn) return;
  btn.classList.toggle('loading', loading);
  btn.disabled = loading;
}

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', async () => {
  sloth.init();

  // Wire nav tabs
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => navigate(tab.dataset.screen));
  });

  // Logo click → dump
  document.getElementById('nav-logo')?.addEventListener('click', () => navigate('dump'));

  // Initial status check
  await refreshStatus();
  setInterval(refreshStatus, 30_000);

  // Start on dump screen
  navigate('dump');
  initDumpScreen();

  // Sloth idle state
  sloth.setState('idle');
  sloth.say('What dreaded task shall we shrink today? 🦥');
});
