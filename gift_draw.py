"""Open earned Gift Draws from the main menu."""
import cv2
import numpy as np

from adb import device_capture_screen, device_tap
from config import DEVICE_IP, DEVICE_PORT
from detection import detect_stage, detect_templates


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


def gift_pick_position(screen):
    if not gift_control(screen, 'HEADER') or not gift_control(screen, 'PICK_TITLE'):
        return None
    x, y = GIFT_PICK_BOTTOM_RIGHT
    patch = cv2.cvtColor(screen[y - 12:y + 12, x - 12:x + 12], cv2.COLOR_BGR2HSV)
    # Once a box is picked, its blue wrapping disappears during the reward reveal.
    blue = cv2.inRange(patch, (92, 50, 45), (135, 255, 255))
    if cv2.countNonZero(blue) >= blue.size / 2:
        return GIFT_PICK_BOTTOM_RIGHT
    return None


def wait_for_screen(wait, find, description, activity='Gift Draw'):
    for _ in range(20):
        screen = device_capture_screen(DEVICE_IP, DEVICE_PORT)
        if detect_stage(screen, ['ANTI_BOT']) == 'ANTI_BOT':
            raise RuntimeError('Player verification required. Complete it in LDPlayer, then start again.')
        if detect_stage(screen, ['CONNECTION_LOST']) == 'CONNECTION_LOST':
            raise RuntimeError(f'Connection lost. {activity} paused. Check LDPlayer before starting again.')
        found = find(screen)
        if found is not None:
            return found
        wait(0.5)
    raise RuntimeError(f'{activity} could not find {description}. Check LDPlayer.')


def draw_gifts(limit, wait, main_screen, *, on_status=None):
    if type(limit) is not int or not 1 <= limit <= 9999:
        raise ValueError('Gift Draw limit must be from 1 to 9999.')
    pick_ready = gift_pick_position(main_screen) is not None
    if not pick_ready and not gift_main_menu(main_screen):
        raise RuntimeError('Gift Draw shortcut was not found on the main menu.')

    def tap(position):
        device_tap(DEVICE_IP, DEVICE_PORT, *position)
        wait(0.8)

    def overview(screen):
        if not gift_control(screen, 'HEADER') or not gift_control(screen, 'CLOSE'):
            return None
        if gift_control(screen, 'DRAW_BUTTON'):
            return (gift_control(screen, 'DRAW_BUTTON', enabled=True), gift_control(screen, 'CLOSE'))
        return None

    def result(screen):
        if gift_control(screen, 'RESULT_TITLE'):
            confirm = gift_control(screen, 'CONFIRM', enabled=True)
            if confirm:
                return confirm, gift_control(screen, 'DRAW_AGAIN', enabled=True)
        return None

    def exit_screen(screen):
        if gift_control(screen, 'HEADER'):
            close = gift_control(screen, 'CLOSE')
            if close:
                return (close,)
        if gift_main_menu(screen):
            return ()
        return None

    close = None
    if not pick_ready:
        tap(GIFT_DRAW_SHORTCUT)
        draw, close = wait_for_screen(wait, overview, 'the Gift Draw menu')
        if draw:
            tap(draw)
            pick_ready = True
    opened = 0
    if pick_ready:
        while opened < limit:
            tap(wait_for_screen(wait, gift_pick_position, 'the bottom-right gift box'))
            confirm, draw_again = wait_for_screen(wait, result, 'the gift result')
            opened += 1
            print(f'🎁 Gift Opened · {opened}/{limit}')
            if on_status:
                on_status(f'Gift Draw · {opened}/{limit}')
            if opened == limit or not draw_again:
                tap(confirm)
                break
            tap(draw_again)
        exit_state = wait_for_screen(wait, exit_screen, 'the Gift Draw close button or main menu')
        close = exit_state[0] if exit_state else None
    if close:
        tap(close)
        wait_for_screen(wait, lambda screen:
                             True if gift_main_menu(screen) else None,
                             'the main menu')
    return opened
