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
