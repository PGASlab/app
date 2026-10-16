// PGAS in-browser circuit simulation.
// The firmware is the real app/sketch/sketch.ino compiled for ATmega328P
// (sim/build_avr.sh) and executed instruction-by-instruction by avr8js
// (the open-source AVR emulator behind Wokwi). Around it:
//   - MQ module outputs (sliders) -> 10k/20k divider -> ADC A0..A2
//   - DHT22 timing model on D2 (10k pull-up to 3.3 V)
//   - USART0 -> serial monitor
// The hood-mode panel is a browser port of pgas/session.py + pgas/display.py
// (the Python originals are what runs on the board and in the simavr CI run).
import {
  CPU, avrInstruction, AVRTimer, timer0Config, timer1Config, timer2Config,
  AVRUSART, usart0Config, AVRADC, adcConfig, AVRIOPort, portBConfig, portCConfig, portDConfig, PinState,
} from 'avr8js';

const F_CPU = 16e6;
const DIV = 20 / (10 + 20);
const ADC_MAX14 = 16383, VREF_Q = 3.3;
const SENSORS = ['mq135', 'mq3', 'mq2'];
const CLEAN_AIR = [1.0, 0.8, 0.9];                 // module volts (simulation parameter)
const FOODS = {                                    // rise in module volts (simulation parameters, not measurements)
  fresh: { name: 'fresh chicken (simulated)', amp: [0.15, 0.05, 0.10] },
  swill: { name: 'swill (simulated)', amp: [2.20, 1.40, 1.80] },
};

// ---------------------------------------------------------------- firmware
function loadHex(hex, target) {
  for (const line of hex.split('\n')) {
    if (line[0] !== ':') continue;
    const n = parseInt(line.substr(1, 2), 16), addr = parseInt(line.substr(3, 4), 16), type = parseInt(line.substr(7, 2), 16);
    if (type !== 0) continue;
    for (let i = 0; i < n; i++) target[addr + i] = parseInt(line.substr(9 + i * 2, 2), 16);
  }
}
const progBytes = new Uint8Array(0x8000);
loadHex(window.PGAS_HEX, progBytes);
const cpu = new CPU(new Uint16Array(progBytes.buffer));
new AVRTimer(cpu, timer0Config); new AVRTimer(cpu, timer1Config); new AVRTimer(cpu, timer2Config);
const portB = new AVRIOPort(cpu, portBConfig), portC = new AVRIOPort(cpu, portCConfig), portD = new AVRIOPort(cpu, portDConfig);
const usart = new AVRUSART(cpu, usart0Config, F_CPU);
const adc = new AVRADC(cpu, adcConfig);
adc.avcc = 5;

// ---------------------------------------------------------------- circuit state
const state = { module: [...CLEAN_AIR], temp: 26.5, rh: 65, dhtConnected: true, dhtActivity: 0 };
function applyADC() {
  for (let i = 0; i < 3; i++) adc.channelValues[i] = state.module[i] * DIV;   // divider: V_pin = V_mod * 2/3
}
applyADC();

// ---------------------------------------------------------------- DHT22 model (port of sim/simavr/pgas_board.c)
const us = (x) => Math.round(x * F_CPU / 1e6);
let seq = [], seqI = 0, lowStart = -1, prevLow = false;
portD.setPin(2, true); // pull-up
function seqStep() {
  if (seqI >= seq.length) { portD.setPin(2, true); return; }
  const [level, dur] = seq[seqI++];
  portD.setPin(2, !!level);
  cpu.addClockEvent(seqStep, us(dur));
}
function startResponse() {
  const h = Math.round(state.rh * 10), t = Math.round(state.temp * 10), ta = Math.abs(t);
  const d = [(h >> 8) & 255, h & 255, ((ta >> 8) & 0x7f) | (t < 0 ? 0x80 : 0), ta & 255];
  d.push((d[0] + d[1] + d[2] + d[3]) & 255);
  seq = [[1, 30], [0, 80], [1, 80]];
  for (let i = 0; i < 40; i++) { const bit = (d[i >> 3] >> (7 - (i & 7))) & 1; seq.push([0, 50], [1, bit ? 70 : 26]); }
  seq.push([0, 50]);
  seqI = 0;
  state.dhtActivity = performance.now();
  seqStep();
}
function dhtPoll() {
  const ps = portD.pinState(2);
  const low = ps === PinState.Low;
  if (low && !prevLow) lowStart = cpu.cycles;
  if (!low && prevLow && lowStart >= 0) {
    const lowUs = (cpu.cycles - lowStart) * 1e6 / F_CPU;
    lowStart = -1;
    if (ps === PinState.Input && lowUs >= 1000 && state.dhtConnected && seqI >= seq.length) startResponse();
  }
  prevLow = low;
  cpu.addClockEvent(dhtPoll, us(20));
}
cpu.addClockEvent(dhtPoll, us(20));

// ---------------------------------------------------------------- serial
let lineBuf = '';
const listeners = [];
usart.onByteTransmit = (b) => {
  const c = String.fromCharCode(b);
  if (c === '\n') { const l = lineBuf.replace('\r', ''); lineBuf = ''; listeners.forEach((f) => f(l)); }
  else lineBuf += c;
};

// ---------------------------------------------------------------- run loop (real time)
let last = performance.now(), simSeconds = 0, running = true;
function frame(now) {
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  if (running) {
    const target = cpu.cycles + dt * F_CPU;
    while (cpu.cycles < target) { avrInstruction(cpu); cpu.tick(); }
    simSeconds = cpu.cycles / F_CPU;
  }
  operatorTick(dt);
  try { render(); } catch (e) { console.error(e); }
  requestAnimationFrame(frame);
}

// ---------------------------------------------------------------- LED matrix (port of pgas/display.py)
const FONT = {
  '0': [7, 5, 5, 5, 7], '1': [2, 6, 2, 2, 7], '2': [7, 1, 7, 4, 7], '3': [7, 1, 7, 1, 7], '4': [5, 5, 7, 1, 1],
  '5': [7, 4, 7, 1, 7], '6': [7, 4, 7, 5, 7], '7': [7, 1, 2, 2, 2], '8': [7, 5, 7, 5, 7], '9': [7, 5, 7, 1, 7],
  A: [2, 5, 7, 5, 5], H: [5, 5, 7, 5, 5], V: [5, 5, 5, 5, 2], M: [5, 7, 7, 5, 5], ' ': [0, 0, 0, 0, 0],
};
function blank() { return new Array(104).fill(0); }
function text3(s) {
  const f = blank();
  [...s].forEach((ch, k) => {
    const col = [0, 5, 9][k];
    (FONT[ch] || FONT[' ']).forEach((bits, r) => { for (let c = 0; c < 3; c++) if (bits & (4 >> c)) f[r * 13 + col + c] = 7; });
  });
  return f;
}
function countdown(letter, left, progress) {
  const s = Math.max(0, Math.min(99, Math.floor(left)));
  const f = text3(`${letter}${Math.floor(s / 10)}${s % 10}`);
  const n = Math.round(Math.max(0, Math.min(1, progress)) * 13);
  for (let x = 0; x < n; x++) f[7 * 13 + x] = 7;
  return f;
}
const ICONS = {
  done: ['0000000000000', '0000000000011', '0000000000110', '0000000001100', '0110000011000', '0011000110000', '0001101100000', '0000111000000'],
};
const iconFrame = (k) => ICONS[k].join('').split('').map((c) => (c === '1' ? 7 : 0));
let ledFrame = blank();

// ---------------------------------------------------------------- hood session (port of pgas/session.run_hood)
const session = { phase: 'idle', i: 0, base: [[], [], []], peak: [-1e9, -1e9, -1e9], held: 0, rows: [], food: null, short: false, result: null };
const operator = { target: 0, level: 0 };
function durations() { return session.short ? { A: 10, M: 5, H: 20, V: 60 } : { A: 30, M: 5, H: 60, V: 180 }; }
function volts(raw) { return raw / ADC_MAX14 * VREF_Q / DIV; }
function startHood(food, short) {
  Object.assign(session, { phase: 'A', i: 0, base: [[], [], []], peak: [-1e9, -1e9, -1e9], held: 0, rows: [], food, short, result: null });
  operator.target = 0;
  log(`hood capture started - ${FOODS[food].name}`);
  log('STEP 1/3: hold the box in open air (baseline)');
}
const median = (a) => { const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
function onSample(raw) {
  if (session.phase === 'idle' || session.phase === 'done') return;
  const v = raw.slice(0, 3).map(volts), D = durations();
  session.rows.push({ phase: session.phase, v });
  if (session.phase === 'A') {
    v.forEach((x, k) => session.base[k].push(x));
    ledFrame = countdown('A', D.A - session.i, session.i / D.A);
    if (++session.i >= D.A) { session.phase = 'M'; session.i = 0; log('MOVE NOW: put the box over the food'); setTimeout(() => { operator.target = 1; log('OPERATOR: box lowered over the food'); }, 2000); }
  } else if (session.phase === 'M') {
    ledFrame = countdown('M', D.M - session.i, session.i / D.M);
    if (++session.i >= D.M) { session.phase = 'H'; session.i = 0; log('STEP 2/3: hold the box still over the food'); }
  } else if (session.phase === 'H') {
    v.forEach((x, k) => { session.peak[k] = Math.max(session.peak[k], x); });
    ledFrame = countdown('H', D.H - session.i, session.i / D.H);
    if (++session.i >= D.H) { session.phase = 'V'; session.i = 0; operator.target = 0; log('STEP 3/3: lift the box away and let it air out'); log('OPERATOR: box lifted'); }
  } else if (session.phase === 'V') {
    ledFrame = countdown('V', D.V - session.i, session.i / D.V);
    const bm = session.base.map(median);
    const ok = v.every((x, k) => x - bm[k] <= 0.10 * Math.max(0, session.peak[k] - bm[k]) + 0.02);
    session.held = ok ? session.held + 1 : 0;
    if (session.held >= 5 || ++session.i >= D.V) finishHood(session.held >= 5);
  }
}
function finishHood(recovered) {
  const bm = session.base.map(median);
  const exp = session.rows.filter((r) => r.phase === 'H');
  const feats = SENSORS.map((s, k) => {
    const xs = exp.map((r) => r.v[k]);
    return { s, d_median: median(xs) - bm[k], d_peak: Math.max(...xs) - bm[k], d_mean: xs.reduce((a, b) => a + b, 0) / xs.length - bm[k] };
  });
  session.phase = 'done';
  session.result = { recovered, feats, n: session.rows.length };
  ledFrame = iconFrame('done');
  log(recovered ? 'readings back to baseline' : 'recover timeout');
  log('features: ' + feats.map((f) => `${f.s.toUpperCase()} d_peak=${f.d_peak.toFixed(3)} V`).join(', '));
  log('(the grade is computed on the UNO Q by the ONNX classifier trained on real captures - not simulated here)');
}
function operatorTick(dt) {
  if (!session.food || session.phase === 'idle') return;
  const tau = operator.target > operator.level ? 12 : 8;
  operator.level += (operator.target - operator.level) * dt / tau;
  const amp = FOODS[session.food].amp;
  state.module = CLEAN_AIR.map((c, k) => c + operator.level * amp[k]);
  applyADC();
  syncSliders();
}

// ---------------------------------------------------------------- UI
const $ = (id) => document.getElementById(id);
const serialEl = $('serial'), logEl = $('log');
function log(msg) {
  const t = simSeconds.toFixed(0).padStart(4, ' ');
  logEl.textContent += `[${t} s] ${msg}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}
let latest = null, sampleCount = 0;
listeners.push((line) => {
  serialEl.textContent += line + '\n';
  const lines = serialEl.textContent.split('\n');
  if (lines.length > 200) serialEl.textContent = lines.slice(-200).join('\n');
  serialEl.scrollTop = serialEl.scrollHeight;
  if (line.startsWith('S,')) {
    const p = line.slice(2).split(',').map(Number);
    latest = p; sampleCount++;
    onSample(p);
  }
});
function syncSliders() {
  SENSORS.forEach((s, k) => { $(`sl-${s}`).value = state.module[k].toFixed(2); });
}
SENSORS.forEach((s, k) => {
  $(`sl-${s}`).addEventListener('input', (e) => { state.module[k] = +e.target.value; applyADC(); });
});
$('sl-temp').addEventListener('input', (e) => { state.temp = +e.target.value; });
$('sl-rh').addEventListener('input', (e) => { state.rh = +e.target.value; });
$('dht-conn').addEventListener('change', (e) => { state.dhtConnected = e.target.checked; });
document.querySelectorAll('[data-hood]').forEach((b) => b.addEventListener('click', () => startHood(b.dataset.hood, $('short').checked)));
$('reset-air').addEventListener('click', () => { session.phase = 'idle'; session.food = null; state.module = [...CLEAN_AIR]; applyADC(); syncSliders(); ledFrame = blank(); log('clean air restored'); });
$('pause').addEventListener('click', (e) => { running = !running; e.target.textContent = running ? 'Pause MCU' : 'Resume MCU'; });

function render() {
  $('simtime').textContent = simSeconds.toFixed(1);
  $('samples').textContent = sampleCount;
  SENSORS.forEach((s, k) => {
    const vm = state.module[k], vp = vm * DIV;
    $(`vm-${s}`).textContent = vm.toFixed(2) + ' V';
    $(`out-${s}`).textContent = vm.toFixed(2) + ' V';
    $(`vp-${s}`).textContent = vp.toFixed(2) + ' V';
    $(`vpin-${s}`).textContent = vp.toFixed(2) + ' V';
    $(`raw-${s}`).textContent = latest ? latest[k] : '–';
    $(`dec-${s}`).textContent = latest ? volts(latest[k]).toFixed(3) + ' V' : '–';
    $(`wire-${s}`).style.strokeWidth = 2 + 4 * Math.min(1, Math.max(0, (vp - 0.4) / 2.6));
  });
  $('val-temp').textContent = state.temp.toFixed(1) + ' °C';
  $('val-rh').textContent = state.rh.toFixed(0) + ' %';
  $('dec-dht').textContent = latest ? (latest[5] ? `${latest[3].toFixed(1)} °C / ${latest[4].toFixed(1)} %` : 'no valid read') : '–';
  const active = performance.now() - state.dhtActivity < 250;
  $('wire-d2').classList.toggle('active', active);
  $('phase').textContent = { idle: 'idle', A: 'A · baseline (open air)', M: 'M · move box over food', H: 'H · hood over food', V: 'V · venting', done: 'done' }[session.phase];
  const cells = document.querySelectorAll('#matrix i');
  ledFrame.forEach((v, i) => cells[i].classList.toggle('on', v > 0));
  if (session.result) {
    $('result').innerHTML = session.result.feats.map((f) =>
      `<tr><td>${f.s.toUpperCase()}</td><td>${f.d_median.toFixed(3)}</td><td>${f.d_peak.toFixed(3)}</td><td>${f.d_mean.toFixed(3)}</td></tr>`).join('');
  }
}
window.PGAS_SIM = { state, session, get latest() { return latest; }, get samples() { return sampleCount; }, startHood };
function start() {
  const m = $('matrix');
  for (let i = 0; i < 104; i++) m.appendChild(document.createElement('i'));
  syncSliders();
  last = performance.now();
  requestAnimationFrame(frame);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
