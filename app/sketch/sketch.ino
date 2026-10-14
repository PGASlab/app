// PGAS - AI Nose, MCU side (STM32U585 on the Arduino UNO Q).
//
// Once per second: read MQ-135 (A0), MQ-3 (A1), MQ-2 (A2) and the last good
// DHT22 (D2) values, and push them to Linux with
//   Bridge.notify("pgas_sample", a0, a1, a2, temp_c, rh_pct, dht_ok)
// Linux sends LED-matrix frames back with Bridge.call("draw", <104 bytes>).
//
// Wiring (do not change): each MQ output goes through a 10k (top) / 20k
// (bottom) divider, so a 5 V output reaches the pin as 3.33 V. DHT22 data on
// D2 with a 10k pull-up to 3.3 V. No pin is ever driven above 3.3 V: D2 is
// only driven LOW (start pulse) or released to the pull-up.

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <vector>

const int DHT_PIN = 2;
const int ADC_BITS = 14;               // must match pgas/config.py
const int ADC_OVERSAMPLE = 16;         // average 16 conversions per reading
const unsigned long SAMPLE_MS = 1000;  // 1 Hz
const unsigned long DHT_MS = 2000;     // DHT22 needs >= 2 s between reads
const unsigned long DHT_STALE_MS = 10000;

Arduino_LED_Matrix matrix;
const size_t FRAME_SIZE = 8 * 13;
uint8_t frame[FRAME_SIZE] = {0};
volatile bool frameDirty = false;

float dhtTemp = 0, dhtHum = 0;
unsigned long dhtGoodAt = 0;
bool dhtEverGood = false;
unsigned long lastSample = 0, lastDht = 0;

// Runs on the Bridge RPC thread: only copy, draw from loop().
void draw(std::vector<uint8_t> newFrame) {
  size_t len = min(newFrame.size(), FRAME_SIZE);
  memcpy(frame, newFrame.data(), len);
  frameDirty = true;
}

static bool waitLevel(int level, uint32_t timeoutUs) {
  uint32_t start = micros();
  while (digitalRead(DHT_PIN) != level) {
    if (micros() - start > timeoutUs) return false;
  }
  return true;
}

// Bit-banged DHT22 read. Interrupts stay enabled so the Bridge UART is never
// starved; a read disturbed by an interrupt fails the checksum and is simply
// retried 2 s later.
bool readDHT22(float &t, float &h) {
  uint8_t d[5] = {0, 0, 0, 0, 0};
  pinMode(DHT_PIN, OUTPUT);
  digitalWrite(DHT_PIN, LOW);
  delay(2);                       // start signal >= 1 ms
  pinMode(DHT_PIN, INPUT);        // release: the 10k pull-up takes it high
  if (!waitLevel(LOW, 200)) return false;   // sensor response: 80 us low
  if (!waitLevel(HIGH, 200)) return false;  // 80 us high
  if (!waitLevel(LOW, 200)) return false;   // first bit starts
  for (int i = 0; i < 40; i++) {
    if (!waitLevel(HIGH, 200)) return false;  // 50 us low
    uint32_t start = micros();
    if (!waitLevel(LOW, 200)) return false;   // 26-28 us = 0, 70 us = 1
    d[i / 8] <<= 1;
    if (micros() - start > 45) d[i / 8] |= 1;
  }
  if ((uint8_t)(d[0] + d[1] + d[2] + d[3]) != d[4]) return false;
  h = ((d[0] << 8) | d[1]) * 0.1f;
  t = (((d[2] & 0x7F) << 8) | d[3]) * 0.1f;
  if (d[2] & 0x80) t = -t;
  return h >= 0 && h <= 100 && t > -40 && t < 80;
}

int readAvg(int pin) {
  long sum = 0;
  for (int i = 0; i < ADC_OVERSAMPLE; i++) sum += analogRead(pin);
  return (int)(sum / ADC_OVERSAMPLE);
}

void setup() {
  analogReadResolution(ADC_BITS);
  pinMode(DHT_PIN, INPUT);
  matrix.begin();
  matrix.setGrayscaleBits(3);
  matrix.clear();
  Bridge.begin();
  Bridge.provide("draw", draw);
}

void loop() {
  unsigned long now = millis();

  if (frameDirty) {
    frameDirty = false;
    matrix.draw(frame);
  }

  if (now - lastDht >= DHT_MS) {
    lastDht = now;
    float t, h;
    if (readDHT22(t, h)) {
      dhtTemp = t;
      dhtHum = h;
      dhtGoodAt = millis();
      dhtEverGood = true;
    }
  }

  if (now - lastSample >= SAMPLE_MS) {
    lastSample = now;
    int a0 = readAvg(A0);
    int a1 = readAvg(A1);
    int a2 = readAvg(A2);
    int dhtOk = (dhtEverGood && millis() - dhtGoodAt < DHT_STALE_MS) ? 1 : 0;
    Bridge.notify("pgas_sample", a0, a1, a2, dhtTemp, dhtHum, dhtOk);
  }

  delay(5);
}
