"""Find LDPlayer instances that ADB can reach, including LDMultiplayer clones."""
import re
import subprocess

from config import DEVICE_IP, DEVICE_PORT


INSTANCE_PORT_STEP = 2  # LDPlayer gives each instance a port 2 above the previous one
PROBED_INSTANCES = 8
ADB_TIMEOUT = 5


def instance_port(index):
    return DEVICE_PORT + index * INSTANCE_PORT_STEP


def instance_index(port):
    offset = port - DEVICE_PORT
    if offset >= 0 and offset % INSTANCE_PORT_STEP == 0:
        return offset // INSTANCE_PORT_STEP
    return None


def instance_label(port):
    index = instance_index(port)
    if index is None:
        return f'{DEVICE_IP}:{port}'
    return f'LDPlayer {index} · {port}'


def _run(arguments):
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    return subprocess.run(arguments, capture_output=True, text=True,
                          timeout=ADB_TIMEOUT, creationflags=flags)


def connected_ports(ports):
    try:
        result = _run(['adb', 'devices'])
    except (OSError, subprocess.SubprocessError):
        return
    for line in result.stdout.splitlines():
        match = re.match(r'^(?:127\.0\.0\.1|localhost):(\d+)\s+device\b', line.strip())
        if match:
            ports.add(int(match.group(1)))


def available_ports():
    """Return the ports of ADB-visible LDPlayer instances, plus the configured default."""
    ports = {DEVICE_PORT}
    connected_ports(ports)
    for index in range(PROBED_INSTANCES):
        port = instance_port(index)
        if port in ports:
            continue
        try:
            result = _run(['adb', 'connect', f'{DEVICE_IP}:{port}'])
        except (OSError, subprocess.SubprocessError):
            continue
        if 'connected' in result.stdout and 'cannot' not in result.stdout:
            ports.add(port)
    return sorted(ports)
