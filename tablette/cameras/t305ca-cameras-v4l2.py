#!/usr/bin/python3
import errno
import fcntl
import os
from pathlib import Path
import signal
import struct
import sys

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst


# V4L2 ABI for amd64 and the client-usage event in v4l2loopback 0.15.3.
SUBSCRIBE_EVENT = 0x4020565A
DEQUEUE_EVENT = 0x80885659
CLIENT_USAGE = 0x10E00001
OUTPUT_CAPS = "video/x-raw,format=YUY2,width=1280,height=720,pixel-aspect-ratio=1/1,framerate=30/1"
SINK_CAPS = OUTPUT_CAPS + ",interlace-mode=progressive,colorimetry=bt601"
BLACK_FRAME = bytes((16, 128, 16, 128)) * (1280 * 720 // 2)
ROTATION_PATH = Path(GLib.get_user_runtime_dir()) / "t305ca-display-rotation"
FRONT_ROTATIONS = {"normal": 0, "left": 3, "inverted": 2, "right": 1}
REAR_ROTATIONS = {"normal": 0, "left": 1, "inverted": 2, "right": 3}
IIO_DEVICES = Path("/sys/bus/iio/devices")


def ambient_gamma(lux):
    return 1.0 + 0.45 * (1.0 - min(max(lux, 0.0), 180.0) / 180.0)


class Camera:
    def __init__(self, number, sensor, rotations, *, adjust_ambient_light=False):
        self.device = f"/dev/video{number}"
        self.sensor = sensor
        self.rotations = rotations
        self.adjust_ambient_light = adjust_ambient_light
        self.light_sensor = None
        self.capture = None
        self.requested = False
        self.failed = False
        self.retry_at = 0
        self.fd = os.open(self.device, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        subscription = struct.pack("=8I", CLIENT_USAGE, 0, 1, 0, 0, 0, 0, 0)
        fcntl.ioctl(self.fd, SUBSCRIBE_EVENT, subscription)
        self.output = Gst.parse_launch(
            f'appsrc name=frames is-live=true format=time do-timestamp=true '
            f'max-bytes=0 max-buffers=2 leaky-type=downstream caps="{SINK_CAPS}" '
            f'! v4l2sink device={self.device} sync=false io-mode=mmap'
        )
        self.frames = self.output.get_by_name("frames")
        self.output.get_bus().add_signal_watch()
        self.output.get_bus().connect("message::error", self.output_failed)
        self.output.set_state(Gst.State.PLAYING)
        self.send_black()
        self.event_watch = GLib.io_add_watch(
            self.fd, GLib.PRIORITY_DEFAULT, GLib.IOCondition.PRI, self.client_changed
        )
        self.frame_timer = 0

    def send_black(self):
        self.frames.emit("push-buffer", Gst.Buffer.new_wrapped(BLACK_FRAME))

    def output_failed(self, _, message):
        error, details = message.parse_error()
        print(f"{self.device}: {error.message} {details}", flush=True)
        self.failed = True
        loop.quit()

    def client_changed(self, *_):
        event = bytearray(136)
        requested = self.requested
        while True:
            try:
                fcntl.ioctl(self.fd, DEQUEUE_EVENT, event, True)
            except OSError as error:
                if error.errno not in (errno.EAGAIN, errno.ENOENT):
                    print(f"{self.device}: {error}", flush=True)
                    self.failed = True
                    loop.quit()
                    return GLib.SOURCE_CONTINUE
                break
            if struct.unpack_from("=I", event)[0] == CLIENT_USAGE:
                requested = bool(struct.unpack_from("=I", event, 8)[0])
        if requested != self.requested:
            self.requested = requested
            if requested:
                self.retry_at = 0
                self.frame_timer = GLib.timeout_add(25, self.forward_frame)
            else:
                GLib.source_remove(self.frame_timer)
                self.frame_timer = 0
                self.stop_capture()
        return GLib.SOURCE_CONTINUE

    def start_capture(self, direction):
        correction = "! gamma name=ambient " if self.adjust_ambient_light else ""
        self.capture = Gst.parse_launch(
            f'libcamerasrc name=sensor ! video/x-raw,width=1280,height=720 '
            f'! queue leaky=downstream max-size-buffers=2 {correction}! videoflip name=rotation '
            f'! videoscale add-borders=true ! videoconvert ! videorate '
            f'! {SINK_CAPS} ! appsink name=images sync=false max-buffers=1 drop=true'
        )
        self.capture.get_by_name("sensor").set_property("camera-name", self.sensor)
        self.flip = self.capture.get_by_name("rotation")
        self.ambient = self.capture.get_by_name("ambient")
        self.next_light_update = 0
        self.gamma = None
        self.set_direction(direction)
        self.images = self.capture.get_by_name("images")
        self.capture.set_state(Gst.State.PLAYING)
        print(f"{self.device}: capture {self.sensor}", flush=True)

    def set_direction(self, direction):
        self.flip.set_property("video-direction", direction)
        self.direction = direction
        print(f"{self.device}: orientation {self.flip.get_property('video-direction').value_nick}", flush=True)

    def stop_capture(self):
        if self.capture is not None:
            self.capture.set_state(Gst.State.NULL)
            self.capture = None
            self.images = self.flip = self.ambient = None
            self.send_black()
            print(f"{self.device}: capteur fermé", flush=True)

    def update_ambient_light(self, now):
        if self.ambient is None or now < self.next_light_update:
            return
        self.next_light_update = now + GLib.USEC_PER_SEC
        try:
            if self.light_sensor is None:
                self.light_sensor = next(
                    (name.with_name("in_illuminance_input")
                     for name in IIO_DEVICES.glob("iio:device*/name")
                     if name.read_text().strip() == "acpi-als"),
                    None,
                )
            lux = float(self.light_sensor.read_text()) if self.light_sensor else None
        except (OSError, ValueError):
            self.light_sensor = None
            lux = None
        target = ambient_gamma(lux) if lux is not None else 1.0
        current = target if self.gamma is None else self.gamma + 0.35 * (target - self.gamma)
        if self.gamma is None or abs(current - self.gamma) >= 0.005:
            self.ambient.set_property("gamma", current)
            self.gamma = current
            print(f"{self.device}: lumière ambiante {lux} lux, gamma {current:.2f}", flush=True)

    def forward_frame(self):
        if not self.requested:
            return GLib.SOURCE_CONTINUE
        now = GLib.get_monotonic_time()
        if now < self.retry_at:
            return GLib.SOURCE_CONTINUE
        try:
            orientation = ROTATION_PATH.read_text().strip()
        except FileNotFoundError:
            orientation = "normal"
        direction = self.rotations.get(orientation, self.rotations["normal"])
        if self.capture is None:
            self.start_capture(direction)
        message = self.capture.get_bus().pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.EOS)
        if message:
            if message.type == Gst.MessageType.ERROR:
                error, _ = message.parse_error()
                print(f"{self.device}: {error.message}", flush=True)
            self.stop_capture()
            self.retry_at = now + 3 * GLib.USEC_PER_SEC
            return GLib.SOURCE_CONTINUE
        if direction != self.direction:
            self.set_direction(direction)
        self.update_ambient_light(now)
        sample = self.images.emit("try-pull-sample", 0)
        if sample is not None:
            frame = sample.get_buffer().copy()
            frame.pts = frame.dts = Gst.CLOCK_TIME_NONE
            frame.offset = frame.offset_end = Gst.BUFFER_OFFSET_NONE
            self.frames.emit("push-buffer", frame)
        return GLib.SOURCE_CONTINUE

    def close(self):
        GLib.source_remove(self.event_watch)
        if self.frame_timer:
            GLib.source_remove(self.frame_timer)
        self.stop_capture()
        self.output.set_state(Gst.State.NULL)
        os.close(self.fd)


if __name__ == "__main__":
    Gst.init(None)
    loop = GLib.MainLoop()
    cameras = []
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: loop.quit() or False)
    try:
        cameras.append(Camera(60, r"\_SB_.PCI0.CAM3", FRONT_ROTATIONS, adjust_ambient_light=True))
        cameras.append(Camera(61, r"\_SB_.PCI0.CAM6", REAR_ROTATIONS))
        loop.run()
    finally:
        for camera in reversed(cameras):
            camera.close()
    sys.exit(any(camera.failed for camera in cameras))
