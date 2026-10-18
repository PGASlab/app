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
    start_h: 'Test food', food_l: 'Food name (English letters)', state_l: 'Condition',
    st_fresh: 'Fresh', st_spoiling: 'Going off', st_spoiled: 'Spoiled', st_swill: 'Food waste',
    st_test: 'Just testing (not used for training)',
    start_btn: 'Start test', selftest_btn: 'Self-test', stop_btn: 'Stop',
    start_help: "Follow the letter on the board's LED matrix: A = hold in clean air, M = move over the food, H = hold still, V = lift away.",
    sent: (l) => `Sent: ${l}. Starting on the board…`, sent_other: 'Sent to the board.',
    bad_food: 'Type the food name in English letters or numbers, e.g. soymilk_soup.',
    bad_state: 'Pick a condition.', not_connected: 'Not connected to the board yet.',
    cmd_failed: (e) => `The board could not start it: ${e}`, busy: 'Another test is running. Press Stop first.',
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
    start_h: '測試食物', food_l: '食物名稱（英文字母）', state_l: '狀態',
    st_fresh: '新鮮', st_spoiling: '快壞了', st_spoiled: '壞掉了', st_swill: '廚餘',
    st_test: '只是測試（不拿去訓練）',
    start_btn: '開始測試', selftest_btn: '自我檢測', stop_btn: '停止',
    start_help: '照板子 LED 矩陣上的字母做：A = 拿在乾淨空氣中，M = 移到食物上方，H = 保持不動，V = 移開散味。',
    sent: (l) => `已送出：${l}，板子正在開始…`, sent_other: '已送到板子。',
    bad_food: '請用英文字母或數字輸入食物名稱，例如 soymilk_soup。',
    bad_state: '請選擇狀態。', not_connected: '還沒連上板子。',
    cmd_failed: (e) => `板子無法開始：${e}`, busy: '另一個測試正在進行，請先按「停止」。',
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
let job = null;          // {name, line, done}
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
  if (p.job && (!job || job.done || job.name !== p.job)) {
    job = { name: p.job, line: job && job.name === p.job ? job.line : '', done: false };
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

function renderJob() {
  const box = $('job');
  if (!job) { box.hidden = true; return; }
  box.hidden = false;
  box.querySelector('h2').textContent = job.done ? T('job_done') : T('job_h');
  $('job-name').textContent = job.name || '';
  $('job-line').textContent = job.line || '';
  const res = $('job-result');
  res.className = 'job-result';
  if (job.done && job.grade) {
    res.hidden = false;
    res.classList.add(job.grade);
    res.textContent = `${T('grade')}: ${job.grade}${job.advice ? ` · ${T('advice')}: ${job.advice}` : ''}`;
  } else if (job.done && job.state === 'rejected') {
    res.hidden = false;
    res.classList.add('rejected');
    res.textContent = T('busy');
  } else if (job.done && job.state === 'failed') {
    res.hidden = false;
    res.classList.add('failed');
    res.textContent = `${T('failed')}${job.error ? `: ${job.error}` : ''}${job.retest ? ` – ${T('retest')}` : ''}`;
  } else {
    res.hidden = true;
  }
}

function onJob(m) {
  if (!m) return;
  pending = false;
  const name = `${m.kind} job ${m.id}`;
  if (m.state === 'running') {
    job = { name, line: m.line, done: false };
  } else {
    job = Object.assign({}, job && job.name === name ? job : { name, line: '' }, m, { name, done: true });
  }
  renderJob();
  renderButtons();
}

// ------------------------------------------------------------ start / self-test / stop
let ui = null;
let pending = false; // a command was sent and its job has not started yet

const FOOD_RE = /^[a-z0-9]+(?:_[a-z0-9]+)*$/;
function cleanFood(v) {
  return String(v || '').trim().toLowerCase().replace(/[\s-]+/g, '_').replace(/^_+|_+$/g, '');
}

function say(text, err) {
  const el = $('start-msg');
  el.textContent = text || '';
  el.classList.toggle('err', !!err);
}

function renderButtons() {
  const online = conn === 'connected';
  const running = !!(job && !job.done);
  $('start-btn').disabled = !online || running || pending;
  $('selftest-btn').disabled = !online || running || pending;
  $('stop-btn').disabled = !online;
}

function send(cmd) {
  if (!ui || conn !== 'connected') { say(T('not_connected'), true); return false; }
  pending = true;
  renderButtons();
  ui.send_message('pgas_command', cmd);
  setTimeout(() => { pending = false; renderButtons(); }, 4000);
  return true;
}

function onReply(r) {
  if (!r) return;
  if (r.ok) {
    say(r.label ? T('sent')(r.label) : T('sent_other'));
  } else {
    pending = false;
    const e = r.error === 'bad_food' ? T('bad_food') : r.error === 'bad_state' ? T('bad_state') : T('cmd_failed')(r.error);
    say(e, true);
  }
  renderButtons();
}

function wireButtons() {
  const food = $('food');
  food.addEventListener('input', () => food.removeAttribute('aria-invalid'));
  $('start-form').addEventListener('submit', (ev) => {
    ev.preventDefault();
    const f = cleanFood(food.value);
    if (!f || f.length > 40 || !FOOD_RE.test(f)) {
      food.setAttribute('aria-invalid', 'true');
      say(T('bad_food'), true);
      food.focus();
      return;
    }
    food.value = f;
    send({ action: 'hood', food: f, state: $('state').value });
  });
  $('selftest-btn').addEventListener('click', () => send({ action: 'selftest' }));
  $('stop-btn').addEventListener('click', () => send({ action: 'stop' }));
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
    if (m && m.last_job && !job) onJob(m.last_job);
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
