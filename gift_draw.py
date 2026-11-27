"""Open earned Gift Draws from the main menu."""
import time

import cv2
import numpy as np

from adb import device_capture_screen, device_tap
from detection import detect_stage, detect_templates


GIFT_TAP_WAIT = 0.6
GIFT_POLL_INTERVAL = 0.35
GIFT_RESULT_TIMEOUT = 15

GIFT_DRAW_SHORTCUT = (396, 675)
GIFT_PICK_BOTTOM_RIGHT = (784, 550)
GIFT_REGIONS = {
    'HOME_PLAY': (790, 598, 1130, 710),
    'HOME_RIBBON': (340, 632, 450, 680),
    'HEADER': (450, 45, 1000, 145),
    'DRAW_BUTTON': (790, 555, 1050, 673),
    'CLOSE': (1040, 56, 1210, 168),
    'PICK_TITLE': (440, 138, 820, 220),
    'RESULT_TITLE': (360, 68, 928, 205),
    'CONFIRM': (320, 525, 620, 650),
    'DRAW_AGAIN': (630, 525, 934, 646),
}


def gift_control(screen, name, *, enabled=False):
    if not isinstance(screen, np.ndarray) or screen.shape != (720, 1280, 3):
        return None
    hits = detect_templates(screen, (f'GIFT_{name}.png',), GIFT_REGIONS[name])
    if not hits:
        return None
    x, y, width, height = hits[0]
    if enabled:
        colors = cv2.cvtColor(screen[y:y + height, x:x + width], cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(colors, (26, 80, 95), (109, 255, 255))
        if cv2.countNonZero(mask) < 0.28 * width * height:
            return None
    return x + width // 2, y + height // 2


def gift_main_menu(screen):
    return (gift_control(screen, 'HOME_PLAY', enabled=True) is not None
            and gift_control(screen, 'HOME_RIBBON') is not None)


def gift_pick_screen(screen):
    return bool(gift_control(screen, 'HEADER') and gift_control(screen, 'PICK_TITLE'))


def gift_overview(screen):
    close = gift_control(screen, 'CLOSE')
    if close and gift_control(screen, 'HEADER') and gift_control(screen, 'DRAW_BUTTON'):
        return gift_control(screen, 'DRAW_BUTTON', enabled=True), close
    return None


def gift_result(screen):
    if not gift_control(screen, 'RESULT_TITLE'):
        return None
    # The cover and buttons can be dimmed for a frame during the reward
    # animation, so fall back to the plain position instead of missing the screen.
    confirm = gift_control(screen, 'CONFIRM', enabled=True) or gift_control(screen, 'CONFIRM')
    if confirm:
        return confirm, gift_control(screen, 'DRAW_AGAIN', enabled=True)
    return None


def gift_draw_screen(screen):
    return bool(gift_pick_screen(screen) or gift_result(screen) or gift_overview(screen))


def wait_for_screen(wait, find, description, activity='Gift Draw', *,
                    timeout=10, interval=0.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        screen = device_capture_screen()
        if detect_stage(screen, ['ANTI_BOT']) == 'ANTI_BOT':
            raise RuntimeError('Player verification required. Complete it in LDPlayer, then start again.')
        if detect_stage(screen, ['CONNECTION_LOST']) == 'CONNECTION_LOST':
            raise RuntimeError(f'Connection lost. {activity} paused. Check LDPlayer before starting again.')
        found = find(screen)
        if found is not None:
            return found
        wait(interval)
    raise RuntimeError(f'{activity} could not find {description}. Check LDPlayer.')


def draw_gifts(limit, wait, main_screen, *, on_status=None):
    if type(limit) is not int or not 1 <= limit <= 9999:
        raise ValueError('Gift Draw limit must be from 1 to 9999.')

    def tap(position):
        device_tap(*position)
        wait(GIFT_TAP_WAIT)

    def open_one_gift():
        """Tap the selection once more only when the tap clearly did not register."""
        for attempt in range(2):
            tap(GIFT_PICK_BOTTOM_RIGHT)
            try:
                return wait_for_screen(wait, gift_result, 'the gift result',
                                       timeout=GIFT_RESULT_TIMEOUT,
                                       interval=GIFT_POLL_INTERVAL)
            except RuntimeError:
                if attempt or not gift_pick_screen(device_capture_screen()):
                    raise

    def exit_screen(screen):
        if gift_control(screen, 'HEADER'):
            close = gift_control(screen, 'CLOSE')
            if close:
                return (close,)
        if gift_main_menu(screen):
            return ()
        return None

    selection_visible = gift_pick_screen(main_screen)
    previous_result = gift_result(main_screen)
    if previous_result:
        confirm, draw_again = previous_result
        tap(draw_again or confirm)
        pick_ready = draw_again is not None
    else:
        pick_ready = selection_visible
        if not pick_ready:
            overview = gift_overview(main_screen)
            if overview is None:
                if not gift_main_menu(main_screen):
                    raise RuntimeError('Gift Draw shortcut was not found on the main menu.')
                tap(GIFT_DRAW_SHORTCUT)
                overview = wait_for_screen(wait, gift_overview, 'the Gift Draw menu')
            draw, _ = overview
            if draw:
                tap(draw)
                pick_ready = True
    opened = 0
    if pick_ready:
        while opened < limit:
            if not selection_visible:
                wait_for_screen(wait, lambda screen: gift_pick_screen(screen) or None,
                                'the gift selection screen', interval=GIFT_POLL_INTERVAL)
            confirm, draw_again = open_one_gift()
            opened += 1
            print(f'🎁 Gift Opened · {opened}/{limit}')
            if on_status:
                on_status(f'Gift Draw · {opened}/{limit}')
            if opened == limit or not draw_again:
                tap(confirm)
                break
            tap(draw_again)
            selection_visible = False
    exit_state = wait_for_screen(wait, exit_screen, 'the Gift Draw close button or main menu')
    if exit_state:
        tap(exit_state[0])
        wait_for_screen(wait, lambda screen:
                             True if gift_main_menu(screen) else None,
                             'the main menu')
    return opened
