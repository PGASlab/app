// PGAS dashboard. Served by the arduino:web_ui brick on the board (port 7000).
// From pgas/web.py: pgas_sample, pgas_history, pgas_job, pgas_command_reply.
// To the board: pgas_command {action: 'check' | 'next' | 'stop'}.
// No CDN: socket.io.min.js and arduino.js (the WebUI client) ship in libs/.

const STALE_MS = 3000;           // no sample for 3 s -> "check the board" warning
const WINDOW_MS = 5 * 60 * 1000; // sparkline window: the last 5 minutes
const GAS = ['mq135_v', 'mq3_v', 'mq2_v'];
const SENSORS = ['mq135', 'mq3', 'mq2'];
const KEY = { mq135: 'mq135_v', mq3: 'mq3_v', mq2: 'mq2_v' };
const NAMES = { mq135: 'MQ-135', mq3: 'MQ-3', mq2: 'MQ-2' };
const COLOR_VAR = { mq135_v: '--c-mq135', mq3_v: '--c-mq3', mq2_v: '--c-mq2' };
// Same thresholds as pgas/rules.py (rise above clean air, volts at the module output).
const WARN_V = 0.10;
const OVER_V = 0.20;
const DIAL_MAX_V = 0.50; // full scale of the dial (rise above clean air)
// pgas.session.run_bag: 1 s clean air -> 1 s into the bag -> 3 s measuring = 5 s per sensor.
const STEP_SHARE = { baseline: [0, 1 / 5], move: [1 / 5, 2 / 5], measure: [2 / 5, 1] };
const RING_LEN = 2 * Math.PI * 96;

const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------ language (English / 繁體中文)
const I18N = {
  en: {
    eyebrow: 'AI nose on Arduino UNO Q', test_h: 'Freshness test',
    connecting: 'Connecting…', connected_wait: 'Connected', disconnected: 'Reconnecting…',
    no_client: 'Open this page from the board', ok: 'Live',
    live_ok: 'Receiving live data from the board.', live_stale: 'No data from the board. Check power, Wi-Fi and the PGAS app.',
    stale: (s) => `No data for ${s} s`,
    live_h: 'Live readings',
    live_sub: 'The needle shows how far each sensor is above clean air. Green is normal, red means a strong smell.',
    g_mq135: 'Ammonia / sulfides', g_mq3: 'Ethanol (alcohol)', g_mq2: 'Broad VOCs', g_dht: 'Temperature & humidity',
    dht_fail: 'The temperature sensor did not answer.',
    above: (d) => `${d >= 0 ? '+' : '−'}${Math.abs(d).toFixed(2)} V vs clean air`,
    normal: (b) => `Normal ≤ ${b.toFixed(2)} V · clean air ${(b - WARN_V).toFixed(2)} V`,
    learning: 'Learning the clean-air level…',
    hint: 'Values are the MQ module output in volts, before the 10 kΩ / 20 kΩ divider. Clean air is estimated from the last few minutes, or measured at the start of each sensor in a test.',
    foot: 'Served by the board over Wi-Fi · works offline', raw: 'raw',
    check_h: 'Is this food still good?',
    check_help: 'Three gas sensors smell the food one at a time, 5 seconds each: a moment in clean air, then into the bag with the food. The page guides every step.',
    check_btn: 'Start test', checking: 'Testing…', next_btn: (n) => `Ready – test ${n}`, cancel: 'Cancel test',
    st_active: 'testing', st_next: 'next',
    sensor_of: (k) => `Sensor ${k} of 3`, sec: 'seconds',
    in_idle: 'Hold MQ-135 outside the bag in clean air, then press Start test.',
    in_baseline: (n) => `Hold ${n} outside the bag, in clean air`,
    in_move: (n) => `Put ${n} into the bag now`,
    in_measure: (n) => `Measuring ${n} – keep it still`,
    in_wait: (n, p) => `${p} done. Take it out, hold ${n} outside the bag, then tap the button.`,
    ring_baseline: 'clean air', ring_move: 'into the bag', ring_measure: 'measuring', ring_wait: 'swap sensor',
    ph_done: 'Done',
    res_good: 'Food looks fine', res_good_d: 'No spoilage gases above the clean-air level.',
    res_bad: 'Food has gone bad', res_bad_d: 'Strong spoilage gases. Do not eat or sell it.',
    res_spoiling: 'Spoilage gases are rising. It is starting to go off.',
    res_retest: 'Please test again', res_busy: 'Another test is running. Wait for it to finish.',
    res_rule: 'Judged from the three gas sensors (MQ-135, MQ-3, MQ-2) with a provisional rule.',
    ag_sense: 'Sense', ag_decide: 'Decide', ag_act: 'Act',
    ag_sense_t: '3 gas sensors, rise above clean air',
    ag_decide_t: (ms, g) => `${g} on the UNO Q, offline, in ${ms} ms`,
    act: { led_alarm: 'LED matrix alarm (flashing ✕)', led_ok: 'LED matrix ✓', alert_sent: 'alert sent to phone', alert_queued: 'alert queued (Telegram not set up)' },
    disclaimer: 'Disclaimer: this site is for reference only. If you have any concern, ask a medical professional. Do not eat food based on this result alone.',
    not_connected: 'Not connected to the board yet.',
    cmd_failed: (e) => `The board could not start it: ${e}`,
  },
  zh: {
    eyebrow: '跑在 Arduino UNO Q 上的 AI 鼻子', test_h: '新鮮度測試',
    connecting: '連線中…', connected_wait: '已連線', disconnected: '重新連線中…',
    no_client: '請從板子開啟此頁', ok: '即時',
    live_ok: '正在接收板子的即時資料。', live_stale: '板子沒有傳來資料，請檢查電源、Wi-Fi 和 PGAS 程式。',
    stale: (s) => `${s} 秒沒有資料`,
    live_h: '即時讀數',
    live_sub: '指針表示每顆感測器比乾淨空氣高出多少。綠色是正常，紅色代表氣味很重。',
    g_mq135: '氨氣／硫化物', g_mq3: '乙醇（酒精）', g_mq2: '揮發性有機物', g_dht: '溫度與濕度',
    dht_fail: '溫濕度感測器沒有回應。',
    above: (d) => `比乾淨空氣 ${d >= 0 ? '+' : '−'}${Math.abs(d).toFixed(2)} V`,
    normal: (b) => `正常範圍 ≤ ${b.toFixed(2)} V · 乾淨空氣 ${(b - WARN_V).toFixed(2)} V`,
    learning: '正在學習乾淨空氣的數值…',
    hint: '數值是 MQ 模組的輸出電壓（伏特），在 10 kΩ / 20 kΩ 分壓之前。乾淨空氣的數值由最近幾分鐘估算；測試時則以每顆感測器開始前量到的為準。',
    foot: '由板子透過 Wi-Fi 提供 · 不需要網際網路', raw: '原始值',
    check_h: '這份食物還能吃嗎？',
    check_help: '三顆氣體感測器依序聞，每顆只要 5 秒：先在乾淨空氣中一下，再放進裝食物的袋子裡。每一步都會帶著你做。',
    check_btn: '開始測試', checking: '測試中…', next_btn: (n) => `準備好了，測 ${n}`, cancel: '取消測試',
    st_active: '測試中', st_next: '下一個',
    sensor_of: (k) => `第 ${k} / 3 顆感測器`, sec: '秒',
    in_idle: '先把 MQ-135 拿在袋子外的乾淨空氣中，再按「開始測試」。',
    in_baseline: (n) => `把 ${n} 拿在袋子外的乾淨空氣中`,
    in_move: (n) => `現在把 ${n} 放進袋子裡`,
    in_measure: (n) => `${n} 量測中，請保持不動`,
    in_wait: (n, p) => `${p} 完成。把它拿出來，把 ${n} 拿在袋子外，準備好後按下面的按鈕。`,
    ring_baseline: '乾淨空氣', ring_move: '放進袋子', ring_measure: '量測中', ring_wait: '換感測器',
    ph_done: '完成',
    res_good: '食物沒壞', res_good_d: '沒有偵測到高於乾淨空氣的腐敗氣體。',
    res_bad: '食物壞了', res_bad_d: '偵測到明顯的腐敗氣體，請不要食用或販售。',
    res_spoiling: '腐敗氣體正在上升，食物開始變質。',
    res_retest: '請重新測試', res_busy: '另一個測試正在進行，請等它結束。',
    res_rule: '依三顆氣體感測器（MQ-135、MQ-3、MQ-2）以暫定規則判斷。',
    ag_sense: '感知', ag_decide: '判斷', ag_act: '行動',
    ag_sense_t: '3 顆氣體感測器，比乾淨空氣高出多少',
    ag_decide_t: (ms, g) => `在 UNO Q 上離線判斷為 ${g}，耗時 ${ms} ms`,
    act: { led_alarm: 'LED 矩陣閃爍 ✕ 警示', led_ok: 'LED 矩陣顯示 ✓', alert_sent: '已傳送警示到手機', alert_queued: '警示已排入佇列（尚未設定 Telegram）' },
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
  renderGauges();
}

function initialLang() {
  try { const saved = localStorage.getItem('pgas-lang'); if (saved) return saved; } catch (e) { /* storage unavailable */ }
  return (navigator.language || '').toLowerCase().startsWith('zh') ? 'zh' : 'en';
}

// ------------------------------------------------------------ state
const series = { mq135_v: [], mq3_v: [], mq2_v: [] }; // [{t: local ms, v}]
const current = { mq135_v: null, mq3_v: null, mq2_v: null };
const testBase = {};      // clean-air level measured at the start of a sensor's turn in a test
let baseBuf = [];         // samples of the active sensor during its clean-air step
let lastAt = 0;
let skewMs = null;
let conn = 'connecting';  // connecting | connected | disconnected | no_client
let job = null;           // {id, kind, step, s, i, n, done, state, grade, rises_v}
let lastRaw = null;
let ui = null;
let pending = false;
let shownResult = null;

const toLocal = (ts) => ts * 1000 + (skewMs ?? 0);
const fmt = (v, nd) => (typeof v === 'number' && isFinite(v) ? v.toFixed(nd) : '—');
const median = (a) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : null; };

function addSample(p, live) {
  if (!p || typeof p.ts !== 'number') return;
  if (live) { skewMs = Date.now() - p.ts * 1000; lastAt = Date.now(); }
  const t = toLocal(p.ts);
  for (const k of GAS) {
    const v = p[k];
    if (typeof v !== 'number' || !isFinite(v)) continue;
    const s = series[k];
    if (s.length && t <= s[s.length - 1].t) continue;
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

// Clean-air level: measured during a test, otherwise the 10th percentile of the last minutes.
function baseline(key) {
  const s = Object.keys(KEY).find((x) => KEY[x] === key);
  if (testBase[s] != null) return testBase[s];
  const v = series[key].map((p) => p.v);
  if (v.length < 10) return null;
  v.sort((a, b) => a - b);
  return v[Math.floor(v.length * 0.1)];
}

// ------------------------------------------------------------ gauges
const A0 = -120, A1 = 120; // dial sweep, degrees (0 = straight up)
function polar(r, deg) { const a = ((deg - 90) * Math.PI) / 180; return [100 + r * Math.cos(a), 100 + r * Math.sin(a)]; }
function arc(r, d0, d1) {
  const [x0, y0] = polar(r, d0), [x1, y1] = polar(r, d1);
  return `M${x0.toFixed(2)} ${y0.toFixed(2)} A${r} ${r} 0 ${d1 - d0 > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}
const toDeg = (rise) => A0 + (A1 - A0) * Math.max(-0.04, Math.min(1.04, rise / DIAL_MAX_V));

function buildDial(el) {
  const parts = [
    `<path class="zone z-ok" d="${arc(74, A0, toDeg(WARN_V))}"/>`,
    `<path class="zone z-warn" d="${arc(74, toDeg(WARN_V), toDeg(OVER_V))}"/>`,
    `<path class="zone z-over" d="${arc(74, toDeg(OVER_V), A1)}"/>`,
  ];
  for (let i = 0; i <= 10; i++) {
    const v = (DIAL_MAX_V * i) / 10, d = toDeg(v), major = i % 2 === 0;
    const [x0, y0] = polar(major ? 58 : 62, d), [x1, y1] = polar(67, d);
    parts.push(`<line class="tick${major ? ' major' : ''}" x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}"/>`);
    if (major) { const [lx, ly] = polar(91, d); parts.push(`<text class="lbl" x="${lx.toFixed(1)}" y="${(ly + 3).toFixed(1)}">+${v.toFixed(1)}</text>`); }
  }
  parts.push('<g class="needle"><line x1="100" y1="110" x2="100" y2="40"/></g>');
  parts.push('<circle class="hub" cx="100" cy="100" r="8"/><circle class="hub-in" cx="100" cy="100" r="3"/>');
  el.innerHTML = `<svg viewBox="-4 -4 208 156" aria-hidden="true">${parts.join('')}</svg>`;
}

// Tween the big number like a speedometer.
const shown = {};
function tweenNumber(el, key, to) {
  const from = shown[key] ?? to;
  shown[key] = to;
  const t0 = performance.now();
  const step = (now) => {
    const f = Math.min(1, (now - t0) / 450), e = 1 - (1 - f) ** 3;
    el.textContent = (from + (to - from) * e).toFixed(2);
    if (f < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function renderGauges() {
  const focusS = running() && job.step !== 'wait' ? job.s : null;
  document.querySelector('.gauges').classList.toggle('focus', !!focusS);
  for (const card of document.querySelectorAll('.gauge')) {
    const key = card.dataset.key;
    const v = current[key];
    const b = baseline(key);
    const rise = v != null && b != null ? v - b : null;
    card.classList.toggle('focused', card.dataset.s === focusS);
    card.classList.toggle('warn', rise != null && rise >= WARN_V && rise < OVER_V);
    card.classList.toggle('over', rise != null && rise >= OVER_V);
    const needle = card.querySelector('.needle');
    if (needle) needle.style.transform = `rotate(${toDeg(rise ?? 0)}deg)`;
    $(`d-${key}`).textContent = rise != null ? T('above')(rise) : v != null ? T('learning') : '';
    $(`r-${key}`).textContent = b != null ? T('normal')(b + WARN_V) : '';
  }
}

// ------------------------------------------------------------ rendering
function showValues(p) {
  for (const k of GAS) {
    if (typeof p[k] === 'number' && isFinite(p[k])) {
      current[k] = p[k];
      tweenNumber($(`v-${k}`), k, p[k]);
    }
  }
  // While a sensor reads clean air in a test, collect its samples for that sensor's baseline.
  if (running() && job.step === 'baseline' && typeof p[KEY[job.s]] === 'number') baseBuf.push(p[KEY[job.s]]);
  const dhtOk = !!p.dht_ok && typeof p.temp_c === 'number';
  $('v-temp').textContent = dhtOk ? fmt(p.temp_c, 1) : '—';
  $('v-rh').textContent = dhtOk ? fmt(p.rh_pct, 0) : '—';
  $('dht-note').hidden = dhtOk;
  if (Array.isArray(p.raw)) { lastRaw = p.raw; renderRaw(); }
  if (p.job && (!job || job.done) && !pending && p.job.startsWith('bag')) {
    job = { id: p.job.split(' ').pop(), kind: 'bag', done: false };
    renderJob();
  }
  renderGauges();
  renderRingLive();
}

function renderRaw() {
  $('raw').textContent = lastRaw ? `${T('raw')} A0/A1/A2: ${lastRaw.join(' / ')}` : '';
}

function renderStatus() {
  const el = $('status');
  let cls = 'wait', msg = T('connecting');
  const age = lastAt ? Date.now() - lastAt : null;
  if (conn === 'no_client') { cls = 'stale'; msg = T('no_client'); }
  else if (conn === 'connected' && age !== null && age <= STALE_MS) { cls = 'ok'; msg = T('ok'); }
  else if (conn === 'connected' && age === null) { cls = 'wait'; msg = T('connected_wait'); }
  else if (conn === 'connected') { cls = 'stale'; msg = T('stale')(Math.floor(age / 1000)); }
  else if (conn === 'disconnected') { cls = 'stale'; msg = T('disconnected'); }
  el.className = `pill ${cls}`;
  if ($('status-text').textContent !== msg) $('status-text').textContent = msg;
  const state = cls === 'ok' ? T('live_ok') : cls === 'stale' ? T('live_stale') : msg;
  if ($('status-live').textContent !== state) $('status-live').textContent = state;
}

// ------------------------------------------------------------ guided test
const running = () => !!(job && !job.done && job.kind === 'bag');
const waiting = () => running() && job.step === 'wait';

function say(text, err) {
  $('start-msg').textContent = text || '';
  $('start-msg').classList.toggle('err', !!err);
}

function renderSteps() {
  const k = running() ? SENSORS.indexOf(job.s) : -1;
  const finished = job && job.done && job.kind === 'bag' && job.state === 'done';
  document.querySelectorAll('#steps li').forEach((li, i) => {
    let st = 'todo';
    if (finished) st = 'done';
    else if (k >= 0) st = i < k ? 'done' : i === k ? (job.step === 'wait' ? 'next' : 'active') : 'todo';
    li.className = st;
    const r = finished && job.rises_v ? Number(job.rises_v[SENSORS[i]]) : NaN;
    li.querySelector('.st').textContent = st === 'done' ? (Number.isFinite(r) ? `${r >= 0 ? '+' : ''}${r.toFixed(2)} V` : '✓')
      : st === 'active' ? T('st_active') : st === 'next' ? T('st_next') : '';
  });
}

function renderButtons() {
  const btn = $('check-btn');
  const online = conn === 'connected';
  btn.classList.toggle('next', waiting());
  if (waiting()) { btn.disabled = !online || pending; btn.textContent = T('next_btn')(NAMES[job.s]); }
  else if (running()) { btn.disabled = true; btn.textContent = T('checking'); }
  else { btn.disabled = !online || pending; btn.textContent = pending ? T('checking') : T('check_btn'); }
  $('cancel-btn').hidden = !running();
}

let lastRingNum = null;
function renderJob() {
  const wrap = $('ring-wrap'), instr = $('instr'), overall = $('overall');
  if (running() && job.step) {
    const k = Math.max(0, SENSORS.indexOf(job.s));
    const name = NAMES[job.s];
    wrap.hidden = false;
    wrap.className = `ring-wrap ${job.step}`;
    $('ring-sensor').textContent = name;
    let num, frac;
    if (job.step === 'wait') { num = '✓'; frac = 1; $('ring-unit').textContent = T('ring_wait'); }
    else {
      const left = Math.max(0, (job.n || 0) - (job.i || 0));
      num = String(left);
      frac = job.n ? Math.min(1, ((job.i || 0) + 1) / job.n) : 0;
      $('ring-unit').textContent = `${T('sec')} · ${T(`ring_${job.step}`)}`;
    }
    const numEl = $('ring-num');
    if (numEl.textContent !== num) {
      numEl.textContent = num;
      numEl.classList.remove('bump'); void numEl.offsetWidth; numEl.classList.add('bump');
    }
    $('ring-fg').style.strokeDashoffset = String(RING_LEN * (1 - frac));
    renderRingLive();
    instr.textContent = T(`in_${job.step}`)(name, k > 0 ? NAMES[SENSORS[k - 1]] : '');
    instr.className = `instr ${job.step}`;
    const [a, b] = STEP_SHARE[job.step] || [0, 0];
    const f = job.n ? Math.min(1, ((job.i || 0) + 1) / job.n) : 0;
    const pct = job.step === 'wait' ? (k / 3) * 100 : ((k + a + (b - a) * f) / 3) * 100;
    overall.hidden = false;
    $('bar-fill').style.width = `${pct}%`;
    $('bar').setAttribute('aria-valuenow', String(Math.round(pct)));
    $('phase-text').textContent = T('sensor_of')(k + 1);
    $('pct-text').textContent = `${Math.round(pct)}%`;
  } else if (running()) {
    wrap.hidden = true; overall.hidden = true;
    instr.textContent = T('checking'); instr.className = 'instr';
  } else {
    wrap.hidden = true;
    const finished = job && job.done && job.kind === 'bag' && job.state === 'done';
    overall.hidden = !finished;
    if (finished) {
      $('bar-fill').style.width = '100%';
      $('phase-text').textContent = T('ph_done');
      $('pct-text').textContent = '100%';
    }
    instr.textContent = T('in_idle');
    instr.className = 'instr';
  }
  renderSteps();
  renderButtons();
  renderGauges();
}

function renderRingLive() {
  const el = $('ring-live');
  if (!running() || !job.s || job.step === 'wait') { el.hidden = true; return; }
  const key = KEY[job.s], v = current[key], b = baseline(key);
  if (v == null) { el.hidden = true; return; }
  const rise = b != null ? v - b : null;
  el.hidden = false;
  el.className = `ring-live ${rise != null && rise >= OVER_V ? 'over' : rise != null && rise >= WARN_V ? 'warn' : ''}`;
  el.textContent = `${NAMES[job.s]} ${v.toFixed(2)} V${rise != null ? ` (${rise >= 0 ? '+' : '−'}${Math.abs(rise).toFixed(2)})` : ''}`;
}

function showResult(m) {
  if (!m || shownResult === m.id) return;
  if (m.state === 'failed' && !m.retest && /stopped/.test(m.error || '')) return; // cancelled by the user
  shownResult = m.id;
  let cls, title, detail = '';
  if (m.state === 'done' && m.grade) {
    const ok = m.grade === 'FRESH';
    cls = ok ? 'good' : 'bad';
    title = ok ? T('res_good') : T('res_bad');
    detail = m.grade === 'SPOILING' ? T('res_spoiling') : ok ? T('res_good_d') : T('res_bad_d');
  } else if (m.state === 'rejected') { cls = 'warn'; title = T('res_busy'); }
  else { cls = 'warn'; title = T('res_retest'); detail = m.error ? String(m.error) : ''; }
  $('result').querySelector('.sheet').className = `sheet ${cls}`;
  $('result-icon').textContent = cls === 'good' ? '✓' : cls === 'bad' ? '✕' : '!';
  $('result-title').textContent = title;
  $('result-detail').textContent = detail;
  const r = m.rises_v || {};
  $('result-bars').innerHTML = SENSORS.filter((s) => r[s] != null).map((s) => {
    const v = Number(r[s]);
    const color = v >= OVER_V ? 'var(--red)' : v >= WARN_V ? 'var(--orange)' : 'var(--green)';
    const w = Math.max(2, Math.min(100, (v / DIAL_MAX_V) * 100));
    return `<div class="rb"><span>${NAMES[s]}</span><span class="t"><span style="background:${color}" data-w="${w}"></span></span><span class="v">${v >= 0 ? '+' : ''}${v.toFixed(2)} V</span></div>`;
  }).join('');
  $('result-note').textContent = m.method === 'rule' ? T('res_rule') : '';
  const ag = $('agent');
  ag.hidden = !(m.state === 'done' && m.grade);
  if (!ag.hidden) {
    $('ag-sense').textContent = T('ag_sense_t');
    $('ag-decide').textContent = T('ag_decide_t')(m.decide_ms != null ? Number(m.decide_ms).toFixed(1) : '<1', m.grade);
    $('ag-act').textContent = (m.actions || []).map((a) => T('act')[a] || a).join(' · ') || '—';
  }
  const box = $('result');
  box.hidden = false;
  requestAnimationFrame(() => {
    box.classList.add('show');
    box.querySelectorAll('.rb .t span').forEach((el) => { el.style.width = `${el.dataset.w}%`; });
  });
  $('result-ok').focus();
}

function closeResult() {
  const box = $('result');
  box.classList.remove('show');
  setTimeout(() => { box.hidden = true; $('check-btn').focus(); }, 250);
}

function onJob(m) {
  if (!m) return;
  pending = false;
  if (m.state === 'running') {
    const same = job && job.id === m.id;
    if (!same) { for (const s of SENSORS) delete testBase[s]; baseBuf = []; }
    job = Object.assign(same ? job : { id: m.id, kind: m.kind }, { done: false });
    if (m.phase && m.phase.includes(':')) {
      const [step, sensor] = m.phase.split(':');
      // The clean-air step just ended: its median is this sensor's baseline for the dial.
      if (job.step === 'baseline' && step !== 'baseline' && baseBuf.length) testBase[job.s] = median(baseBuf);
      if (step === 'baseline' && job.step !== 'baseline') baseBuf = [];
      Object.assign(job, { step, s: sensor, i: m.i, n: m.n });
    }
  } else {
    job = Object.assign({}, job && job.id === m.id ? job : { id: m.id, kind: m.kind }, m, { done: true });
    if (m.kind === 'bag' || m.state === 'rejected') showResult(m);
    for (const s of SENSORS) delete testBase[s];
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

function onReply(r) {
  if (r && !r.ok) { pending = false; say(T('cmd_failed')(r.error), true); }
  renderButtons();
}

// ------------------------------------------------------------ sparklines
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function drawSpark(key, now) {
  const cv = $(`c-${key}`);
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  if (!w || !h) return;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
  const g = cv.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  const s = series[key];
  if (s.length < 2) return;
  let lo = Infinity, hi = -Infinity;
  for (const p of s) { lo = Math.min(lo, p.v); hi = Math.max(hi, p.v); }
  const span = Math.max(hi - lo, 0.1), mid = (hi + lo) / 2;
  lo = mid - span * 0.6; hi = mid + span * 0.6;
  const x = (t) => ((t - (now - WINDOW_MS)) / WINDOW_MS) * w;
  const y = (v) => 4 + (1 - (v - lo) / (hi - lo)) * (h - 8);
  const color = cssVar(COLOR_VAR[key]);
  const grad = g.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, `${color}55`); grad.addColorStop(1, `${color}00`);
  g.beginPath();
  s.forEach((p, i) => (i ? g.lineTo(x(p.t), y(p.v)) : g.moveTo(x(p.t), y(p.v))));
  g.lineTo(x(s[s.length - 1].t), h); g.lineTo(x(s[0].t), h); g.closePath();
  g.fillStyle = grad; g.fill();
  g.beginPath();
  let prev = null;
  for (const p of s) {
    if (!prev || p.t - prev.t > 5000) g.moveTo(x(p.t), y(p.v)); else g.lineTo(x(p.t), y(p.v));
    prev = p;
  }
  g.strokeStyle = color; g.lineWidth = 2; g.lineJoin = 'round'; g.stroke();
}

function tick() {
  const now = Date.now();
  trim(now);
  renderStatus();
  for (const k of GAS) drawSpark(k, now);
}

// ------------------------------------------------------------ wiring
function connect() {
  if (typeof WebUI === 'undefined' || typeof io === 'undefined') { conn = 'no_client'; return; }
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
  document.querySelectorAll('.dial').forEach(buildDial);
  $('lang-en').addEventListener('click', () => setLang('en'));
  $('lang-zh').addEventListener('click', () => setLang('zh'));
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
  setLang(initialLang());
  connect();
  tick();
  setInterval(tick, 500);
  document.addEventListener('visibilitychange', tick);
  window.addEventListener('resize', tick);
});
