// PGAS live dashboard. Served by the arduino:web_ui brick on the board (port 7000).
// Messages come from pgas/web.py (LiveFeed): pgas_sample, pgas_history, pgas_job.
// No CDN: socket.io.min.js and arduino.js (the WebUI client) ship in libs/.

const STALE_MS = 3000;           // no sample for 3 s -> "check the board" warning
const WINDOW_MS = 5 * 60 * 1000; // chart window: the last 5 minutes
const GAS = ['mq135_v', 'mq3_v', 'mq2_v'];
const COLOR_VAR = { mq135_v: '--c-mq135', mq3_v: '--c-mq3', mq2_v: '--c-mq2' };

const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------ language (English / 繁體中文)
const I18N = {
  en: {
    live: 'live', sub: 'What the sensors smell right now',
    connecting: 'Connecting to the board…',
    connected_wait: 'Connected. Waiting for the first reading…',
    disconnected: 'Lost the connection to the board. Reconnecting…',
    no_client: 'This page must be opened from the board (http://<board-name>.local:7000).',
    ok: (s) => `Live · last update ${s} s ago`,
    live_ok: 'Receiving live data from the board.', live_stale: 'No data from the board. Check power, Wi-Fi and the PGAS app.',
    stale: (s) => `No data for ${s} s – check the board (power, Wi-Fi, PGAS app running).`,
    g_mq135: 'Ammonia / sulfides', g_mq3: 'Ethanol (alcohol)', g_mq2: 'Broad VOCs', g_dht: 'Air in the box',
    ago5: '5 min ago', now: 'now',
    dht_fail: 'The temperature sensor did not answer.',
    hint: "Each gas sensor's voltage goes up when it smells its gas. Values are the MQ module output in volts, before the 10 kΩ / 20 kΩ divider.",
    job_h: 'Current test', job_done: 'Last test', grade: 'Grade', advice: 'Advice', failed: 'Stopped',
    retest: 'please re-test',
    foot: 'Served by the board over Wi-Fi · works offline', raw: 'raw',
    check_h: 'Is this food still good?',
    check_help: 'The three gas sensors are tested one at a time: each reads clean air for 3 s, goes into the bag with the food, and is measured for 5 s. The page tells you what to do at every step.',
    check_btn: 'Start test', checking: 'Testing…', next_btn: (n) => `Ready – test ${n}`, cancel: 'Cancel',
    st_active: 'testing', st_next: 'next',
    sensor_of: (k) => `Sensor ${k} of 3`,
    in_idle: 'Hold MQ-135 outside the bag in clean air, then press Start test.',
    in_baseline: (n) => `Hold ${n} outside the bag, in clean air`,
    in_move: (n) => `Put ${n} into the bag now and close it around the sensor`,
    in_measure: (n) => `Measuring ${n} in the bag – keep it still`,
    in_wait: (n, p) => `${p} done ✓ Take ${p} out of the bag, hold ${n} outside in clean air, then press the button.`,
    ph_starting: 'Starting…', ph_baseline: 'A · Hold the box in clean air, away from food',
    ph_move: 'M · Move the box over the food now', ph_expose: 'H · Hold still over the food',
    ph_recover: 'V · Lift the box away and let it air out', ph_analyse: 'Analysing the smell…',
    ph_done: 'Done', ph_stopped: 'Stopped',
    res_good: 'Food looks fine', res_good_d: 'No spoilage gases above the clean-air level.',
    res_bad: 'Food has gone bad', res_bad_d: 'Strong spoilage gases. Do not eat or sell it.',
    res_spoiling: 'Spoilage gases are rising. It is starting to go off.',
    res_retest: 'Please test again', res_busy: 'Another test is running. Wait for it to finish.',
    res_rule: 'Judged from the three gas sensors (MQ-135, MQ-3, MQ-2) with a provisional rule.',
    disclaimer: 'Disclaimer: this site is for reference only. If you have any concern, ask a medical professional. Do not eat food based on this result alone.',
    not_connected: 'Not connected to the board yet.',
    cmd_failed: (e) => `The board could not start it: ${e}`,
  },
  zh: {
    live: '即時', sub: '感測器現在聞到的氣味',
    connecting: '正在連線到板子…',
    connected_wait: '已連線，等待第一筆讀數…',
    disconnected: '與板子的連線中斷，正在重新連線…',
    no_client: '請從板子開啟這個頁面（http://<板子名稱>.local:7000）。',
    ok: (s) => `即時 · ${s} 秒前更新`,
    live_ok: '正在接收板子的即時資料。', live_stale: '板子沒有傳來資料，請檢查電源、Wi-Fi 和 PGAS 程式。',
    stale: (s) => `已經 ${s} 秒沒有資料 – 請檢查板子（電源、Wi-Fi、PGAS 程式是否在執行）。`,
    g_mq135: '氨氣／硫化物', g_mq3: '乙醇（酒精）', g_mq2: '揮發性有機物（VOCs）', g_dht: '盒內空氣',
    ago5: '5 分鐘前', now: '現在',
    dht_fail: '溫濕度感測器沒有回應。',
    hint: '每顆氣體感測器聞到對應氣體時電壓會上升。數值是 MQ 模組的輸出電壓（伏特），在 10 kΩ / 20 kΩ 分壓之前。',
    job_h: '目前的測試', job_done: '上一次測試', grade: '等級', advice: '建議', failed: '已中斷',
    retest: '請重新測試',
    foot: '由板子透過 Wi-Fi 提供 · 不需要網際網路', raw: '原始值',
    check_h: '這份食物還能吃嗎？',
    check_help: '三顆氣體感測器會依序測：每顆先在乾淨空氣中量 3 秒，再放進裝食物的袋子裡量 5 秒。每一步頁面都會告訴你要做什麼。',
    check_btn: '開始測試', checking: '測試中…', next_btn: (n) => `準備好了，測 ${n}`, cancel: '取消',
    st_active: '測試中', st_next: '下一個',
    sensor_of: (k) => `第 ${k} / 3 顆感測器`,
    in_idle: '先把 MQ-135 拿在袋子外的乾淨空氣中，再按「開始測試」。',
    in_baseline: (n) => `把 ${n} 拿在袋子外的乾淨空氣中`,
    in_move: (n) => `現在把 ${n} 放進袋子裡，袋口收緊包住感測器`,
    in_measure: (n) => `${n} 在袋子裡量測中，請保持不動`,
    in_wait: (n, p) => `${p} 完成 ✓ 把 ${p} 拿出袋子，把 ${n} 拿在袋子外的乾淨空氣中，準備好後按下面的按鈕。`,
    ph_starting: '準備中…', ph_baseline: 'A · 盒子拿在乾淨空氣中，遠離食物',
    ph_move: 'M · 現在把盒子移到食物上方', ph_expose: 'H · 在食物上方保持不動',
    ph_recover: 'V · 把盒子移開，讓它散味', ph_analyse: '正在分析氣味…',
    ph_done: '完成', ph_stopped: '已中斷',
    res_good: '食物沒壞', res_good_d: '沒有偵測到高於乾淨空氣的腐敗氣體。',
    res_bad: '食物壞了', res_bad_d: '偵測到明顯的腐敗氣體，請不要食用或販售。',
    res_spoiling: '腐敗氣體正在上升，食物開始變質。',
    res_retest: '請重新測試', res_busy: '另一個測試正在進行，請等它結束。',
    res_rule: '依三顆氣體感測器（MQ-135、MQ-3、MQ-2）以暫定規則判斷。',
    disclaimer: '免責聲明：本網站僅提供參考，若有問題請洽專業醫師指示，請勿僅依此結果自行食用。',
    not_connected: '還沒連上板子。',
    cmd_failed: (e) => `板子無法開始：${e}`,
  },
};
let lang = 'en';
const T = (k) => I18N[lang][k];

function setLang(l) {
  lang = l === 'zh' ? 'zh' : 'en';
  document.documentElement.lang = lang === 'zh' ? 'zh-Hant-TW' : 'en';
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const v = T(el.dataset.i18n);
    if (typeof v === 'string') el.textContent = v;
  });
  $('lang-en').setAttribute('aria-pressed', String(lang === 'en'));
  $('lang-zh').setAttribute('aria-pressed', String(lang === 'zh'));
  try { localStorage.setItem('pgas-lang', lang); } catch (e) { /* storage unavailable */ }
  renderStatus();
  renderJob();
  renderRaw();
}

function initialLang() {
  try { const saved = localStorage.getItem('pgas-lang'); if (saved) return saved; } catch (e) { /* storage unavailable */ }
  return (navigator.language || '').toLowerCase().startsWith('zh') ? 'zh' : 'en';
}

// ------------------------------------------------------------ state
const series = { mq135_v: [], mq3_v: [], mq2_v: [] }; // [{t: local ms, v}]
let lastAt = 0;          // local time (ms) the last sample arrived
let skewMs = null;       // local clock minus board clock, from the latest sample
let conn = 'connecting'; // connecting | connected | disconnected | no_client
let job = null;          // {id, kind, phase, i, n, pct, done, grade, state}
let lastRaw = null;      // [a0, a1, a2] of the last sample

function toLocal(ts) {
  return ts * 1000 + (skewMs ?? 0);
}

function addSample(p, live) {
  if (!p || typeof p.ts !== 'number') return;
  if (live) {
    skewMs = Date.now() - p.ts * 1000;
    lastAt = Date.now();
  }
  const t = toLocal(p.ts);
  for (const k of GAS) {
    const v = p[k];
    if (typeof v !== 'number' || !isFinite(v)) continue;
    const s = series[k];
    if (s.length && t <= s[s.length - 1].t) continue; // history overlap
    s.push({ t, v });
  }
  if (live) showValues(p);
}

function trim(now) {
  for (const k of GAS) {
    const s = series[k];
    let i = 0;
    while (i < s.length && s[i].t < now - WINDOW_MS) i++;
    if (i) s.splice(0, i);
  }
}

// ------------------------------------------------------------ rendering
function fmt(v, nd) {
  return typeof v === 'number' && isFinite(v) ? v.toFixed(nd) : '—';
}

function showValues(p) {
  for (const k of GAS) $(`v-${k}`).textContent = fmt(p[k], 2);
  const dhtOk = !!p.dht_ok && typeof p.temp_c === 'number';
  $('v-temp').textContent = dhtOk ? fmt(p.temp_c, 1) : '—';
  $('v-rh').textContent = dhtOk ? fmt(p.rh_pct, 0) : '—';
  $('dht-note').hidden = dhtOk;
  if (Array.isArray(p.raw)) { lastRaw = p.raw; renderRaw(); }
  if (p.job && (!job || job.done) && !pending && p.job.startsWith('bag')) {
    job = { id: p.job.split(' ').pop(), kind: 'bag', done: false };
    renderJob();
  }
}

function renderRaw() {
  $('raw').textContent = lastRaw ? `${T('raw')} A0/A1/A2: ${lastRaw.join(' / ')}` : '';
}

function renderStatus() {
  const el = $('status');
  const txt = $('status-text');
  let cls = 'wait';
  let msg = T('connecting');
  const age = lastAt ? Date.now() - lastAt : null;
  if (conn === 'no_client') {
    cls = 'stale'; msg = T('no_client');
  } else if (age !== null && age > STALE_MS) {
    cls = 'stale'; msg = T('stale')(Math.floor(age / 1000));
  } else if (age !== null) {
    cls = 'ok'; msg = T('ok')(Math.floor(age / 1000));
  } else if (conn === 'connected') {
    msg = T('connected_wait');
  } else if (conn === 'disconnected') {
    msg = T('disconnected');
  }
  if (conn === 'disconnected' && (age === null || age > STALE_MS)) {
    cls = 'stale';
    msg = age === null ? T('disconnected') : `${T('stale')(Math.floor(age / 1000))} ${T('disconnected')}`;
  }
  el.className = `status ${cls}`;
  if (txt.textContent !== msg) txt.textContent = msg;
  const state = cls === 'ok' ? T('live_ok') : cls === 'stale' ? T('live_stale') : msg;
  const live = $('status-live');
  if (live.textContent !== state) live.textContent = state;
  document.querySelector('.tiles').classList.toggle('stale-data', cls === 'stale');
}

// ------------------------------------------------------------ guided bag test, one sensor at a time
// pgas.session.run_bag: for each sensor, 3 s clean air -> 3 s into the bag -> 5 s measuring,
// then the operator swaps sensors and presses Next.
const SENSORS = ['mq135', 'mq3', 'mq2'];
const NAMES = { mq135: 'MQ-135', mq3: 'MQ-3', mq2: 'MQ-2' };
const STEP_SHARE = { baseline: [0, 3 / 11], move: [3 / 11, 6 / 11], measure: [6 / 11, 1], wait: [0, 0] };
let ui = null;
let pending = false;    // a command was sent and has not been answered by a job update
let shownResult = null; // id of the job whose result pop-up was shown

function say(text, err) {
  const el = $('start-msg');
  el.textContent = text || '';
  el.classList.toggle('err', !!err);
}

const running = () => !!(job && !job.done && job.kind === 'bag');
const waiting = () => running() && job.step === 'wait';

function renderSteps() {
  const k = running() ? SENSORS.indexOf(job.s) : -1;
  document.querySelectorAll('#steps li').forEach((li, i) => {
    let st = 'todo';
    if (job && job.done && job.kind === 'bag' && job.state === 'done') st = 'done';
    else if (k >= 0) st = i < k ? 'done' : i === k ? (job.step === 'wait' ? 'next' : 'active') : 'todo';
    li.className = st;
    const r = job && job.done && job.rises_v ? Number(job.rises_v[SENSORS[i]]) : NaN;
    li.querySelector('.st').textContent = st === 'done' ? (Number.isFinite(r) ? `${r >= 0 ? '+' : ''}${r.toFixed(2)} V` : '✓')
      : st === 'active' ? T('st_active') : st === 'next' ? T('st_next') : '';
  });
}

function renderButtons() {
  const btn = $('check-btn');
  const online = conn === 'connected';
  if (waiting()) {
    btn.disabled = !online || pending;
    btn.textContent = T('next_btn')(NAMES[job.s]);
  } else if (running()) {
    btn.disabled = true;
    btn.textContent = T('checking');
  } else {
    btn.disabled = !online || pending;
    btn.textContent = pending ? T('checking') : T('check_btn');
  }
  $('cancel-btn').hidden = !running();
}

function renderJob() {
  const box = $('progress');
  const instr = $('instr');
  if (running()) {
    box.hidden = false;
    const k = Math.max(0, SENSORS.indexOf(job.s));
    const [a, b] = STEP_SHARE[job.step] || [0, 0];
    const f = job.n ? Math.min(1, (job.i + 1) / job.n) : 0;
    const pct = job.step === 'wait' ? (k / 3) * 100 : ((k + a + (b - a) * f) / 3) * 100;
    $('bar-fill').style.width = `${pct}%`;
    $('bar').setAttribute('aria-valuenow', String(Math.round(pct)));
    const left = job.step !== 'wait' && job.n ? Math.max(0, job.n - job.i) : null;
    $('phase-text').textContent = `${T('sensor_of')(k + 1)}${left !== null ? ` · ${left} s` : ''}`;
    const name = NAMES[job.s];
    const prev = k > 0 ? NAMES[SENSORS[k - 1]] : '';
    instr.textContent = T(`in_${job.step}`)(name, prev);
    instr.className = `instr ${job.step}`;
  } else if (job && job.done && job.kind === 'bag' && job.state === 'done') {
    box.hidden = false;
    $('bar-fill').style.width = '100%';
    $('phase-text').textContent = T('ph_done');
    instr.textContent = '';
    instr.className = 'instr';
  } else {
    box.hidden = true;
    instr.textContent = T('in_idle');
    instr.className = 'instr';
  }
  renderSteps();
  renderButtons();
}

function showResult(m) {
  if (!m || shownResult === m.id) return;
  shownResult = m.id;
  const box = $('result');
  let cls, title, detail = '';
  if (m.state === 'done' && m.grade) {
    const ok = m.grade === 'FRESH';
    cls = ok ? 'good' : 'bad';
    title = ok ? T('res_good') : T('res_bad');
    detail = m.grade === 'SPOILING' ? T('res_spoiling') : ok ? T('res_good_d') : T('res_bad_d');
  } else if (m.state === 'rejected') {
    cls = 'warn'; title = T('res_busy');
  } else if (m.state === 'failed' && !m.retest && /stopped/.test(m.error || '')) {
    return; // cancelled by the user: no pop-up
  } else {
    cls = 'warn'; title = T('res_retest');
    detail = m.error ? String(m.error) : '';
  }
  box.querySelector('.modal').className = `modal ${cls}`;
  $('result-icon').textContent = cls === 'good' ? '✓' : cls === 'bad' ? '✕' : '!';
  $('result-title').textContent = title;
  $('result-detail').textContent = detail;
  const r = m.rises_v;
  const vals = r ? SENSORS.filter((s) => r[s] !== undefined && r[s] !== null)
    .map((s) => `${NAMES[s]} ${r[s] >= 0 ? '+' : ''}${Number(r[s]).toFixed(2)} V`).join(' · ') : '';
  $('result-note').textContent = [vals, m.method === 'rule' ? T('res_rule') : ''].filter(Boolean).join('\n');
  box.hidden = false;
  requestAnimationFrame(() => box.classList.add('show'));
  $('result-ok').focus();
}

function closeResult() {
  const box = $('result');
  box.classList.remove('show');
  setTimeout(() => { box.hidden = true; $('check-btn').focus(); }, 200);
}

function onJob(m) {
  if (!m) return;
  pending = false;
  if (m.state === 'running') {
    const same = job && job.id === m.id;
    job = Object.assign(same ? job : { id: m.id, kind: m.kind }, { done: false });
    if (m.phase && m.phase.includes(':')) {
      const [step, sensor] = m.phase.split(':');
      Object.assign(job, { step, s: sensor, i: m.i, n: m.n });
    }
  } else {
    job = Object.assign({}, job && job.id === m.id ? job : { id: m.id, kind: m.kind }, m, { done: true });
    if (m.kind === 'bag' || m.state === 'rejected') showResult(m);
  }
  renderJob();
}

function send(cmd) {
  if (!ui || conn !== 'connected') { say(T('not_connected'), true); return; }
  say('');
  pending = true;
  renderButtons();
  ui.send_message('pgas_command', cmd);
  setTimeout(() => { if (pending) { pending = false; renderButtons(); } }, 6000);
}

function wireButtons() {
  $('check-btn').addEventListener('click', () => {
    if (waiting()) { send({ action: 'next' }); return; }
    job = null;
    send({ action: 'check' });
    renderJob();
  });
  $('cancel-btn').addEventListener('click', () => send({ action: 'stop' }));
  $('result-ok').addEventListener('click', closeResult);
  $('result').addEventListener('click', (e) => { if (e.target === $('result')) closeResult(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('result').hidden) closeResult(); });
}

function onReply(r) {
  if (r && !r.ok) { pending = false; say(T('cmd_failed')(r.error), true); }
  renderButtons();
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function drawChart(key, now) {
  const cv = $(`c-${key}`);
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  if (!w || !h) return;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
  }
  const g = cv.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);

  const s = series[key];
  const padL = 34, padR = 4, padT = 6, padB = 6;
  const pw = w - padL - padR, ph = h - padT - padB;
  let lo = Infinity, hi = -Infinity;
  for (const p of s) { if (p.v < lo) lo = p.v; if (p.v > hi) hi = p.v; }
  if (!s.length) { lo = 0; hi = 1; }
  const span = Math.max(hi - lo, 0.1); // at least 0.1 V so sensor noise stays flat
  const mid = (hi + lo) / 2;
  lo = Math.max(0, mid - span * 0.6); hi = lo + span * 1.2;

  const x = (t) => padL + ((t - (now - WINDOW_MS)) / WINDOW_MS) * pw;
  const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * ph;

  // grid + labels
  g.strokeStyle = cssVar('--line'); g.lineWidth = 1;
  g.fillStyle = cssVar('--muted'); g.font = '11px ui-monospace, Menlo, monospace';
  g.textAlign = 'right'; g.textBaseline = 'middle';
  for (let i = 0; i <= 2; i++) {
    const v = lo + ((hi - lo) * i) / 2;
    const yy = Math.round(y(v)) + 0.5;
    g.beginPath(); g.moveTo(padL, yy); g.lineTo(w - padR, yy); g.stroke();
    g.fillText(v.toFixed(2), padL - 4, yy);
  }
  for (let m = 1; m < 5; m++) {
    const xx = Math.round(x(now - m * 60000)) + 0.5;
    g.globalAlpha = 0.5;
    g.beginPath(); g.moveTo(xx, padT); g.lineTo(xx, h - padB); g.stroke();
    g.globalAlpha = 1;
  }
  if (!s.length) return;

  // line; break it where samples are more than 5 s apart (board stopped sending)
  g.strokeStyle = cssVar(COLOR_VAR[key]); g.lineWidth = 2; g.lineJoin = 'round';
  g.beginPath();
  let prev = null;
  for (const p of s) {
    if (prev && p.t - prev.t > 5000) g.moveTo(x(p.t), y(p.v));
    else if (!prev) g.moveTo(x(p.t), y(p.v));
    else g.lineTo(x(p.t), y(p.v));
    prev = p;
  }
  g.stroke();
  const last = s[s.length - 1];
  g.fillStyle = g.strokeStyle;
  g.beginPath(); g.arc(x(last.t), y(last.v), 3, 0, Math.PI * 2); g.fill();
}

function tick() {
  const now = Date.now();
  trim(now);
  renderStatus();
  for (const k of GAS) drawChart(k, now);
}

// ------------------------------------------------------------ wiring
function connect() {
  if (typeof WebUI === 'undefined' || typeof io === 'undefined') {
    conn = 'no_client';
    return;
  }
  ui = new WebUI();
  ui.on_connect(() => { conn = 'connected'; renderStatus(); renderButtons(); });
  ui.on_disconnect(() => { conn = 'disconnected'; renderStatus(); renderButtons(); });
  ui.on_message('pgas_command_reply', onReply);
  ui.on_message('pgas_sample', (p) => { addSample(p, true); tick(); });
  ui.on_message('pgas_history', (m) => {
    const list = (m && m.samples) || [];
    if (list.length) {
      const latest = list[list.length - 1];
      if (skewMs === null) skewMs = Date.now() - latest.ts * 1000;
      for (const p of list) addSample(p, false);
      if (!lastAt) showValues(latest);
    }
    if (m && m.last_job && !job) { shownResult = m.last_job.id; onJob(m.last_job); }
    tick();
  });
  ui.on_message('pgas_job', onJob);
}

document.addEventListener('DOMContentLoaded', () => {
  $('lang-en').addEventListener('click', () => setLang('en'));
  $('lang-zh').addEventListener('click', () => setLang('zh'));
  setLang(initialLang());
  wireButtons();
  connect();
  renderButtons();
  tick();
  setInterval(tick, 500);
  document.addEventListener('visibilitychange', tick);
  window.addEventListener('resize', tick);
});
