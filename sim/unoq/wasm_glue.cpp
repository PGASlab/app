// Browser hooks: forward Bridge.notify / matrix.draw / DHT activity to JS.
#include <emscripten.h>
#include <cstdint>

EM_JS(void, js_notify, (const char *t), { if (Module.onNotify) Module.onNotify(UTF8ToString(t)); });
EM_JS(void, js_matrix, (const uint8_t *f), { if (Module.onMatrix) Module.onMatrix(Array.from(HEAPU8.subarray(f, f + 104))); });
EM_JS(void, js_dht, (), { if (Module.onDht) Module.onDht(); });

extern "C" {
void hal_on_notify(const char *t) { js_notify(t); }
void hal_on_matrix(const uint8_t *f) { js_matrix(f); }
void hal_on_dht_read(void) { js_dht(); }
}
