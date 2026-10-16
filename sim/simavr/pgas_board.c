/*
 * PGAS virtual board for simavr: runs the real sketch (built for ATmega328P by
 * sim/build_avr.sh) against simulated wiring.
 *
 *   MQ module output (volts, set from stdin) -> 10k/20k divider -> A0/A1/A2
 *   DHT22 on PD2 (Arduino D2) with a 10k pull-up: a timing-level model of the
 *   sensor protocol (start pulse, 80/80 us response, 40 bits, checksum)
 *   UART0 -> stdout (the sketch's "S,..." lines)
 *
 * stdin commands (one per line):
 *   G <v_mq135> <v_mq3> <v_mq2>   module output volts (before the divider)
 *   E <temp_c> <rh_pct>           DHT22 values
 *   D <0|1>                       DHT22 disconnected (1) / connected (0)
 *   Q                             quit
 *
 * Runs in real time (simulated time is throttled to the wall clock), so the
 * Linux-side code sees samples at 1 Hz exactly as on the board.
 * Usage: pgas_board <firmware.elf> [speed]
 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <simavr/avr_adc.h>
#include <simavr/avr_ioport.h>
#include <simavr/avr_uart.h>
#include <simavr/sim_avr.h>
#include <simavr/sim_elf.h>
#include <simavr/sim_time.h>

#define DIV_RATIO (20.0 / (10.0 + 20.0))
#define DDRD_ADDR 0x2A
#define PORTD_ADDR 0x2B
#define DHT_BIT 2

static avr_t *avr;
static avr_irq_t *dht_pin;
static double module_v[3] = {0.8, 0.6, 0.7};
static double env_t = 26.0, env_h = 60.0;
static int dht_disconnected = 0;
static double speed = 1.0;

/* ---------------- ADC: divider ---------------- */
static void apply_adc(void) {
  for (int i = 0; i < 3; i++) {
    double pin_mv = module_v[i] * DIV_RATIO * 1000.0;
    avr_raise_irq(avr_io_getirq(avr, AVR_IOCTL_ADC_GETIRQ, ADC_IRQ_ADC0 + i), (uint32_t)(pin_mv + 0.5));
  }
}

/* ---------------- DHT22 model ---------------- */
static struct { int level; uint32_t us; } seq[90];
static int seq_n, seq_i;
static int line_low_since_valid;
static avr_cycle_count_t low_start;
static int prev_driving_low;

static void set_line(int level) { avr_raise_irq(dht_pin, level); }

static avr_cycle_count_t seq_step(avr_t *a, avr_cycle_count_t when, void *p) {
  (void)a; (void)when; (void)p;
  if (seq_i >= seq_n) { set_line(1); return 0; }   /* release: pull-up */
  set_line(seq[seq_i].level);
  uint32_t us = seq[seq_i].us;
  seq_i++;
  avr_cycle_timer_register_usec(avr, us, seq_step, NULL);
  return 0;
}

static void start_response(void) {
  int h = (int)(env_h * 10 + 0.5), t = (int)(env_t * 10 + (env_t >= 0 ? 0.5 : -0.5));
  uint8_t d[5];
  d[0] = (h >> 8) & 0xFF; d[1] = h & 0xFF;
  int ta = t < 0 ? -t : t;
  d[2] = ((ta >> 8) & 0x7F) | (t < 0 ? 0x80 : 0); d[3] = ta & 0xFF;
  d[4] = (uint8_t)(d[0] + d[1] + d[2] + d[3]);
  seq_n = 0;
  seq[seq_n++] = (typeof(seq[0])){1, 30};   /* host releases; sensor waits ~30 us */
  seq[seq_n++] = (typeof(seq[0])){0, 80};
  seq[seq_n++] = (typeof(seq[0])){1, 80};
  for (int i = 0; i < 40; i++) {
    int bit = (d[i / 8] >> (7 - i % 8)) & 1;
    seq[seq_n++] = (typeof(seq[0])){0, 50};
    seq[seq_n++] = (typeof(seq[0])){1, bit ? 70 : 26};
  }
  seq[seq_n++] = (typeof(seq[0])){0, 50};
  seq_i = 0;
  seq_step(avr, 0, NULL);
}

/* Poll the MCU's DDRD/PORTD to see the start pulse and the release. */
static avr_cycle_count_t dht_poll(avr_t *a, avr_cycle_count_t when, void *p) {
  (void)p;
  int ddr = (a->data[DDRD_ADDR] >> DHT_BIT) & 1;
  int port = (a->data[PORTD_ADDR] >> DHT_BIT) & 1;
  int driving_low = ddr && !port;
  if (driving_low && !prev_driving_low) { low_start = when; line_low_since_valid = 1; }
  if (!driving_low && prev_driving_low && line_low_since_valid) {
    double low_us = (double)(when - low_start) * 1e6 / a->frequency;
    line_low_since_valid = 0;
    if (!ddr && low_us >= 1000 && !dht_disconnected && seq_i >= seq_n) start_response();
  }
  prev_driving_low = driving_low;
  return when + avr_usec_to_cycles(a, 20);
}

/* ---------------- UART -> stdout ---------------- */
static void uart_out(struct avr_irq_t *irq, uint32_t value, void *param) {
  (void)irq; (void)param;
  putchar((int)value);
  if (value == '\n') fflush(stdout);
}

/* ---------------- stdin control ---------------- */
static char inbuf[256];
static size_t inlen;
static int quit;

static void handle_line(char *s) {
  if (s[0] == 'G') sscanf(s + 1, "%lf %lf %lf", &module_v[0], &module_v[1], &module_v[2]), apply_adc();
  else if (s[0] == 'E') sscanf(s + 1, "%lf %lf", &env_t, &env_h);
  else if (s[0] == 'D') dht_disconnected = atoi(s + 1);
  else if (s[0] == 'Q') quit = 1;
}

static avr_cycle_count_t io_tick(avr_t *a, avr_cycle_count_t when, void *p) {
  (void)p;
  char c;
  while (read(0, &c, 1) == 1) {
    if (c == '\n') { inbuf[inlen] = 0; handle_line(inbuf); inlen = 0; }
    else if (inlen < sizeof inbuf - 1) inbuf[inlen++] = c;
  }
  /* Real-time throttle: keep simulated time <= wall time * speed. */
  static struct timespec t0; static int init;
  struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
  if (!init) { t0 = now; init = 1; }
  double wall = (now.tv_sec - t0.tv_sec) + (now.tv_nsec - t0.tv_nsec) / 1e9;
  double sim = (double)when / a->frequency;
  if (sim > wall * speed) usleep((useconds_t)((sim - wall * speed) / speed * 1e6));
  return when + avr_usec_to_cycles(a, 10000);
}

int main(int argc, char **argv) {
  if (argc < 2) { fprintf(stderr, "usage: %s firmware.elf [speed]\n", argv[0]); return 64; }
  if (argc > 2) speed = atof(argv[2]);
  elf_firmware_t fw = {0};
  if (elf_read_firmware(argv[1], &fw)) { fprintf(stderr, "cannot read %s\n", argv[1]); return 1; }
  avr = avr_make_mcu_by_name("atmega328p");
  if (!avr) return 1;
  avr_init(avr);
  avr->frequency = 16000000;
  avr->avcc = 5000; avr->aref = 5000; avr->vcc = 5000;
  avr_load_firmware(avr, &fw);

  uint32_t f = 0;
  avr_ioctl(avr, AVR_IOCTL_UART_GET_FLAGS('0'), &f);
  f &= ~AVR_UART_FLAG_STDIO;
  avr_ioctl(avr, AVR_IOCTL_UART_SET_FLAGS('0'), &f);
  avr_irq_register_notify(avr_io_getirq(avr, AVR_IOCTL_UART_GETIRQ('0'), UART_IRQ_OUTPUT), uart_out, NULL);

  dht_pin = avr_io_getirq(avr, AVR_IOCTL_IOPORT_GETIRQ('D'), DHT_BIT);
  seq_i = seq_n = 0;
  set_line(1);  /* 10k pull-up */
  apply_adc();
  fcntl(0, F_SETFL, fcntl(0, F_GETFL) | O_NONBLOCK);
  avr_cycle_timer_register_usec(avr, 20, dht_poll, NULL);
  avr_cycle_timer_register_usec(avr, 10000, io_tick, NULL);

  int state = cpu_Running;
  while (!quit && state != cpu_Done && state != cpu_Crashed) state = avr_run(avr);
  fflush(stdout);
  return state == cpu_Crashed ? 2 : 0;
}
