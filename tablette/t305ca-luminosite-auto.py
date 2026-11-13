#!/usr/bin/python3
from pathlib import Path
from statistics import median
from time import sleep

from gi.repository import Gio, GLib


BACKLIGHT = Path("/sys/class/backlight/intel_backlight")
SENSOR_DRIVER = Path("/sys/module/t305ca_als")
LID_STATE = Path("/proc/acpi/button/lid/LID/state")
READING_MODE = Path(GLib.get_user_runtime_dir()) / "t305ca-mode-lecture"
# Lux ambiants et pourcentage de rétroéclairage, avec un plancher lisible.
CURVE = ((0, 10), (15, 20), (50, 27), (200, 42), (600, 63), (1500, 82), (3500, 100))
STEP_PERCENT = 3


def brightness_percent(lux):
    for (low_lux, low_pct), (high_lux, high_pct) in zip(CURVE, CURVE[1:]):
        if lux <= high_lux:
            fraction = (lux - low_lux) / (high_lux - low_lux)
            return round(low_pct + fraction * (high_pct - low_pct))
    return CURVE[-1][1]


def find_sensor():
    for name in Path("/sys/bus/iio/devices").glob("iio:device*/name"):
        if name.read_text().strip() == "acpi-als":
            return name.with_name("in_illuminance_input")
    return None


def brightness_step(current, target, maximum):
    step = max(1, round(maximum * STEP_PERCENT / 100))
    return current + max(-step, min(step, target - current))


def run():
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    session = Gio.DBusProxy.new_sync(
        bus, Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES, None,
        "org.freedesktop.login1", "/org/freedesktop/login1/session/auto",
        "org.freedesktop.login1.Session", None,
    )
    sensor = None
    readings = []
    last_percent = None
    target = None
    last_written = None
    while True:
        sleep(1)
        try:
            if READING_MODE.exists():
                continue
            if not SENSOR_DRIVER.is_dir() or LID_STATE.read_text().split()[-1] == "closed":
                readings.clear()
                target = last_written = last_percent = None
                continue
            if sensor is None:
                sensor = find_sensor()
                if sensor is None:
                    continue
            readings.append(max(0, int(sensor.read_text())))
            readings = readings[-3:]
            if len(readings) < 3:
                continue

            lux = median(readings)
            percent = brightness_percent(lux)
            maximum = int((BACKLIGHT / "max_brightness").read_text())
            current = int((BACKLIGHT / "brightness").read_text())
            if last_written is not None and current != last_written:
                # Un réglage manuel interrompt la transition en cours.
                target = None
                last_written = None
                last_percent = percent
            if last_percent is None or abs(percent - last_percent) >= 5:
                last_percent = percent
                target = round(maximum * percent / 100)
                print(f"{lux} lux → cible {percent} % ({target}/{maximum})", flush=True)
            if target is None or target == current:
                continue
            next_value = brightness_step(current, target, maximum)
            session.call_sync(
                "SetBrightness", GLib.Variant("(ssu)", ("backlight", BACKLIGHT.name, next_value)),
                Gio.DBusCallFlags.NONE, 3000, None,
            )
            last_written = next_value
        except (OSError, ValueError, GLib.Error) as error:
            print(error, flush=True)
            sensor = None
            readings.clear()
            target = last_written = last_percent = None
            sleep(5)


if __name__ == "__main__":
    run()
