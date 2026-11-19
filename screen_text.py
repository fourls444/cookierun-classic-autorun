"""Read local screenshots with Windows OCR. No screenshots leave the PC."""
import json
import subprocess
import tempfile
from pathlib import Path

import cv2


def read_text(screen):
    if screen is None:
        raise ValueError('No screenshot available for OCR.')
    success, encoded = cv2.imencode('.png', screen)
    if not success:
        raise ValueError('Could not encode screenshot for OCR.')
    with tempfile.TemporaryDirectory(prefix='cookierun-ocr-') as folder:
        image_path = Path(folder) / 'screen.png'
        image_path.write_bytes(encoded.tobytes())
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy',
             'Bypass', '-File', str(Path(__file__).with_name('read_screen_text.ps1')),
             '-ImagePath', str(image_path)],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=25, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            raise RuntimeError('Windows OCR failed: ' + result.stderr.strip()[-500:])
        return json.loads(result.stdout.strip().lstrip('\ufeff'))['lines']


def save_evidence(screen, label):
    from datetime import datetime
    directory = Path(__file__).parent / 'stats' / 'screenshots'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + label + '.png')
    success, encoded = cv2.imencode('.png', screen)
    if not success:
        raise ValueError('Could not encode evidence screenshot.')
    path.write_bytes(encoded.tobytes())
    return str(path)
