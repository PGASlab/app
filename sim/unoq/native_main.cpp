// Native runner: the sketch's UNO Q code path on the emulated MCU API, talking
// line-by-line over stdin/stdout so the REAL Python Linux side can drive it
// (sim/unoq/run_unoq.py). Real-time paced.
//   stdout: N,<method>,<args...>   Bridge.notify      M,<104 digits>  matrix frame   R  DHT read
//   stdin:  G v0 v1 v2 | E t h | D 0|1 | F <208 hex chars> (Bridge.call draw) | Q
#include <chrono>
#include <thread>
#include <fcntl.h>
#include <unistd.h>
#include "hal/unoq_hal.h"

extern "C" {
void hal_setup();
void hal_run_us(double us);
void hal_set_module(int ch, double v);
void hal_set_env(double t, double h);
void hal_set_dht_connected(int c);
void hal_bridge_draw(const uint8_t *f);
void hal_on_notify(const char *t) { printf("N,%s\n", t); fflush(stdout); }
void hal_on_matrix(const uint8_t *f) {
  char b[106]; for (int i = 0; i < 104; i++) b[i] = '0' + (f[i] > 9 ? 9 : f[i]); b[104] = 0;
  printf("M,%s\n", b); fflush(stdout);
}
void hal_on_dht_read(void) {}
}

int main() {
  fcntl(0, F_SETFL, fcntl(0, F_GETFL) | O_NONBLOCK);
  hal_setup();
  std::string buf;
  auto t0 = std::chrono::steady_clock::now();
  double sim_ms = 0;
  for (;;) {
    char c;
    while (read(0, &c, 1) == 1) {
      if (c != '\n') { buf += c; continue; }
      double a, b, d;
      if (buf[0] == 'G' && sscanf(buf.c_str() + 1, "%lf %lf %lf", &a, &b, &d) == 3) { hal_set_module(0, a); hal_set_module(1, b); hal_set_module(2, d); }
      else if (buf[0] == 'E' && sscanf(buf.c_str() + 1, "%lf %lf", &a, &b) == 2) hal_set_env(a, b);
      else if (buf[0] == 'D') hal_set_dht_connected(atoi(buf.c_str() + 1));
      else if (buf[0] == 'F' && buf.size() >= 2 + 208) {
        uint8_t f[104];
        for (int i = 0; i < 104; i++) f[i] = (uint8_t)strtol(buf.substr(2 + 2 * i, 2).c_str(), nullptr, 16);
        hal_bridge_draw(f);
      } else if (buf[0] == 'Q') return 0;
      buf.clear();
    }
    hal_run_us(10000);
    sim_ms += 10;
    std::this_thread::sleep_until(t0 + std::chrono::microseconds((long long)(sim_ms * 1000)));
  }
}
