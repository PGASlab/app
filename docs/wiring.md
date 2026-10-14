# Wiring

The wiring is fixed. The code adapts to it, never the other way round.

| Signal | From | To UNO Q | Through |
|---|---|---|---|
| MQ-135 AO | MQ-135 module | **A0** | 10 kΩ series (top) + 20 kΩ to GND (bottom) |
| MQ-3 AO | Waveshare MQ-3 module | **A1** | same 10 kΩ / 20 kΩ divider |
| MQ-2 AO | MQ-2 module | **A2** | same 10 kΩ / 20 kΩ divider |
| DHT22 DATA | DHT22 / AM2302 (bare part) | **D2** | 10 kΩ pull-up from DATA to 3.3 V |
| DHT22 VCC | DHT22 | **3.3 V** | — |
| MQ VCC (heaters) | all three MQ modules | **5 V** | — |
| GND | everything | **GND** | one common ground |

```
 MQ module AO ──[10k]──┬── A0 / A1 / A2
                       │
                     [20k]
                       │
 GND ──────────────────┴── GND

 3.3V ──┬───────── DHT22 VCC
       [10k]
        │
 D2 ────┴───────── DHT22 DATA         DHT22 GND ── GND
```

## Voltage budget

The UNO Q MCU pins use 3.3 V logic. Per Arduino's UNO Q power specification, the
analog pins are **not 5 V tolerant** and their absolute maximum is about 3.6 V.

The divider scales every MQ output by 20 / (10 + 20) = **2/3**:

| MQ module output | Voltage at the pin |
|---|---|
| 1.0 V (typical clean-air region) | 0.67 V |
| 4.5 V | 3.00 V |
| 4.95 V | 3.30 V |
| 5.00 V (output at its 5 V rail) | **3.33 V** |
| 5.10 V (rail at 5.1 V, output at the rail) | **3.40 V** |

> **Important.** A module output can only reach its supply rail in extreme gas
> concentrations. If it does, the pin sees slightly **more than 3.3 V** (3.33 V
> at 5.00 V). That is below the 3.6 V absolute maximum but above the 3.3 V
> logic level. `pgas.selftest` fails any channel above 97 % of full scale
> (about 3.2 V). If you want a hard margin, change the bottom resistor to 18 kΩ:
> a 5.1 V output then gives 3.28 V. This is a wiring change, so it is the
> builder's call. The code reads the ratio from `pgas/config.py`
> (`DIVIDER_BOTTOM_OHM`).

D2 is never driven high by the sketch. To start a DHT22 read the sketch drives D2
LOW for 2 ms, then releases it to the 10 kΩ pull-up, which goes to 3.3 V.

## Before inserting the MQ modules (multimeter checks)

Do these with the board powered over USB-C and the MQ modules **not** plugged in:

1. 5 V rail to GND: expect about 5 V. Write down the exact value.
2. 3.3 V rail to GND: expect about 3.3 V.
3. Each divider midpoint (the A0/A1/A2 node) to GND, with **5 V applied to the
   divider's top end** (the wire that will go to the module AO): expect
   2/3 of the rail you measured in step 1, under 3.4 V.
4. With nothing driving the dividers: each midpoint reads about 0 V (the 20 kΩ
   pulls it to GND).

## Inside the K-812 box

All sensors are mounted on the inside of the box, so the same box works in both
measurement modes. Leave a few millimetres between the MQ heaters and the plastic.
The heaters run warm, and the DHT22 should sit as far from them as possible, or it
will read the heater temperature instead of the air.
