# pico-clock-rectangular

A **MicroPython clock** for the **Waveshare RP2350-LCD-1.47-A** — a rectangular **172×320** ST7789 IPS board.

```
   00:42                  ← HH:MM        (white)
    17                    ← seconds       (cyan)
 3 Nov 2026               ← date          (cyan)
  Tuesday                 ← weekday       (blue)
  35.5 C                  ← chip temp     (amber)
```

The onboard **WS2812B RGB LED (GP22)** pulses a bright colour once a second (12 colours), and
turns **solid red** when it hasn't received the time for a while.

## Board facts

| | |
|---|---|
| MCU | RP2350A (dual Cortex‑M33 + dual Hazard3), 150 MHz, 520 KB SRAM, 16 MB flash |
| Display | 1.47″ 172×320 IPS, **ST7789V3**, SPI (SCK 18, MOSI 19, DC 16, CS 17, RST 20, BL 21) |
| RGB LED | WS2812B on **GP22** |
| Sensors | **on-chip temperature** only (ADC ch4). No IMU. |
| Radios | **none** — no WiFi, no Bluetooth |
| RTC | none battery-backed (software RTC only) |
| Storage | microSD/TF slot (SPI) |

## Why a host is needed (and how it's handled)

The board can't know the time by itself (no WiFi, no battery-backed RTC), so a host sends it over
**USB serial**:

```
host -> S|DT:YYYY-MM-DD:HH:MM:SS:WD|TS:HH:MM:SS      (WD: 0=Mon … 6=Sun)
pico -> K                                            (ack)
```

To make it work **without** the host, the app **persists the time to flash** (`clock.dat`), written
on every sync *and once a minute*. At boot it restores the RTC from that file, so after a power cycle
it resumes from the last known time instead of showing `syncing…`.

> Limitation: the RP2350 has no battery-backed clock, so it can't know how long it was powered off,
> and its RTC drifts a few seconds/day. It is exact while a host syncs; otherwise it resumes from the
> last saved time. For true standalone accuracy add an I²C RTC (e.g. DS3231 + coin cell).

## Files

| File | Runs on | Purpose |
|------|---------|---------|
| `main.py` | the Pico | the clock + LED |
| `time_pusher.py` | your computer | sends the current time over USB serial (stdlib only, auto-reconnects) |

`lcd.py` (the `LCD_1inch47` display driver) ships with Waveshare's demo and is **not** included here.

## Install

1. Flash MicroPython for the Pico 2 / RP2350, and copy the Waveshare `lcd.py` next to these files.
2. Copy the clock to the board:
   ```bash
   mpremote connect /dev/ttyACM0 fs cp main.py :main.py
   ```
3. On the host:
   ```bash
   python3 time_pusher.py                 # auto-detects the port, pushes every 5 s
   ```

## Gotchas discovered the hard way

1. **The `neopixel` module does not work on this board.** It initialises without error but never
   drives the LEDs (they sit stuck on white). Use Waveshare's **PIO** driver — that's what `main.py`
   does (`rp2.asm_pio` + `StateMachine(0, …, freq=8_000_000, sideset_base=Pin(22))`, GRB via
   `put((g<<24)|(r<<16)|(b<<8))`).
2. **The LCD often fails to initialise at boot** → blank screen. Fix (in `main.py`): `time.sleep(1)`
   *before* creating the display, then re-assert `lcd.init_display()`.
3. **Never apply a "white boost" to the OFF colour.** Writing `(30,30,30)` for "off" makes the LED
   glow dim white — the off value must be exactly `(0,0,0)`.
4. No WiFi/BT: `import network` / `import bluetooth` both fail.

## License

MIT
