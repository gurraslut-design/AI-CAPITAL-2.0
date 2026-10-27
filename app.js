const form = document.querySelector('#taskForm');
const input = document.querySelector('#taskInput');
const tasksEl = document.querySelector('#tasks');
const countEl = document.querySelector('#taskCount');
const activityEl = document.querySelector('#activity');
const runBtn = document.querySelector('#runWorkflow');
const exportBtn = document.querySelector('#exportReport');
const workflowOutput = document.querySelector('#workflowOutput');
const backendInput = document.querySelector('#backendUrl');
const connectBtn = document.querySelector('#connectBackend');
const backendStatus = document.querySelector('#backendStatus');

let tasks = [];
let events = [];
let latestReport = null;
let backendUrl = '';
let backendConnected = false;

function log(message) {
  events.unshift({ message, time: new Date().toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' }) });
  events = events.slice(0, 8);
  renderEvents();
  persist();
}
function renderEvents() {
  activityEl.replaceChildren();
  if (!events.length) {
    const p = document.createElement('p');
    p.className = 'muted';
    p.textContent = 'Arbetsloggen visas här när du lägger till uppgifter.';
    activityEl.append(p);
    return;
  }
  for (const event of events) {
    const div = document.createElement('div');
    div.className = 'event';
    div.append(document.createTextNode(event.message));
    const time = document.createElement('time');
    time.textContent = event.time;
    div.append(time);
    activityEl.append(div);
  }
}
function persist() {
  try {
    localStorage.setItem('aiCapitalLabTasks', JSON.stringify(tasks));
    localStorage.setItem('aiCapitalLabEvents', JSON.stringify(events));
    localStorage.setItem('aiCapitalLabBackendUrl', backendUrl);
  } catch (_) {}
}
function renderTasks() {
  tasksEl.replaceChildren();
  countEl.textContent = String(tasks.length);
  if (!tasks.length) {
    const div = document.createElement('div');
    div.className = 'empty';
    div.textContent = 'Lägg till den första uppgiften för att komma igång.';
    tasksEl.append(div);
    return;
  }
  for (const task of tasks) {
    const row = document.createElement('div');
    row.className = 'task' + (task.done ? ' done' : '');
    const check = document.createElement('input');
    check.type = 'checkbox';
    check.checked = task.done;
    check.setAttribute('aria-label', 'Markera uppgift som klar');
    check.addEventListener('change', () => {
      task.done = check.checked;
      log((task.done ? 'Markerade klar: ' : 'Återöppnade: ') + task.text);
      renderTasks();
    });
    const text = document.createElement('span');
    text.className = 'task-text';
    text.textContent = task.text;
    const del = document.createElement('button');
    del.className = 'delete';
    del.type = 'button';
    del.textContent = 'Ta bort';
    del.addEventListener('click', () => {
      tasks = tasks.filter(item => item.id !== task.id);
      log('Tog bort uppgift: ' + task.text);
      renderTasks();
    });
    row.append(check, text, del);
    tasksEl.append(row);
  }
}
form.addEventListener('submit', event => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  tasks.push({ id: Date.now() + Math.random(), text, done: false });
  log('Ny uppgift: ' + text);
  input.value = '';
  renderTasks();
  input.focus();
});

function addStep(title, body, note) {
  const card = document.createElement('article');
  card.className = 'workflow-step';
  const heading = document.createElement('h3');
  heading.textContent = title;
  const paragraph = document.createElement('p');
  paragraph.textContent = body;
  const small = document.createElement('small');
  small.textContent = note;
  card.append(heading, paragraph, small);
  workflowOutput.append(card);
}
function showNotice(message) {
  const p = document.createElement('p');
  p.className = 'muted';
  p.textContent = message;
  workflowOutput.append(p);
}
function renderTemplateReport(topic) {
  latestReport = {
    title: 'Teamgenomgång: ' + topic,
    date: new Date().toLocaleString('sv-SE'),
    notice: 'Mallbaserad lokal genomgång. Inga externa AI-modeller har anropats.',
    steps: [
      { title: '1 · Coordinator — plan', body: 'Mål: ' + topic + '\nFöreslagen ordning: definiera målet och begränsningar → samla fakta → identifiera risker → välj nästa verifierbara åtgärd.', note: 'Planförslag, inte en färdig leverans.' },
      { title: '2 · Analyst — analys', body: 'Kontrollera vilka fakta som saknas, vilka antaganden som styr beslutet och hur resultat kan mätas. Dela upp arbetet i små testbara delar.', note: 'Ingen extern datainsamling utförd.' },
      { title: '3 · Developer — genomförandeplan', body: 'Dela upp arbetet i små ändringar eller experiment. Definiera hur varje del ska testas och vad som räknas som godkänt resultat.', note: 'Inga filer eller system har ändrats av den här mallen.' },
      { title: '4 · Independent Reviewer — motgranskning', body: 'Risker att kontrollera: obekräftade antaganden, saknade tester, kostnader och oavsiktliga sidoeffekter. Kräv evidens innan något markeras verifierat.', note: 'Granskningsmall; inte en separat AI-modell.' },
      { title: '5 · Coordinator — nästa steg', body: 'Välj en liten åtgärd, ange hur den ska testas och dokumentera utfallet. Markera uppgiften klar först när resultatet har kontrollerats.', note: 'Nästa steg behöver mänsklig bedömning.' }
    ]
  };
  renderReport(latestReport);
  log('Körde mallbaserad teamgenomgång');
}
function renderReport(report) {
  workflowOutput.replaceChildren();
  if (report.agents) {
    const labels = [
      ['coordinator', '1 · Coordinator — plan'],
      ['analyst', '2 · Analyst — analys'],
      ['developer', '3 · Developer — genomförandeplan'],
      ['reviewer', '4 · Independent Reviewer — motgranskning'],
      ['final', '5 · Coordinator — sammanställning']
    ];
    latestReport = {
      title: 'AI-teamrapport: ' + report.topic,
      date: report.completedAt || new Date().toISOString(),
      notice: 'AI-modellen har tagit fram fyra separata rollperspektiv och en slutlig sammanställning via den säkra backend-servern. Inga handelsorder har lagts.',
      steps: labels.map(([key, title]) => ({ title, body: report[key] || report.agents[key] || 'Inget svar returnerades.', note: 'Modellsvar. Kontrollera fakta innan beslut.' }))
    };
  } else {
    latestReport = report;
  }
  for (const step of latestReport.steps) addStep(step.title, step.body, step.note);
  showNotice(latestReport.notice);
}
function normalizeBackendUrl(value) {
  return value.trim().replace(/\/+$/, '');
}
async function testBackend() {
  backendUrl = normalizeBackendUrl(backendInput.value);
  if (!backendUrl) {
    backendConnected = false;
    backendStatus.textContent = 'Ange serverns bas-URL. Lägg aldrig in någon API-nyckel här.';
    persist();
    return false;
  }
  backendStatus.textContent = 'Testar anslutningen…';
  connectBtn.disabled = true;
  try {
    const response = await fetch(backendUrl + '/api/health', { method: 'GET' });
    if (!response.ok) throw new Error('Servern svarade med HTTP ' + response.status);
    const health = await response.json();
    if (!health.ok) throw new Error('Backend svarade, men är inte redo.');
    backendConnected = Boolean(health.modelConfigured);
    backendStatus.textContent = backendConnected
      ? 'Ansluten. Servern rapporterar att modellnyckel finns. Riktiga modell-anrop kan provas.'
      : 'Servern svarar, men saknar modellnyckel. Lägg till den som server-hemlighet hos driftleverantören.';
    log(backendConnected ? 'AI-backend ansluten' : 'Backend nådd, men modellnyckel saknas');
    persist();
    return backendConnected;
  } catch (error) {
    backendConnected = false;
    backendStatus.textContent = 'Kunde inte ansluta: ' + error.message + '. Kontrollera URL, driftstatus och CORS.';
    log('Backend-anslutning misslyckades');
    return false;
  } finally {
    connectBtn.disabled = false;
  }
}
connectBtn.addEventListener('click', testBackend);
backendInput.addEventListener('change', () => {
  backendUrl = normalizeBackendUrl(backendInput.value);
  backendConnected = false;
  persist();
});

runBtn.addEventListener('click', async () => {
  const open = tasks.filter(task => !task.done);
  const topic = open.length ? open.map(task => task.text).join('; ') : 'Granska AI Capital Lab och föreslå nästa utvecklingssteg';
  if (!backendUrl) {
    renderTemplateReport(topic);
    return;
  }
  runBtn.disabled = true;
  runBtn.textContent = 'Teamet arbetar…';
  workflowOutput.replaceChildren();
  showNotice('Skickar uppgiften till backend. En modellkörning tar fram fyra rollperspektiv och en kritisk granskning för att minska väntetid och kostnad.');
  try {
    const response = await fetch(backendUrl + '/api/team-run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'Servern svarade med HTTP ' + response.status);
    if (data.mode !== 'real-model-run') throw new Error('Servern bekräftade inte en riktig AI-körning.');
    renderReport(data);
    log('Körde AI-teamgenomgång via backend');
  } catch (error) {
    workflowOutput.replaceChildren();
    showNotice('Riktig AI-körning misslyckades: ' + error.message + ' — ingen mallrapport visas som om den vore ett AI-resultat.');
    log('AI-teamkörning misslyckades');
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = 'Kör teamgenomgång';
  }
});
exportBtn.addEventListener('click', () => {
  if (!latestReport) {
    log('Kör en teamgenomgång innan rapport exporteras');
    return;
  }
  const content = [latestReport.title, latestReport.date, latestReport.notice, '', ...latestReport.steps.flatMap(step => [step.title, step.body, step.note, ''])].join('\n');
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'ai-capital-lab-report.txt';
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  log('Exporterade teamrapport');
});

try {
  tasks = JSON.parse(localStorage.getItem('aiCapitalLabTasks') || '[]');
  events = JSON.parse(localStorage.getItem('aiCapitalLabEvents') || '[]');
  backendUrl = localStorage.getItem('aiCapitalLabBackendUrl') || '';
} catch (_) {
  tasks = [];
  events = [];
  backendUrl = '';
}
backendInput.value = backendUrl;
renderTasks();
renderEvents();
if (backendUrl) {
  backendStatus.textContent = 'Sparad backend-URL finns. Tryck ”Testa anslutning” för att kontrollera den.';
}
