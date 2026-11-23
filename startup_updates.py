"""Handle recognized game-data and Play Store update screens with bounded waits."""
import re
import subprocess
import time
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from adb import device_capture_screen, device_tap, run_adb
from config import DEVICE_IP, DEVICE_PORT
import detection
from screen_text import read_text, save_evidence


GAME_PACKAGE = 'com.devsisters.crg'
GAME_ACTIVITY = GAME_PACKAGE + '/com.devsisters.CookieRunForKakao.OvenbreakX'


def adb_command(*arguments):
    result = run_adb(['adb', '-s', f'{DEVICE_IP}:{DEVICE_PORT}', 'shell',
                             *arguments], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=20)
    if result.returncode:
        raise RuntimeError('Update ADB command failed: ' + result.stderr.strip())
    return result.stdout


def foreground_package():
    output = adb_command('dumpsys', 'activity', 'activities')
    for line in output.splitlines():
        if 'mResumedActivity' in line or 'topResumedActivity' in line:
            match = re.search(r'\b([a-zA-Z0-9_.]+)/[a-zA-Z0-9_.$]+', line)
            if match:
                return match.group(1)
    return None


def normalize(text):
    return re.sub(r'[^a-z0-9%]+', ' ', text.lower()).strip()


def yellow_login_button(screen, lines):
    if not isinstance(screen, np.ndarray) or screen.shape != (720, 1280, 3):
        return False
    for line in lines:
        label = normalize(line['text'])
        words = line.get('words')
        if not words or not (
            re.search(r'\b(?:log\s?in|sign\s?in)\b', label)
            or label in ('kakao', 'kakaotalk', 'kakao account', 'continue with kakao')
            or 'เข้าสู่ระบบ' in line['text']
        ):
            continue
        left = round(min(word['x'] for word in words))
        right = round(max(word['x'] + word['width'] for word in words))
        top = round(min(word['y'] for word in words))
        bottom = round(max(word['y'] + word['height'] for word in words))
        if not (128 < (left + right) / 2 < 1152 and 180 < (top + bottom) / 2 < 690):
            continue
        margin = max(6, (bottom - top) // 2)
        area = screen[max(0, top - margin):min(720, bottom + margin),
                      max(0, left - margin):min(1280, right + margin)]
        if area.size:
            hue = cv2.cvtColor(area, cv2.COLOR_BGR2HSV)
            yellow = cv2.inRange(hue, (16, 95, 150), (40, 255, 255))
            if cv2.countNonZero(yellow) >= 0.45 * yellow.size:
                return True
    return False


def update_action(lines, package):
    """Return a recognized action only in the game or its Play Store listing."""
    text = ' '.join(normalize(line['text']) for line in lines)
    store = package == 'com.android.vending'
    if store:
        if 'cookierun classic' not in text and 'cookie run classic' not in text:
            return None
        labels = ('update', 'open')
        updating = any(term in text for term in ('pending', 'downloading', 'installing', '%'))
    elif package == GAME_PACKAGE:
        if not any(term in text for term in
                   ('please update', 'update required', 'new update', 'new version',
                    'latest version', 'download additional', 'additional data',
                    'download data', 'downloading', 'updating', 'download the latest')):
            return None
        labels = ('update', 'download', 'confirm', 'ok', 'yes', 'proceed', 'restart')
        updating = any(term in text for term in ('downloading', 'updating', '%'))
    else:
        return None
    for label in labels:
        for line in lines:
            if normalize(line['text']) != label or not line.get('words'):
                continue
            words = line['words']
            left = min(word['x'] for word in words)
            top = min(word['y'] for word in words)
            right = max(word['x'] + word['width'] for word in words)
            bottom = max(word['y'] + word['height'] for word in words)
            if not store and top < 300:
                continue
            return ('open' if store and label == 'open' else 'tap',
                    (round((left + right) / 2), round((top + bottom) / 2)))
    return ('wait', None) if updating else ('needs_help', None)


@lru_cache(maxsize=1)
def promo_close_templates():
    path = Path(__file__).with_name('templates') / 'PROMO_CLOSE.png'
    icon = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
    return tuple(cv2.resize(icon, (size, size), interpolation=cv2.INTER_LINEAR)
                 for size in (28, 32, 36))


def promo_close_position(screen):
    """Find the gray X only when it sits inside a bright, framed modal corner."""
    if not isinstance(screen, np.ndarray) or screen.shape != (720, 1280, 3):
        return None
    gray = cv2.resize(cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY), (695, 394),
                      interpolation=cv2.INTER_AREA)
    left, top = 350, 0
    search = gray[top:108, left:680]
    for icon in promo_close_templates():
        size = icon.shape[0]
        result = cv2.matchTemplate(search, icon, cv2.TM_CCOEFF_NORMED)
        _, score, _, (px, py) = cv2.minMaxLoc(result)
        if score < 0.88:
            continue
        x, y = left + px + size // 2, top + py + size // 2
        top_edge = gray[max(0, y - 35):y - 14, x - 90:x - 12] if y >= 15 else gray[:0]
        right_edge = gray[y + 13:y + 65, x + 16:x + 32]
        if (top_edge.size and right_edge.size
                and np.max(np.mean(top_edge >= 220, axis=1)) >= 0.85
                and np.max(np.mean(right_edge >= 220, axis=0)) >= 0.85):
            return round(x * 1280 / 695), round(y * 720 / 394)
    return None


def friend_info_close_position(screen):
    if not isinstance(screen, np.ndarray) or screen.shape != (720, 1280, 3):
        return None
    if not detection.detect_templates(screen, ('FRIEND_INFO_TITLE.png',), (500, 35, 780, 105)):
        return None
    matches = detection.detect_templates(screen, ('FRIEND_INFO_CLOSE.png',), (1035, 28, 1135, 113))
    if not matches:
        return None
    x, y, width, height = matches[0]
    return x + width // 2, y + height // 2


class StartupUpdates:
    def __init__(self):
        self.last_check = -float('inf')
        self.warned = False
        self.popup_closes = 0
        self.login_required = False

    def dismiss_popup(self, screen, package=None, *, friend_only=False):
        position = friend_info_close_position(screen)
        label = "Friend's Info"
        if position is None and not friend_only:
            position = promo_close_position(screen)
            label = 'event popup'
        if position is None or (package or foreground_package()) != GAME_PACKAGE:
            return False
        if self.popup_closes >= 6:
            path = save_evidence(screen, 'popup-not-cleared')
            raise RuntimeError(f'Could not close {label} after 6 attempts. Screenshot: {path}')
        self.popup_closes += 1
        print(f'🪟 Closing {label} ({self.popup_closes}/6).')
        device_tap(DEVICE_IP, DEVICE_PORT, *position)
        return True


    def note_login(self, screen, lines, package):
        if package != GAME_PACKAGE or not yellow_login_button(screen, lines):
            return False
        if not self.login_required:
            print('⚠️ กรุณา Login ใน LDPlayer แล้วรอให้เกมกลับเข้าเมนูหลัก')
        self.login_required = True
        return True

    def check_login_during_reconnect(self, screen):
        if not isinstance(screen, np.ndarray):
            return False
        try:
            package = foreground_package()
            return package == GAME_PACKAGE and self.note_login(screen, read_text(screen), package)
        except (RuntimeError, ValueError, subprocess.TimeoutExpired):
            return False

    def handle_if_needed(self, screen=None, force=False):
        if not force and time.monotonic() - self.last_check < 15:
            return False
        self.last_check = time.monotonic()
        screen = screen if screen is not None else device_capture_screen(DEVICE_IP, DEVICE_PORT)
        try:
            lines = read_text(screen)
            package = foreground_package()
            if self.note_login(screen, lines, package):
                return True
            action = update_action(lines, package)
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            if not self.warned:
                print(f'⚠️ Could not inspect update screen: {error}')
                self.warned = True
            return False
        if action is None:
            return False
        print('⬇️ Update screen detected. Waiting for the game update to finish...')
        deadline = time.monotonic() + 10 * 60
        tap_counts = {}
        ready_checks = 0
        while time.monotonic() < deadline:
            kind, position = action
            if kind == 'needs_help':
                path = save_evidence(screen, 'update-needs-help')
                raise RuntimeError(f'Update requires manual confirmation. Screenshot: {path}')
            if kind == 'open':
                adb_command('am', 'start', '-W', '-n', GAME_ACTIVITY)
            elif kind == 'tap':
                tap_counts[position] = tap_counts.get(position, 0) + 1
                if tap_counts[position] > 3:
                    path = save_evidence(screen, 'update-repeated-button')
                    raise RuntimeError(f'Update button did not advance after 3 attempts. Screenshot: {path}')
                device_tap(DEVICE_IP, DEVICE_PORT, *position)
            time.sleep(5)
            screen = device_capture_screen(DEVICE_IP, DEVICE_PORT)
            package = foreground_package()
            if package == GAME_PACKAGE and detection.detect_stage(screen, ['ANTI_BOT']) == 'ANTI_BOT':
                raise RuntimeError('Player verification required. Complete it in LDPlayer, then start again.')
            if package == GAME_PACKAGE and self.dismiss_popup(screen, package):
                ready_checks = 0
                action = ('wait', None)
                continue
            if package == GAME_PACKAGE and detection.detect_stage(screen, ['MAINMENU', 'PURCHASE_ITEM']):
                print('✅ Update finished; game menu is ready.')
                return True
            lines = read_text(screen)
            if self.note_login(screen, lines, package):
                return True
            action = update_action(lines, package)
            if action is None:
                ready_checks += 1
                if ready_checks >= 4:
                    path = save_evidence(screen, 'update-unrecognized')
                    raise RuntimeError(f'Update flow reached an unrecognized screen. Screenshot: {path}')
                action = ('wait', None)
            else:
                ready_checks = 0
        path = save_evidence(screen, 'update-timeout')
        raise RuntimeError(f'Update exceeded 10 minutes. Screenshot: {path}')
