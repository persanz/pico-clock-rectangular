#!/usr/bin/env python3
"""Send the current date/time to the Pico over USB serial.

The board has no WiFi/RTC, so this host-side helper pushes the time and the Pico
stores it in its RTC. Standard library only; reconnects automatically.

    S|DT:YYYY-MM-DD:HH:MM:SS:WD|TS:HH:MM:SS

Usage:
    python3 time_pusher.py
    python3 time_pusher.py --port /dev/ttyACM0 --interval 5
"""
import argparse
import glob
import os
import select
import termios
import time
import tty

DEFAULT_PORT = os.environ.get("PICO_PORT", "/dev/cu.usbmodem101")


def resolve_port(dev):
    if os.path.exists(dev):
        return dev
    cands = (sorted(glob.glob("/dev/cu.usbmodem*")) + sorted(glob.glob("/dev/ttyACM*"))
             + sorted(glob.glob("/dev/ttyUSB*")))
    return cands[0] if cands else dev


def open_port(dev):
    dev = resolve_port(dev)
    if not os.path.exists(dev):
        raise FileNotFoundError(dev)
    fd = os.open(dev, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    tty.setraw(fd)
    a = termios.tcgetattr(fd)
    a[4] = a[5] = termios.B115200
    termios.tcsetattr(fd, termios.TCSANOW, a)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def build_line():
    lt = time.localtime()
    return "S|DT:%04d-%02d-%02d:%02d:%02d:%02d:%d|TS:%s" % (
        lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, lt.tm_min, lt.tm_sec, lt.tm_wday,
        time.strftime("%H:%M:%S"))


def main():
    ap = argparse.ArgumentParser(description="Push the time to the Pico clock over USB serial.")
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--once", action="store_true", help="send one update and exit")
    args = ap.parse_args()

    if args.once:
        fd = open_port(args.port)
        line = build_line()
        os.write(fd, (line + "\n").encode())
        time.sleep(0.5)
        try:
            print(os.read(fd, 64).decode("utf-8", "replace").strip() or "(no reply)")
        except BlockingIOError:
            pass
        os.close(fd)
        return

    print("sending the time every %ss (reconnects automatically) — Ctrl-C to stop" % args.interval)
    while True:
        fd = None
        try:
            fd = open_port(args.port)
            print("%s connected to %s" % (time.strftime("%H:%M:%S"), resolve_port(args.port)))
            os.write(fd, (build_line() + "\n").encode())
            last = time.time()
            while True:
                select.select([fd], [], [], 0.25)
                if time.time() - last >= args.interval:
                    os.write(fd, (build_line() + "\n").encode())
                    last = time.time()
        except KeyboardInterrupt:
            print("\nstopped")
            if fd is not None:
                try:
                    os.close(fd)
                except Exception:
                    pass
            return
        except OSError as e:
            print("%s link lost (%s) — retrying in 3s" % (time.strftime("%H:%M:%S"), e))
            if fd is not None:
                try:
                    os.close(fd)
                except Exception:
                    pass
            time.sleep(3)


if __name__ == "__main__":
    main()
