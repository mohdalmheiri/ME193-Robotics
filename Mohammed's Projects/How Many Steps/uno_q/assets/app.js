// Step Recorder phone page. Every 0.5 s it asks the board for /status and
// shows the right controls for the board's state:
//   idle      -> pick name + activity, Start
//   recording -> Stop (and a "stomp" reminder for the first seconds)
//   pending   -> type in steps + distance, Save or Discard

// Button labels for the activities (the board and file names keep the short ones)
const LABELS = {
  Walk_slow: 'Walk slow', Walk_normal: 'Walk normal', Walk_fast: 'Walk fast',
  Run: 'Run', Stand: 'Stand', Fidget: 'Fidget<small>shift weight</small>',
  LegSwing: 'Leg swing<small>sitting</small>', Test: 'Test<small>counted</small>',
  Outdoor: 'Outdoor<small>vs phone</small>',
};
const STOMP_SECONDS = 4;   // how long the stomp reminder stays up

const $ = (sel) => document.querySelector(sel);

// localStorage remembers names and the last activity on this phone. It can be
// unavailable (private browsing), so every use is wrapped in try/catch.
function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (e) { return fallback; }
}
function store(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
}

let names = load('names', ['Mohammed']);     // quick-pick name buttons
let activity = load('activity', 'Walk_normal');
let state = null;                            // the latest /status from the board
let shownPending = null;                     // the trial whose count form is filled in

$('#person').value = load('person', 'Mohammed');

// ---- Name buttons: tap to fill in a name used before ----
function drawNames() {
  $('#name-buttons').innerHTML = '';
  names.forEach((name) => {
    const b = document.createElement('button');
    b.textContent = name;
    b.className = 'chip';
    b.onclick = () => { $('#person').value = name; store('person', name); updateNext(); };
    $('#name-buttons').append(b);
  });
}
drawNames();
$('#person').addEventListener('input', () => { store('person', $('#person').value); updateNext(); });

// ---- Activity buttons (built once the board says which activities exist) ----
function drawActivities(list) {
  const box = $('#activities');
  if (box.children.length) return;
  if (!list.includes(activity)) activity = list[0];
  list.forEach((a) => {
    const b = document.createElement('button');
    b.innerHTML = LABELS[a] || a;
    b.className = 'activity-btn' + (a === activity ? ' selected' : '');
    b.onclick = () => {
      activity = a;
      store('activity', a);
      box.querySelectorAll('button').forEach((x) => x.classList.toggle('selected', x === b));
      updateNext();
    };
    box.append(b);
  });
  updateNext();
}

// Show the file name the next trial will get, e.g. Mohammed_Walk_normal_T04.csv
async function updateNext() {
  try {
    const url = `/next?person=${encodeURIComponent($('#person').value)}&activity=${activity}`;
    const r = await (await fetch(url)).json();
    $('#next-file').textContent = r.file || '-';
  } catch (e) {}
}

// ---- Buttons that talk to the board ----
async function call(url) {
  const r = await fetch(url);
  const body = await r.json();
  if (!r.ok || body.ok === false) throw new Error(body.error || 'Please check the numbers');
  return body;
}

$('#start-btn').onclick = async () => {
  const person = $('#person').value.trim() || 'anonymous';
  if (!names.includes(person)) { names.push(person); store('names', names); drawNames(); }
  try {
    await call(`/start?person=${encodeURIComponent(person)}&activity=${activity}`);
  } catch (e) { alert(e.message); }
  refresh();
};

$('#stop-btn').onclick = async () => {
  try { await call('/stop'); } catch (e) { alert(e.message); }
  refresh();
};

$('#save-btn').onclick = async () => {
  const steps = $('#steps').value, dist = $('#distance').value;
  if (steps === '' || dist === '') {
    $('#count-error').textContent = 'Enter both the steps and the distance.';
    return;
  }
  try {
    await call(`/save?steps=${encodeURIComponent(steps)}&distance_m=${encodeURIComponent(dist)}`);
    $('#count-error').textContent = '';
  } catch (e) { $('#count-error').textContent = e.message; }
  refresh();
};

$('#discard-btn').onclick = async () => {
  if (!confirm(`Delete ${state.trial.file} without saving?`)) return;
  try { await call('/discard'); } catch (e) { alert(e.message); }
  refresh();
};

$('#delete-btn').onclick = async () => {
  const last = state && state.recent_trials[0];
  if (!last) return;
  if (!confirm(`Delete ${last.file} and its row in trials.csv?`)) return;
  try { await call('/delete_last'); } catch (e) { alert(e.message); }
  refresh();
  updateNext();
};

// ---- Show the board's state ----
function fillCountForm(s) {
  // Pre-fill once per trial: 0 steps / 0 m for the no-step activities,
  // 20 m otherwise, nothing for Outdoor (its distance comes from GPS/phone).
  if (shownPending === s.trial.file) return;
  shownPending = s.trial.file;
  const noSteps = s.no_step_activities.includes(s.trial.activity);
  $('#steps').value = noSteps ? 0 : '';
  $('#distance').value = noSteps ? 0 : (s.trial.activity === 'Outdoor' ? '' : s.default_distance_m);
  $('#count-file').textContent = s.trial.file;
  $('#phyphox-name').textContent = s.trial.file.replace(/\.csv$/, '.zip');
  $('#count-error').textContent = '';
  if (!noSteps) $('#steps').focus();
}

async function refresh() {
  let s;
  try { s = await (await fetch('/status')).json(); } catch (e) { return; }  // try again next tick
  // Back to idle after a save or discard: the next trial number has changed
  if (s.mode === 'idle' && state && state.mode !== 'idle') updateNext();
  state = s;
  drawActivities(s.activities);

  const labels = { idle: 'Ready', recording: 'Recording', pending: 'Waiting for the count' };
  $('#status-mode').textContent = labels[s.mode] + (s.trial && s.mode !== 'idle' ? ` · ${s.trial.file}` : '');
  // Recording: live numbers. Waiting for the count: the finished trial's
  // length. Ready: nothing yet (don't show the previous trial's numbers).
  $('#status-time').textContent = { recording: s.elapsed, pending: s.duration_s, idle: 0 }[s.mode];
  $('#status-samples').textContent = s.mode === 'idle' ? 0 : s.samples_saved;
  $('#status-rate').textContent = s.mode === 'recording' ? s.samples_per_sec : '-';
  $('#status-gaps').textContent = s.gap_count > 0 ? `${s.gap_count} samples missed` : '';

  $('#setup').hidden = s.mode !== 'idle';
  $('#start-btn').disabled = s.mode !== 'idle';
  $('#stop-btn').disabled = s.mode !== 'recording';
  $('#stomp').hidden = !(s.mode === 'recording' && s.elapsed < STOMP_SECONDS);
  $('#count').hidden = s.mode !== 'pending';
  if (s.mode === 'pending') {
    fillCountForm(s);
    $('#count-duration').textContent = s.duration_s;
  } else {
    shownPending = null;
  }

  $('#trial-count').textContent = s.trial_count;
  $('#recent').innerHTML = s.recent_trials
    .map((t) => `<tr><td>${t.file.replace(/\.csv$/, '')}</td><td>${t.steps}</td><td>${t.distance_m}</td><td>${t.duration_s}</td></tr>`)
    .join('');
  $('#delete-btn').disabled = s.mode !== 'idle' || s.recent_trials.length === 0;
}

setInterval(refresh, 500);
refresh();
