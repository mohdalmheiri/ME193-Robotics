const personInput = document.querySelector('#person');
const activityButtons = document.querySelectorAll('.activity-btn');
const startBtn = document.querySelector('#start-btn');
const stopBtn = document.querySelector('#stop-btn');

let selectedActivity = 'Standing';

activityButtons.forEach((btn) => {
  if (btn.dataset.activity === selectedActivity) btn.classList.add('selected');
  btn.addEventListener('click', () => {
    selectedActivity = btn.dataset.activity;
    activityButtons.forEach((b) => b.classList.toggle('selected', b === btn));
  });
});

startBtn.addEventListener('click', async () => {
  const person = personInput.value || 'anonymous';
  const url = `/start?person=${encodeURIComponent(person)}&activity=${encodeURIComponent(selectedActivity)}`;
  await fetch(url);
});

stopBtn.addEventListener('click', async () => {
  await fetch('/stop');
});

async function refreshStatus() {
  try {
    const response = await fetch('/status');
    const s = await response.json();
    document.querySelector('#status-activity').textContent = s.recording ? s.activity : '-';
    document.querySelector('#status-time').textContent = s.elapsed;
    document.querySelector('#status-samples').textContent = s.samples_saved;
    document.querySelector('#status-rate').textContent = s.samples_per_sec;

    const gapsEl = document.querySelector('#status-gaps');
    gapsEl.textContent = s.gap_count > 0 ? `${s.gap_count} samples missed` : '';

    startBtn.disabled = s.recording;
    stopBtn.disabled = !s.recording;
  } catch (e) {
    // Board unreachable for a moment; try again on the next tick.
  }
}

setInterval(refreshStatus, 500);
refreshStatus();

// ---- Record / Live tabs (the last one used is remembered on this phone) ----
const tabs = document.querySelectorAll('.tab');
let currentView = 'record';
try {
  currentView = localStorage.getItem('view') || 'record';
} catch (e) {}

function showView(view) {
  currentView = view;
  tabs.forEach((t) => t.classList.toggle('selected', t.dataset.view === view));
  document.querySelector('#record-view').hidden = view !== 'record';
  document.querySelector('#live-view').hidden = view !== 'live';
  try {
    localStorage.setItem('view', view);
  } catch (e) {}
  if (view === 'live') refreshLive();
}

tabs.forEach((t) => t.addEventListener('click', () => showView(t.dataset.view)));
showView(currentView);

// ---- Live view ----
const LETTER = { Standing: 'S', Walking: 'W', Running: 'R', Biking: 'B' };

function setGuess(el, activity) {
  el.textContent = activity;
  el.className = `guess ${activity.toLowerCase()}`;
}

async function refreshLive() {
  if (currentView !== 'live') return;
  try {
    const response = await fetch('/live');
    const live = await response.json();
    document.querySelector('#live-waiting').hidden = live.ready;
    if (!live.ready) return;

    const m1 = live.model1;
    setGuess(document.querySelector('#m1-guess'), m1.guess);
    document.querySelector('#m1-axis').textContent = m1.axis;
    document.querySelector('#m1-axis2').textContent = m1.axis;
    document.querySelector('#m1-peak').textContent = m1.peak.toFixed(2);
    // e.g. "Standing ≤ 0.31 < Walking ≤ 2.00 < Biking"
    document.querySelector('#m1-bands').textContent = m1.classes
      .map((c, i) => (i < m1.thresholds.length ? `${c} ≤ ${m1.thresholds[i].toFixed(2)} <` : c))
      .join(' ');
    document.querySelector('#m1-recent').textContent = m1.recent.map((a) => LETTER[a]).join(' ');

    const m2 = live.model2;
    setGuess(document.querySelector('#m2-guess'), m2.guess);
    document.querySelector('#m2-rotation').textContent = m2.rotation.toFixed(0);
    document.querySelector('#m2-bumpiness').textContent = m2.bumpiness.toFixed(2);
    document.querySelector('#m2-smoothness').textContent = m2.smoothness.toFixed(0);
    document.querySelector('#m2-recent').textContent = m2.recent.map((a) => LETTER[a]).join(' ');
  } catch (e) {
    // Board unreachable for a moment; try again on the next tick.
  }
}

setInterval(refreshLive, 500);
