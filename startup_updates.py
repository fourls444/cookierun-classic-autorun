"""Handle recognized game-data and Play Store update screens with bounded waits."""
import re
import subprocess
import time

from adb import device_capture_screen, device_tap, run_adb
from config import DEVICE_IP, DEVICE_PORT
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


class StartupUpdates:
    def __init__(self):
        self.last_check = -float('inf')
        self.warned = False

    def handle_if_needed(self, screen=None, force=False):
        if not force and time.monotonic() - self.last_check < 15:
            return False
        self.last_check = time.monotonic()
        screen = screen if screen is not None else device_capture_screen(DEVICE_IP, DEVICE_PORT)
        try:
            lines = read_text(screen)
            action = update_action(lines, foreground_package())
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
            from detection import detect_stage
            if package == GAME_PACKAGE and detect_stage(screen, ['MAINMENU', 'PURCHASE_ITEM']):
                print('✅ Update finished; game menu is ready.')
                return True
            lines = read_text(screen)
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
