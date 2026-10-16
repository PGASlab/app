// Emulated Arduino UNO Q MCU API for software-in-the-loop simulation of
// app/sketch/sketch.ino (its UNO Q code path, not the AVR one).
//
// Emulates exactly what the sketch uses: analogReadResolution/analogRead
// (3.3 V reference), pinMode/digitalWrite/digitalRead, delay/millis/micros on
// a virtual microsecond clock, Bridge.begin/provide/notify (Arduino_RouterBridge),
// Arduino_LED_Matrix (8x13, 3-bit grayscale) - plus the PGAS wiring around the
// MCU: MQ module outputs -> 10k/20k dividers -> A0..A2, and a DHT22 on D2
// with a 10k pull-up, modelled at protocol-timing level.
//
// The host (WebAssembly page or native runner) provides four hooks:
//   hal_on_notify(text)      Bridge.notify(...) -> "method,arg1,arg2,..."
//   hal_on_matrix(frame104)  matrix.draw(...)
//   hal_on_dht_read()        a DHT22 transaction started (for the UI)
//   and drives the MCU with hal_setup() / hal_run_us(us) / hal_bridge_draw(...)
#pragma once
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <functional>
#include <map>
#include <string>
#include <vector>

#define LOW 0
#define HIGH 1
#define INPUT 0
#define OUTPUT 1
#define A0 14
#define A1 15
#define A2 16

using std::min;

extern "C" void hal_on_notify(const char *text);
extern "C" void hal_on_matrix(const uint8_t *frame);
extern "C" void hal_on_dht_read(void);

namespace hal {
extern uint64_t now_us;
extern double module_v[3];
extern double temp_c, rh_pct;
extern bool dht_connected;
extern int adc_bits;
void tick(uint64_t us);
int d2_level();
void d2_mode(int mode);
void d2_write(int level);
}

inline void analogReadResolution(int bits) { hal::adc_bits = bits; }
inline int analogRead(int pin) {
  hal::tick(2);  // conversion time
  int ch = pin - A0;
  if (ch < 0 || ch > 2) return 0;
  double pin_v = hal::module_v[ch] * 20.0 / (10.0 + 20.0);
  if (pin_v > 3.3) pin_v = 3.3;
  if (pin_v < 0) pin_v = 0;
  int full = (1 << hal::adc_bits) - 1;
  return (int)std::lround(pin_v / 3.3 * full);
}
inline void pinMode(int pin, int mode) { if (pin == 2) hal::d2_mode(mode); }
inline void digitalWrite(int pin, int level) { if (pin == 2) hal::d2_write(level); }
inline int digitalRead(int pin) { hal::tick(1); return pin == 2 ? hal::d2_level() : 0; }
inline uint32_t micros() { hal::tick(1); return (uint32_t)hal::now_us; }
inline unsigned long millis() { return (unsigned long)(hal::now_us / 1000); }
inline void delay(unsigned long ms) { hal::tick((uint64_t)ms * 1000); }

// ---- Arduino_RouterBridge -------------------------------------------------
class BridgeClass {
 public:
  bool begin() { return true; }
  void provide(const char *name, void (*fn)(std::vector<uint8_t>)) { draw_handlers[name] = fn; }
  template <class... A> void notify(const char *method, A... args) {
    std::string s(method);
    (append(s, args), ...);
    hal_on_notify(s.c_str());
  }
  std::map<std::string, void (*)(std::vector<uint8_t>)> draw_handlers;

 private:
  static void append(std::string &s, int v) { s += "," + std::to_string(v); }
  static void append(std::string &s, long v) { s += "," + std::to_string(v); }
  static void append(std::string &s, unsigned long v) { s += "," + std::to_string(v); }
  static void append(std::string &s, double v) { char b[32]; snprintf(b, sizeof b, ",%.1f", v); s += b; }
  static void append(std::string &s, float v) { append(s, (double)v); }
};
extern BridgeClass Bridge;

// ---- Arduino_LED_Matrix ---------------------------------------------------
class Arduino_LED_Matrix {
 public:
  void begin() {}
  void setGrayscaleBits(int) {}
  void clear() { uint8_t z[104] = {0}; hal_on_matrix(z); }
  void draw(uint8_t *frame) { hal_on_matrix(frame); }
};
