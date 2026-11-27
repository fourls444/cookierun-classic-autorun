"""Read local screenshots with Windows OCR. No screenshots leave the PC."""
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import cv2


ROOT = Path(__file__).resolve().parent
EVIDENCE_DIR = ROOT / 'stats' / 'screenshots'
ERROR_DIR = EVIDENCE_DIR / 'errors'
_save_successful = False


def keep_successful_screenshots(enabled):
    """Choose whether screenshots of successful reads are kept. Failures are always saved."""
    global _save_successful
    _save_successful = bool(enabled)


def read_text(screen, *, timeout=25):
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
            timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            raise RuntimeError('Windows OCR failed: ' + result.stderr.strip()[-500:])
        return json.loads(result.stdout.strip().lstrip('\ufeff'))['lines']


def save_evidence(screen, label, *, error=False):
    """Save a screenshot under stats/screenshots and return its path relative to the app.

    Successful reads are skipped unless keep_successful_screenshots(True), which keeps
    stats/screenshots small. Failures and unreadable results are always saved.
    """
    if not error and not _save_successful:
        return None
    directory = ERROR_DIR if error else EVIDENCE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + label + '.png')
    success, encoded = cv2.imencode('.png', screen)
    if not success:
        raise ValueError('Could not encode evidence screenshot.')
    path.write_bytes(encoded.tobytes())
    return str(path.relative_to(ROOT))
