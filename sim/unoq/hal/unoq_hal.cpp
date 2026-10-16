// Virtual clock, DHT22 model and host entry points for unoq_hal.h.
#include "unoq_hal.h"

BridgeClass Bridge;
void setup();
void loop();

namespace hal {
uint64_t now_us = 0;
double module_v[3] = {1.00, 0.80, 0.90};
double temp_c = 26.5, rh_pct = 65.0;
bool dht_connected = true;
int adc_bits = 10;  // Arduino default until analogReadResolution()

// D2 line: the MCU drives it (OUTPUT) or releases it to the 10k pull-up, and
// the DHT22 pulls it low while it answers.
static int d2_dir = INPUT, d2_out = HIGH;
static uint64_t low_since = 0;
static bool start_pulse = false;
static std::vector<std::pair<uint64_t, int>> resp;  // (time_us, level) edges of the sensor reply

void tick(uint64_t us) { now_us += us; }

static void start_response() {
  int h = (int)std::lround(rh_pct * 10), t = (int)std::lround(temp_c * 10), ta = t < 0 ? -t : t;
  uint8_t d[5] = {(uint8_t)(h >> 8), (uint8_t)h, (uint8_t)(((ta >> 8) & 0x7F) | (t < 0 ? 0x80 : 0)), (uint8_t)ta, 0};
  d[4] = (uint8_t)(d[0] + d[1] + d[2] + d[3]);
  resp.clear();
  uint64_t t0 = now_us + 30;  // sensor answers ~30 us after release
  auto edge = [&](int level, uint64_t dur) { resp.push_back({t0, level}); t0 += dur; };
  edge(LOW, 80);
  edge(HIGH, 80);
  for (int i = 0; i < 40; i++) {
    int bit = (d[i / 8] >> (7 - i % 8)) & 1;
    edge(LOW, 50);
    edge(HIGH, bit ? 70 : 26);
  }
  edge(LOW, 50);
  resp.push_back({t0, HIGH});
  hal_on_dht_read();
}

// The line is driven low whenever the pin is an OUTPUT holding LOW, however
// that state was reached (pinMode after digitalWrite, or the other way round).
static void update_drive() {
  bool low = d2_dir == OUTPUT && d2_out == LOW;
  if (low && !start_pulse) { low_since = now_us; start_pulse = true; }
}

void d2_mode(int mode) {
  if (d2_dir == OUTPUT && mode == INPUT && start_pulse) {
    start_pulse = false;
    if (now_us - low_since >= 1000 && dht_connected) start_response();
  }
  d2_dir = mode;
  update_drive();
}

void d2_write(int level) {
  if (level == HIGH) start_pulse = false;
  d2_out = level;
  update_drive();
}

int d2_level() {
  if (d2_dir == OUTPUT) return d2_out;
  int level = HIGH;  // pull-up
  for (auto &e : resp) {
    if (e.first <= now_us) level = e.second; else break;
  }
  return level;
}
}  // namespace hal

extern "C" {
void hal_setup() { setup(); }
// Run loop() until the virtual clock has advanced by `us`.
void hal_run_us(double us) {
  uint64_t end = hal::now_us + (uint64_t)us;
  while (hal::now_us < end) loop();
}
double hal_time_ms() { return (double)hal::now_us / 1000.0; }
void hal_set_module(int ch, double volts) { if (ch >= 0 && ch < 3) hal::module_v[ch] = volts; }
void hal_set_env(double t, double h) { hal::temp_c = t; hal::rh_pct = h; }
void hal_set_dht_connected(int c) { hal::dht_connected = c != 0; }
// Linux side -> Bridge.call("draw", frame)
void hal_bridge_draw(const uint8_t *frame) {
  auto it = Bridge.draw_handlers.find("draw");
  if (it != Bridge.draw_handlers.end()) it->second(std::vector<uint8_t>(frame, frame + 104));
}
}
