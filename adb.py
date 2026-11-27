import random
import struct
import subprocess
import threading
import time
from contextvars import ContextVar

import cv2
import numpy as np

from config import DEVICE_IP, DEVICE_PORT


stop_signal = ContextVar('adb_stop_signal', default=None)

# Each worker thread can talk to a different LDPlayer instance.
_device = threading.local()


def set_device(ip, port):
    """Point this thread's ADB commands at one device or LDPlayer instance."""
    ip, port = str(ip), int(port)
    _device.ip = ip
    _device.port = port
    return ip, port


def get_device():
    return getattr(_device, 'ip', DEVICE_IP), getattr(_device, 'port', DEVICE_PORT)


def _address(ip=None, port=None):
    current_ip, current_port = get_device()
    return (current_ip if ip is None else ip,
            current_port if port is None else port)


def device_address(ip=None, port=None):
    ip, port = _address(ip, port)
    return f'{ip}:{port}'


def run_adb(command, **kwargs):
    stop = stop_signal.get()
    if stop is not None:
        if stop.is_set():
            raise KeyboardInterrupt
        kwargs.setdefault('timeout', 15)
        kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
    return subprocess.run(command, **kwargs)


def device_connect(ip: str = None, port: int = None):
    ip, port = _address(ip, port)
    result = run_adb(
        ["adb", "connect", f"{ip}:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    print(f"🔌 {result.stdout.strip().capitalize()}")
    if "connected" not in result.stdout and "already connected" not in result.stdout:
        raise Exception(f"❌ Failed to connect to {ip}:{port}\n{result.stderr.strip()}")


def _decode_raw_capture(data):
    """Turn `screencap` raw output into a BGR frame, or None if unreadable."""
    if len(data) < 16:
        return None
    width, height, pixel_format = struct.unpack('<III', data[:12])
    if pixel_format != 1 or not 0 < width <= 4096 or not 0 < height <= 4096:
        return None
    size = width * height * 4
    if len(data) < size:
        return None
    pixels = np.frombuffer(data[-size:], dtype=np.uint8).reshape(height, width, 4)
    return cv2.cvtColor(pixels, cv2.COLOR_RGBA2BGR)


def device_capture_screen(ip: str = None, port: int = None):
    ip, port = _address(ip, port)
    # Raw screencap skips PNG encoding on the device, which is roughly twice as
    # fast as `screencap -p` on LDPlayer.
    result = run_adb(
        ["adb", "-s", f"{ip}:{port}", "exec-out", "screencap"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True
    )
    frame = _decode_raw_capture(result.stdout)
    if frame is not None:
        return frame
    # Fall back to PNG for devices that do not emit a raw header.
    result = run_adb(
        ["adb", "-s", f"{ip}:{port}", "exec-out", "screencap", "-p"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True
    )
    img = np.frombuffer(result.stdout, dtype=np.uint8)
    return cv2.imdecode(img, cv2.IMREAD_COLOR)


def device_tap(x: int, y: int, ip: str = None, port: int = None):
    ip, port = _address(ip, port)
    run_adb(
        ["adb", "-s", f"{ip}:{port}", "shell", "input", "tap", str(x), str(y)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )


def safe_device_tap(x: int, y: int, ip: str = None, port: int = None):
    ip, port = _address(ip, port)
    jitter_x = x + random.randint(-15, 15)
    jitter_y = y + random.randint(-15, 15)
    run_adb(
        ["adb", "-s", f"{ip}:{port}", "shell", "input", "tap", str(jitter_x), str(jitter_y)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )


def safe_device_scroll(x: int, y: int, direction: str = "up", distance: int = 500, duration: int = 300,
                       ip: str = None, port: int = None):
    ip, port = _address(ip, port)
    jx = x + random.randint(-15, 15)
    jy = y + random.randint(-15, 15)
    direction_map = {
        "up":    (jx, jy + distance, jx, jy - distance),
        "down":  (jx, jy - distance, jx, jy + distance),
        "left":  (jx + distance, jy, jx - distance, jy),
        "right": (jx - distance, jy, jx + distance, jy),
    }
    if direction not in direction_map:
        raise ValueError(f"Invalid direction '{direction}'. Use: up, down, left, right.")
    x1, y1, x2, y2 = direction_map[direction]
    run_adb(
        ["adb", "-s", f"{ip}:{port}", "shell", "input", "swipe",
         str(x1), str(y1), str(x2), str(y2), str(duration)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )


def device_is_app_running(package: str, ip: str = None, port: int = None) -> bool:
    ip, port = _address(ip, port)
    result = run_adb(
        ["adb", "-s", f"{ip}:{port}", "shell", "pidof", package],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return bool(result.stdout.strip())


def device_reset_app(*, startup_handler=None, package: str = "com.devsisters.crg", max_retries: int = 5,
                     ip: str = None, port: int = None):
    ip, port = _address(ip, port)
    print(f"🔄 Resetting app {package} on device at {ip}:{port}...")
    run_adb(
        ["adb", "-s", f"{ip}:{port}", "shell", "cmd", "activity", "force-stop", package],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    print(f"⏳ Waiting 15 seconds for app {package} to stop...")
    time.sleep(15)

    for attempt in range(1, max_retries + 1):
        print(f"📱 Restarting app {package} on device at {ip}:{port} (attempt {attempt}/{max_retries})...")
        run_adb(
            ["adb", "-s", f"{ip}:{port}", "shell", "am", "start", "-W", "-n",
             f"{package}/com.devsisters.CookieRunForKakao.OvenbreakX"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print(f"⏳ Waiting 15 seconds to check if app started...")
        time.sleep(15)
        if startup_handler is not None:
            startup_handler()

        if device_is_app_running(package):
            print(f"📊 App {package} is running, verifying stability...")
            stable = True
            for check in range(1, 4):
                time.sleep(20)
                if not device_is_app_running(package):
                    print(f"💥 App {package} crashed during stability check ({check}/3).")
                    stable = False
                    break
                print(f"✅ Stability check {check}/3 passed.")
            if stable:
                print(f"✅ App {package} is stable.")
                return

        print(f"💥 App {package} appears to have crashed after launch.")
        if attempt < max_retries:
            print(f"🔁 Retrying in 5 seconds...")
            time.sleep(5)

    raise Exception(f"❌ Failed to start {package} after {max_retries} attempts.")
