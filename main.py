# Clock + RGB LED — Waveshare RP2350-LCD-1.47-A (172x320, ST7789) — MicroPython
#
# LED = WS2812B on GP22, driven with Waveshare's PIO program (the `neopixel` module
# does NOT work on this board).
#   - one bright colour pulse every second (12 colours, repeating)
#   - OFF between pulses
#   - solid red if no time has been received for >15 s
#
# No RTC/WiFi on the board, so the host sends the time over USB serial:
#     S|DT:YYYY-MM-DD:HH:MM:SS:WD|TS:HH:MM:SS
import gc
import select
import sys
import time

import framebuf
import rp2
from machine import RTC, Pin, ADC
from lcd import LCD_1inch47

try:
    @rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW, out_shiftdir=rp2.PIO.SHIFT_LEFT,
                 autopull=True, pull_thresh=24)
    def _ws2812():
        T1, T2, T3 = 2, 5, 3
        wrap_target()
        label("bitloop")
        out(x, 1).side(0)[T3 - 1]
        jmp(not_x, "do_zero").side(1)[T1 - 1]
        jmp("bitloop").side(1)[T2 - 1]
        label("do_zero")
        nop().side(0)[T2 - 1]
        wrap()

    _sm = rp2.StateMachine(0, _ws2812, freq=8_000_000, sideset_base=Pin(22))
    _sm.active(1)
    HAVE_LED = True
except Exception as _e:
    _sm = None
    HAVE_LED = False
    _led_err = _e

W = 172

WHITE = 0xFFFF
BG    = 0x0841
DIM   = 0x4A69
CYAN  = 0x07FF
BLUE  = 0x249F
AMBER = 0xFD20

DOW = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

STALE_S = 15            # no time for this long -> red LED
FLASH_S = 0.50          # how long the colour stays on each second
COLOURS = 12            # distinct colours per cycle


def hsv(h, v):
    """h in 0..1 (colour), v in 0..1 (brightness) -> (r,g,b) 0..255."""
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    q = v * (1 - f)
    t = v * f
    r, g, b = [(v, t, 0), (q, v, 0), (0, v, t), (0, q, v), (t, 0, v), (v, 0, q)][i]
    return int(r * 255), int(g * 255), int(b * 255)


def led(r, g, b):
    if HAVE_LED:
        _sm.put((g << 24) | (r << 16) | (b << 8))   # WS2812 wants GRB order


TIME_FILE = "clock.dat"        # last known time, so the clock survives a power cycle


def save_time():
    t = time.localtime()
    try:
        with open(TIME_FILE, "w") as f:
            f.write("%d,%d,%d,%d,%d,%d,%d" % (t[0], t[1], t[2], t[3], t[4], t[5], t[6]))
    except Exception:
        pass


def load_time():
    """Restore the RTC from flash at boot. Returns True if a saved time was found."""
    try:
        with open(TIME_FILE) as f:
            p = f.read().strip().split(",")
        rtc.datetime((int(p[0]), int(p[1]), int(p[2]), int(p[6]),
                      int(p[3]), int(p[4]), int(p[5]), 0))
        return True
    except Exception:
        return False


gc.collect()
time.sleep(1)            # let the panel settle after power-up (Waveshare's demo does this)
lcd = LCD_1inch47()
time.sleep(0.2)
lcd.init_display()       # re-assert the init sequence (the first one after boot can be missed)
rtc = RTC()
time_set = load_time()   # resume from the last saved time if we have one

poll = select.poll()
poll.register(sys.stdin, select.POLLIN)

last_rx = 0
_led_until = 0
_led_on = False
_glyph = bytearray(8 * 8 * 2)
_gfb = framebuf.FrameBuffer(_glyph, 8, 8, framebuf.RGB565)

temp_adc = ADC(4)          # RP2350 on-chip temperature sensor


def read_temp():
    v = temp_adc.read_u16() * 3.3 / 65535
    return 27 - (v - 0.706) / 0.001721


def text(s, x, y, scale, color):
    for i, ch in enumerate(s):
        _gfb.fill(BG)
        _gfb.text(ch, 0, 0, color)
        cx = x + i * 8 * scale
        for yy in range(8):
            for xx in range(8):
                if _gfb.pixel(xx, yy) != BG:
                    lcd.fill_rect(cx + xx * scale, y + yy * scale, scale, scale, color)


def ctext(s, y, scale, color):
    text(s, max(0, (W - len(s) * 8 * scale) // 2), y, scale, color)


def draw_clock():
    lcd.fill(BG)
    if not time_set:
        ctext("CLOCK", 120, 2, CYAN)
        ctext("syncing...", 160, 1, DIM)
    else:
        t = time.localtime()
        ctext("%02d:%02d" % (t[3], t[4]), 70, 4, WHITE)
        ctext("%02d" % t[5], 122, 3, CYAN)
        ctext("%d %s %d" % (t[2], MON[t[1] - 1], t[0]), 176, 2, CYAN)
        ctext(DOW[t[6]], 220, 2, BLUE)
        ctext("%.1f C" % read_temp(), 262, 2, AMBER)
    lcd.show()


def handle(line):
    global time_set, last_rx
    line = line.strip()
    if not (line.startswith("S|") or line.startswith("F|")):
        return False
    for part in line.split("|")[1:]:
        f = part.split(":")
        if f[0] == "DT":
            try:
                y, mo, d = f[1].split("-")
                rtc.datetime((int(y), int(mo), int(d), int(f[5]),
                              int(f[2]), int(f[3]), int(f[4]), 0))
                time_set = True
                save_time()
            except Exception:
                pass
    last_rx = time.time()
    return True


gc.collect()
draw_clock()
_tick = time.time()
_saved_min = time.localtime()[4]

while True:
    if poll.poll(0):
        try:
            line = sys.stdin.readline()
        except Exception:
            line = ""
        if line and handle(line):
            print("K")
            draw_clock()

    now = time.time()

    if now - _tick >= 1.0:                    # once a second
        _tick = now
        draw_clock()
        if time.localtime()[4] != _saved_min:  # once a minute: persist the time
            _saved_min = time.localtime()[4]
            save_time()
        if time_set:
            r, g, b = hsv((time.localtime()[5] % COLOURS) / float(COLOURS), 1.0)
            led(r, g, b)                      # bright colour
            _led_until = now + FLASH_S
            _led_on = True

    if HAVE_LED and _led_on and now >= _led_until:
        led(0, 0, 0)                          # OFF between pulses
        _led_on = False

    if HAVE_LED and not _led_on and last_rx and (now - last_rx > STALE_S):
        led(140, 0, 0)                        # red = time feed lost

    time.sleep_ms(40)
