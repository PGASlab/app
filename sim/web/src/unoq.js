// PGAS on the Arduino UNO Q - software-in-the-loop simulation in the browser.
//
// MCU: the UNO Q code path of app/sketch/sketch.ino (analogReadResolution(14),
// Bridge.provide/notify, Arduino_LED_Matrix), compiled to WebAssembly against
// sim/unoq/hal - an emulation of the UNO Q MCU API plus the PGAS wiring
// (10k/20k dividers, DHT22 timing model). The STM32U585 instruction set and
// Zephyr are not emulated.
// Linux side: a browser port of pgas/session.py + pgas/display.py that talks to
// the sketch only through the Bridge, exactly like pgas/board.py: it receives
// Bridge.notify("pgas_sample", ...) and sends Bridge.call("draw", frame).

const DIV = 20 / 30, FULL14 = 16383, VREF = 3.3;
const SENSORS = ['mq135', 'mq3', 'mq2'];
const CLEAN_AIR = [1.0, 0.8, 0.9];          // module volts - simulation parameter
const FOODS = {                              // rise in module volts - simulation parameters, not measurements
  fresh: { name: 'fresh chicken (simulated)', amp: [0.15, 0.05, 0.10] },
  swill: { name: 'swill (simulated)', amp: [2.20, 1.40, 1.80] },
};
const $ = (id) => document.getElementById(id);
const state = { module: [...CLEAN_AIR], temp: 26.5, rh: 65, dht: true, dhtAt: 0 };
let mcu = null, framePtr = 0, latest = null, samples = 0, matrixDraws = 0, bridgeCalls = 0, running = true;
let matrix = new Array(104).fill(0);

// ------------------------------------------------------------------ logs
function addLine(id, text, max = 300) {
  const el = $(id);
  el.textContent += text + '\n';
  const lines = el.textContent.split('\n');
  if (lines.length > max) el.textContent = lines.slice(-max).join('\n');
  el.scrollTop = el.scrollHeight;
}
const tMcu = () => (mcu ? (mcu._hal_time_ms() / 1000).toFixed(1).padStart(6, ' ') : '   0.0');
const log = (m) => addLine('log', `[${tMcu()} s] ${m}`);

// ------------------------------------------------------------------ Bridge (Linux side)
function bridgeDraw(frame) {
  bridgeCalls++;
  mcu.HEAPU8.set(frame.map((v) => Math.max(0, Math.min(7, v))), framePtr);
  mcu._hal_bridge_draw(framePtr);
  addLine('bridge', `[${tMcu()} s] Linux → MCU  Bridge.call("draw", <104 bytes>)`, 120);
}
function onNotify(text) {
  const [method, ...args] = text.split(',');
  addLine('bridge', `[${tMcu()} s] MCU → Linux  Bridge.notify("${method}", ${args.join(', ')})`, 120);
  if (method !== 'pgas_sample') return;
  latest = args.map(Number);
  samples++;
  onSample(latest);
}

// ------------------------------------------------------------------ display.py port
const FONT = {
  '0': [7, 5, 5, 5, 7], '1': [2, 6, 2, 2, 7], '2': [7, 1, 7, 4, 7], '3': [7, 1, 7, 1, 7], '4': [5, 5, 7, 1, 1],
  '5': [7, 4, 7, 1, 7], '6': [7, 4, 7, 5, 7], '7': [7, 1, 2, 2, 2], '8': [7, 5, 7, 5, 7], '9': [7, 5, 7, 1, 7],
  A: [2, 5, 7, 5, 5], H: [5, 5, 7, 5, 5], V: [5, 5, 5, 5, 2], M: [5, 7, 7, 5, 5], ' ': [0, 0, 0, 0, 0],
};
function text3(s) {
  const f = new Array(104).fill(0);
  [...s].forEach((ch, k) => {
    const col = [0, 5, 9][k];
    (FONT[ch] || FONT[' ']).forEach((bits, r) => { for (let c = 0; c < 3; c++) if (bits & (4 >> c)) f[r * 13 + col + c] = 7; });
  });
  return f;
}
function countdown(letter, left, progress) {
  const s = Math.max(0, Math.min(99, Math.floor(left)));
  const f = text3(`${letter}${Math.floor(s / 10)}${s % 10}`);
  for (let x = 0; x < Math.round(Math.max(0, Math.min(1, progress)) * 13); x++) f[7 * 13 + x] = 7;
  return f;
}
const CHECK = ['0000000000000', '0000000000011', '0000000000110', '0000000001100', '0110000011000', '0011000110000', '0001101100000', '0000111000000'];
const checkFrame = () => CHECK.join('').split('').map((c) => (c === '1' ? 7 : 0));
let lastSent = '';
function show(frame) { const k = frame.join(''); if (k !== lastSent) { lastSent = k; bridgeDraw(frame); } }

// ------------------------------------------------------------------ session.py port (hood mode)
const S = { phase: 'idle', i: 0, base: [[], [], []], peak: [-1e9, -1e9, -1e9], held: 0, rows: [], food: null, short: true, result: null };
const op = { target: 0, level: 0 };
const D = () => (S.short ? { A: 10, M: 5, H: 20, V: 60 } : { A: 30, M: 5, H: 60, V: 180 });
const volts = (raw) => raw / FULL14 * VREF / DIV;
const median = (a) => { const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
function startHood(food) {
  finalRise = null;
  Object.assign(S, { phase: 'A', i: 0, base: [[], [], []], peak: [-1e9, -1e9, -1e9], held: 0, rows: [], food, short: $('short').checked, result: null });
  op.target = 0;
  $('result').innerHTML = '<tr><td colspan="4" style="text-align:left">capturing…</td></tr>';
  log(`$ python3 -m pgas.capture --mode hood --label ${food === 'swill' ? 'swill_sim' : 'fresh_sim_chicken'}`);
  log('STEP 1/3: hold the box in open air, away from food');
}
function onSample(raw) {
  if (S.phase === 'idle' || S.phase === 'done') return;
  const v = raw.slice(0, 3).map(volts), d = D();
  S.rows.push({ phase: S.phase, v, t: raw[3], h: raw[4], ok: raw[5] });
  if (S.phase === 'A') {
    v.forEach((x, k) => S.base[k].push(x));
    show(countdown('A', d.A - S.i, S.i / d.A));
    if (++S.i >= d.A) { S.phase = 'M'; S.i = 0; log('MOVE NOW: put the box over the food, opening down, 3-5 cm above it'); setTimeout(() => { op.target = 1; log('OPERATOR: box lowered over the food'); }, 2000); }
  } else if (S.phase === 'M') {
    show(countdown('M', d.M - S.i, S.i / d.M));
    if (++S.i >= d.M) { S.phase = 'H'; S.i = 0; log('STEP 2/3: hold the box still over the food'); }
  } else if (S.phase === 'H') {
    v.forEach((x, k) => { S.peak[k] = Math.max(S.peak[k], x); });
    show(countdown('H', d.H - S.i, S.i / d.H));
    if (++S.i >= d.H) { S.phase = 'V'; S.i = 0; op.target = 0; log('STEP 3/3: lift the box away and let it air out'); log('OPERATOR: box lifted'); }
  } else if (S.phase === 'V') {
    show(countdown('V', d.V - S.i, S.i / d.V));
    const bm = S.base.map(median);
    const ok = v.every((x, k) => x - bm[k] <= 0.10 * Math.max(0, S.peak[k] - bm[k]) + 0.02);
    S.held = ok ? S.held + 1 : 0;
    if (S.held >= 5 || ++S.i >= d.V) finish(S.held >= 5);
  }
}
function finish(recovered) {
  const bm = S.base.map(median), ex = S.rows.filter((r) => r.phase === 'H');
  const feats = SENSORS.map((s, k) => {
    const xs = ex.map((r) => r.v[k]);
    return { s, dmed: median(xs) - bm[k], dpeak: Math.max(...xs) - bm[k], dmean: xs.reduce((a, b) => a + b, 0) / xs.length - bm[k] };
  });
  const env = ex.filter((r) => r.ok);
  S.phase = 'done';
  S.result = feats;
  finalRise = Math.max(...feats.map((f) => f.dpeak));
  show(checkFrame());
  log(recovered ? 'readings back to baseline' : 'recover timeout');
  log('features: ' + feats.map((f) => `${f.s.toUpperCase()} d_peak=${f.dpeak.toFixed(3)} V`).join(', ')
      + (env.length ? `, temp ${median(env.map((r) => r.t)).toFixed(1)} C, RH ${median(env.map((r) => r.h)).toFixed(0)} %` : ', DHT22: no valid reading (imputed on the board)'));
  log('grade: decided on the UNO Q by the ONNX model trained on real captures - not simulated here');
  $('result').innerHTML = feats.map((f) => `<tr><td>${f.s.toUpperCase()}</td><td>${f.dmed.toFixed(3)}</td><td>${f.dpeak.toFixed(3)}</td><td>${f.dmean.toFixed(3)}</td></tr>`).join('');
}

// ------------------------------------------------------------------ physical world
function pushInputs() {
  if (!mcu) return;
  state.module.forEach((v, k) => mcu._hal_set_module(k, v));
  mcu._hal_set_env(state.temp, state.rh);
  mcu._hal_set_dht_connected(state.dht ? 1 : 0);
}
function operatorTick(dt) {
  if (!S.food || S.phase === 'idle') return;
  const tau = op.target > op.level ? 12 : 8;
  op.level += (op.target - op.level) * dt / tau;
  state.module = CLEAN_AIR.map((c, k) => c + op.level * FOODS[S.food].amp[k]);
  SENSORS.forEach((s, k) => { $(`sl-${s}`).value = state.module[k].toFixed(2); });
}

// ------------------------------------------------------------------ render
function render() {
  $('simtime').textContent = mcu ? (mcu._hal_time_ms() / 1000).toFixed(1) : '0';
  $('samples').textContent = samples;
  $('draws').textContent = `${bridgeCalls} / ${matrixDraws}`;
  SENSORS.forEach((s, k) => {
    const vm = state.module[k], vp = Math.min(3.3, vm * DIV);
    $(`out-${s}`).textContent = vm.toFixed(2) + ' V';
    $(`vm-${s}`).textContent = vm.toFixed(2) + ' V';
    $(`vp-${s}`).textContent = vp.toFixed(2) + ' V';
    $(`vpin-${s}`).textContent = vp.toFixed(3) + ' V';
    $(`raw-${s}`).textContent = latest ? latest[k] : '–';
    $(`dec-${s}`).textContent = latest ? volts(latest[k]).toFixed(3) + ' V' : '–';
    $(`wire-${s}`).style.strokeWidth = 2 + 4 * Math.min(1, Math.max(0, (vp - 0.4) / 2.6));
  });
  $('val-temp').textContent = state.temp.toFixed(1) + ' °C';
  $('val-rh').textContent = state.rh.toFixed(0) + ' %';
  $('dec-dht').textContent = latest ? (latest[5] ? `${latest[3].toFixed(1)} °C / ${latest[4].toFixed(1)} %` : 'no valid reading (dht_ok = 0)') : '–';
  $('wire-d2').classList.toggle('active', performance.now() - state.dhtAt < 250);
  $('phase').textContent = { idle: 'ready', A: 'A · clean air', M: 'M · move the box', H: 'H · over the food', V: 'V · airing out', done: '✓ done' }[S.phase];
  for (let i = 0; i < 104; i++) {
    const on = matrix[i] > 0;
    $(`led-${i}`).setAttribute('class', on ? 'led on' : 'led');
    bigCells[i].classList.toggle('on', on);
  }
  renderSteps();
  renderMeter();
}

// ------------------------------------------------------------------ main loop
let last = 0;
function frame(now) {
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  if (mcu && running) {
    operatorTick(dt);
    pushInputs();
    mcu._hal_run_us(dt * 1e6);
  }
  try { render(); } catch (e) { console.error(e); }
  requestAnimationFrame(frame);
}

// ------------------------------------------------------------------ plain-language hero
let bigCells = [];
const STEP_OF = { A: 1, M: 2, H: 2, V: 3 };
function renderSteps() {
  const d = D(), cur = STEP_OF[S.phase] || 0, done = S.phase === 'done';
  const left = { A: d.A - S.i, M: d.M - S.i + d.H, H: d.H - S.i, V: null }[S.phase];
  for (let n = 1; n <= 3; n++) {
    const li = $(`step-${n}`);
    li.classList.toggle('active', n === cur);
    li.classList.toggle('done', done || (cur > n));
    $(`t-${n}`).textContent = n === cur ? (left != null ? `${Math.max(0, left)} s` : 'waiting…') : (done || cur > n ? '✓' : '');
  }
}
function smellRise() {
  // Largest rise above the clean-air reading, over the three sensors (volts at the module).
  if (!latest || !S.base[0].length) return 0;
  const bm = S.base.map(median);
  return Math.max(0, ...latest.slice(0, 3).map((raw, k) => volts(raw) - bm[k]));
}
function smellWord(r) { return r < 0.2 ? 'none' : r < 0.8 ? 'some' : 'strong'; }
let finalRise = null;
function renderMeter() {
  const active = S.phase !== 'idle';
  const r = S.phase === 'done' && finalRise != null ? finalRise : (active ? smellRise() : 0);
  $('meter-fill').style.width = `${Math.min(100, r / 2 * 100)}%`;
  $('meter-word').textContent = active ? smellWord(r) : '–';
  if (S.phase === 'done') {
    $('verdict').textContent = r >= 0.8
      ? `Strong spoilage smell: the gas sensors rose ${r.toFixed(2)} V above clean air.`
      : r >= 0.2 ? `Some smell: the gas sensors rose ${r.toFixed(2)} V above clean air.`
        : `Barely any smell: the gas sensors rose only ${r.toFixed(2)} V above clean air.`;
  } else if (active) {
    $('verdict').textContent = { A: 'Step 1: measuring clean air…', M: 'Step 2: put the box over the food now.', H: 'Step 2: smelling the food…', V: 'Step 3: lift the box and let it air out.' }[S.phase];
  }
}

function buildBoardLeds() {
  const bm = $('bigmatrix');
  for (let i = 0; i < 104; i++) bm.appendChild(document.createElement('i'));
  bigCells = [...bm.children];
  const g = $('leds');
  for (let r = 0; r < 8; r++) for (let c = 0; c < 13; c++) {
    const el = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    el.setAttribute('cx', 0 + c * 15); el.setAttribute('cy', 0 + r * 15); el.setAttribute('r', 5.2);
    el.setAttribute('id', `led-${r * 13 + c}`); el.setAttribute('class', 'led');
    g.appendChild(el);
  }
}

async function start() {
  buildBoardLeds();
  SENSORS.forEach((s, k) => {
    $(`sl-${s}`).value = state.module[k];
    $(`sl-${s}`).addEventListener('input', (e) => { state.module[k] = +e.target.value; });
  });
  $('sl-temp').addEventListener('input', (e) => { state.temp = +e.target.value; });
  $('sl-rh').addEventListener('input', (e) => { state.rh = +e.target.value; });
  $('dht-conn').addEventListener('change', (e) => { state.dht = e.target.checked; });
  document.querySelectorAll('[data-hood]').forEach((b) => b.addEventListener('click', () => startHood(b.dataset.hood)));
  $('reset-air').addEventListener('click', () => { S.phase = 'idle'; S.food = null; op.level = 0; state.module = [...CLEAN_AIR]; SENSORS.forEach((s, k) => { $(`sl-${s}`).value = state.module[k]; }); finalRise = null; show(new Array(104).fill(0)); $('verdict').textContent = 'Press a button to start a test.'; log('clean air'); });
  $('pause').addEventListener('click', (e) => { running = !running; e.target.textContent = running ? 'Pause MCU' : 'Resume MCU'; });

  mcu = await window.UnoQMcu({
    onNotify,
    onMatrix: (f) => { matrix = f; matrixDraws++; },
    onDht: () => { state.dhtAt = performance.now(); },
  });
  framePtr = mcu._malloc(104);
  pushInputs();
  mcu._hal_setup();
  log('UNO Q MCU booted: setup() ran (analogReadResolution(14), matrix.begin(), Bridge.begin(), Bridge.provide("draw"))');
  window.PGAS_UNOQ = { get latest() { return latest; }, get samples() { return samples; }, get session() { return S; }, get matrixDraws() { return matrixDraws; }, startHood };
  last = performance.now();
  requestAnimationFrame(frame);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
