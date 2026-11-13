#!/usr/bin/python3
import json
import os
import signal
import subprocess
from time import monotonic
from pathlib import Path

import pyudev
from gi.repository import Gio, GLib


DISPLAY = "eDP-1"
TOUCH = "ELAN22BF:00 04F3:22BF"
DOCK_KEYBOARD = Path("/dev/input/by-id/usb-0b05_ASUS_Touchpad_and_G-sensor_Keyboard-event-kbd")
DOCK_SETTLE_US = 450_000
ROTATIONS = {
    "normal": ("normal", (1, 0, 0, 0, 1, 0)),
    "left-up": ("left", (0, -1, 1, 1, 0, 0)),
    "right-up": ("right", (0, 1, 0, -1, 0, 1)),
    "bottom-up": ("inverted", (-1, 0, 1, 0, -1, 1)),
}

PANEL = "/panels/panel-1"
TABLET_PANEL = {
    "autohide-behavior": 0,
    "enable-struts": False,
    "output-name": "T305CA-tablet-panel-hidden",
}
OPTIONAL_PANEL_PROPERTIES = {
    "autohide-behavior": ("uint", 0),
    "disable-struts": ("bool", False),
    "enable-struts": ("bool", True),
    "output-name": ("string", "Automatic"),
}
PANEL_STATE = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "t305ca" / "panneau-avant-tablette.json"
)


def panel_command(name):
    return ["xfconf-query", "-c", "xfce4-panel", "-p", f"{PANEL}/{name}"]


def read_panel(name):
    result = subprocess.run(panel_command(name), capture_output=True, text=True)
    if result.returncode != 0 and name in OPTIONAL_PANEL_PROPERTIES:
        return None
    result.check_returncode()
    value = result.stdout.rstrip("\n")
    value_type, _ = OPTIONAL_PANEL_PROPERTIES.get(name, ("uint", None))
    if value_type == "bool":
        return value == "true"
    if value_type == "string":
        return value
    return int(value)


def write_panel(name, value):
    command = panel_command(name)
    if value is None:
        if read_panel(name) is not None:
            # Xfce can keep the previous value in memory when a key is reset.
            write_panel(name, OPTIONAL_PANEL_PROPERTIES[name][1])
            subprocess.run([*command, "-r"], check=True)
        return
    if name in OPTIONAL_PANEL_PROPERTIES and read_panel(name) is None:
        command += ["-n", "-t", OPTIONAL_PANEL_PROPERTIES[name][0]]
    setting = str(value).lower() if isinstance(value, bool) else str(value)
    subprocess.run([*command, "-s", setting], check=True)


def apply_panel(tablet):
    if not tablet and not PANEL_STATE.exists():
        return
    saved = json.loads(PANEL_STATE.read_text()) if PANEL_STATE.exists() else {}
    if not tablet:
        for name, value in saved.items():
            write_panel(name, value)
        PANEL_STATE.unlink(missing_ok=True)
        return

    for name in TABLET_PANEL:
        if name not in saved:
            saved[name] = read_panel(name)
    PANEL_STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = PANEL_STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(saved) + "\n")
    temporary.replace(PANEL_STATE)
    for name, value in TABLET_PANEL.items():
        write_panel(name, value)


def apply_orientation(orientation):
    started = monotonic()
    monitors = subprocess.check_output(["xrandr", "--listactivemonitors"], text=True)
    outputs = [line.split()[-1] for line in monitors.splitlines()[1:]]
    if DISPLAY not in outputs:
        return
    # Laisser les écrans externes dans leur disposition actuelle.
    if len(outputs) > 1:
        return
    rotation, coefficients = ROTATIONS[orientation]
    matrix = [f"{value}.0" for value in (*coefficients, 0, 0, 1)]
    subprocess.run(["xrandr", "--current", "--output", DISPLAY, "--rotate", rotation], check=True)
    subprocess.run(["xinput", "set-prop", TOUCH, "Coordinate Transformation Matrix", *matrix], check=True)
    subprocess.run(
        ["xinput", "set-prop", f"{TOUCH} Stylus", "libinput Calibration Matrix", *matrix],
        check=False,
    )
    state = Path(GLib.get_user_runtime_dir()) / "t305ca-display-rotation"
    temporary = state.with_suffix(".tmp")
    temporary.write_text(rotation + "\n")
    temporary.replace(state)
    print(f"Rotation de l’écran et du tactile → {rotation} ({(monotonic() - started) * 1000:.0f} ms)", flush=True)


def main():
    if Path("/sys/class/dmi/id/product_name").read_text().strip() != "T305CA":
        return

    context = pyudev.Context()
    sensor = Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
        "net.hadess.SensorProxy", "/net/hadess/SensorProxy", "net.hadess.SensorProxy", None,
    )
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    onboard_auto_show = Gio.Settings.new("org.onboard.auto-show")
    keyboard = None
    home = None
    tablet = False
    panel_tablet = None
    keyboard_ready = None
    keyboard_changed_at = 0
    dock_settle_timer = 0
    claimed_by = None
    orientation = "normal"
    state = Path(GLib.get_user_runtime_dir()) / "t305ca-display-rotation"
    rotation_lock = state.with_name("t305ca-rotation-locked")
    drawing_mode = state.with_name("t305ca-mode-dessin")
    reading_mode = state.with_name("t305ca-mode-lecture")
    backlight = Path("/sys/class/backlight/intel_backlight")
    reading_previous = None
    restore_orientation = None
    touch_disabled = False
    state.unlink(missing_ok=True)

    def update_drawing_mode(detached):
        nonlocal touch_disabled
        if not detached:
            drawing_mode.unlink(missing_ok=True)
        wanted = drawing_mode.exists()
        if wanted != touch_disabled:
            subprocess.run(["xinput", "disable" if wanted else "enable", TOUCH], check=True)
            touch_disabled = wanted

    def set_reading_brightness(value):
        bus_system = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        bus_system.call_sync(
            "org.freedesktop.login1", "/org/freedesktop/login1/session/auto",
            "org.freedesktop.login1.Session", "SetBrightness",
            GLib.Variant("(ssu)", ("backlight", backlight.name, value)),
            None, Gio.DBusCallFlags.NONE, 3000, None,
        )

    def update_reading_mode(detached):
        nonlocal reading_previous, restore_orientation
        if not detached or drawing_mode.exists():
            reading_mode.unlink(missing_ok=True)
        if reading_mode.exists() and reading_previous is None:
            current = int((backlight / "brightness").read_text())
            maximum = int((backlight / "max_brightness").read_text())
            set_reading_brightness(min(current, round(maximum * 0.25)))
            reading_previous = (orientation, current)
        elif not reading_mode.exists() and reading_previous is not None:
            previous_orientation, previous_brightness = reading_previous
            set_reading_brightness(previous_brightness)
            restore_orientation = previous_orientation if detached else "normal"
            reading_previous = None

    def refresh_orientation():
        nonlocal orientation, restore_orientation
        reading = sensor.get_cached_property("AccelerometerOrientation")
        if tablet and reading_previous is not None:
            wanted = "right-up" if reading and reading.unpack() == "right-up" else "left-up"
            if orientation in ("left-up", "right-up"):
                wanted = orientation
        elif restore_orientation is not None:
            wanted = restore_orientation
        elif tablet and (rotation_lock.exists() or drawing_mode.exists()):
            return
        else:
            wanted = reading.unpack() if tablet and reading is not None else "normal"
        if wanted in ROTATIONS and wanted != orientation:
            try:
                apply_orientation(wanted)
            except (OSError, subprocess.SubprocessError) as error:
                print(error, flush=True)
            else:
                orientation = wanted
        if wanted == orientation:
            restore_orientation = None

    def orientation_changed(_, changed, invalidated):
        if tablet and "AccelerometerOrientation" in changed.unpack():
            refresh_orientation()

    def update():
        nonlocal keyboard, home, tablet, panel_tablet, claimed_by
        nonlocal keyboard_ready, keyboard_changed_at
        try:
            ready = DOCK_KEYBOARD.exists()
            now = GLib.get_monotonic_time()
            if ready != keyboard_ready:
                keyboard_ready = ready
                keyboard_changed_at = now
            if now - keyboard_changed_at < DOCK_SETTLE_US:
                return GLib.SOURCE_CONTINUE
            detached = not ready
            update_reading_mode(detached)
            update_drawing_mode(detached)
            if detached != panel_tablet:
                onboard_auto_show.set_boolean("enabled", detached)
                Gio.Settings.sync()
                if not detached:
                    rotation_lock.unlink(missing_ok=True)
                apply_panel(detached)
                panel_tablet = detached

            if detached != tablet:
                if detached:
                    keyboard = subprocess.Popen(["onboard"])
                    home = subprocess.Popen([
                        "/usr/bin/python3", str(Path(__file__).with_name("t305ca-accueil-tablette.py")),
                    ])
                else:
                    tablet = False
                    refresh_orientation()
                    for process in (home, keyboard):
                        if process is not None and process.poll() is None:
                            process.terminate()
                    home = None
                    keyboard = None
                    bus.call(
                        "org.onboard.Onboard", "/org/onboard/Onboard/Keyboard",
                        "org.onboard.Onboard.Keyboard", "Hide", None, None,
                        Gio.DBusCallFlags.NO_AUTO_START, 1000, None, None,
                    )
                tablet = detached
                print("Mode tablette" if tablet else "Mode clavier", flush=True)

            owner = sensor.get_name_owner()
            if tablet and owner and claimed_by != owner:
                sensor.call_sync("ClaimAccelerometer", None, Gio.DBusCallFlags.NONE, 2000, None)
                claimed_by = owner
            elif not tablet and claimed_by:
                if owner == claimed_by:
                    sensor.call_sync("ReleaseAccelerometer", None, Gio.DBusCallFlags.NONE, 2000, None)
                claimed_by = None

            refresh_orientation()
        except (OSError, subprocess.SubprocessError, GLib.Error) as error:
            print(error, flush=True)
        return GLib.SOURCE_CONTINUE

    def dock_changed(*_):
        nonlocal dock_settle_timer
        while monitor.poll(timeout=0) is not None:
            pass
        update()
        if dock_settle_timer:
            GLib.source_remove(dock_settle_timer)
        dock_settle_timer = GLib.timeout_add(DOCK_SETTLE_US // 1000, settle_dock)
        return GLib.SOURCE_CONTINUE

    def settle_dock():
        nonlocal dock_settle_timer
        dock_settle_timer = 0
        update()
        return GLib.SOURCE_REMOVE

    sensor.connect("g-properties-changed", orientation_changed)
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem="usb", device_type="usb_device")
    monitor.filter_by(subsystem="input")
    monitor.start()
    GLib.io_add_watch(monitor.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, dock_changed)
    dock_changed()
    GLib.timeout_add_seconds(2, update)
    loop = GLib.MainLoop()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, loop.quit)
    try:
        loop.run()
    finally:
        try:
            update_reading_mode(False)
        finally:
            update_drawing_mode(False)


if __name__ == "__main__":
    main()
