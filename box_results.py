"""Read the xN box counter on the 1280x720 result screen."""
import re
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path
from subprocess import TimeoutExpired

import cv2
import numpy as np

from adb import device_capture_screen, stop_signal
from config import DEVICE_IP, DEVICE_PORT
from detection import detect_stage
from round_rewards import read_rewards
from screen_text import read_text, save_evidence

RESULT_SETTLE_SECONDS = 2.5
RESULT_SAMPLE_SECONDS = 0.65
RESULT_CAPTURE_LIMIT = 15
REWARD_STABLE_FRAMES = 3
RESULT_READ_SECONDS = 9.5
BOX_OCR_SECONDS = 2.4
BOX_COUNTER = (1065, 207, 1127, 257)


class ResultConnectionLost(Exception):
    """A connection dialog interrupted the results screen."""


def parse_count(lines):
    text = ' '.join(line['text'] for line in lines)
    matches = re.findall(r'[xX×]\s*(\d{1,2})(?!\d)', text)
    values = {int(value) for value in matches if 0 <= int(value) <= 20}
    return next(iter(values)) if len(values) == 1 else None


@lru_cache(maxsize=1)
def result_box_template():
    template = cv2.imread(str(Path(__file__).parent / 'templates' / 'RESULT_BOX_ICON.png'))
    if template is None:
        raise RuntimeError('Result box icon template is missing.')
    return cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)


@lru_cache(maxsize=1)
def result_box_counters():
    path = Path(__file__).parent / 'templates' / 'RESULT_BOX_COUNTERS.png'
    sheet = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    return None if sheet is None else sheet.reshape(3, 50, 62) > 0


def count_from_screen(screen):
    if screen is None or screen.shape[:2] != (720, 1280):
        return None
    area = screen[185:285, 975:1140]
    match = cv2.matchTemplate(cv2.cvtColor(area, cv2.COLOR_BGR2GRAY),
                              result_box_template(), cv2.TM_CCOEFF_NORMED)
    if cv2.minMaxLoc(match)[1] >= 0.85:
        templates = result_box_counters()
        if templates is not None:
            x1, y1, x2, y2 = BOX_COUNTER
            mask = cv2.cvtColor(screen[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY) <= 95
            errors = np.mean(mask != templates, axis=(1, 2))
            first, second = np.argsort(errors)[:2]
            if errors[first] < 0.045 and errors[second] - errors[first] > 0.018:
                return int(first) + 1
        return None
    # A genuinely empty counter area has the same flat panel colour as below it.
    # An unreadable icon/counter is unknown rather than a zero-box round.
    reference = np.median(screen[290:305, 980:1120], axis=(0, 1))
    panel = screen[195:275, 985:1130].astype(float)
    uniform_fraction = np.mean(np.max(np.abs(panel - reference), axis=2) < 18)
    return 0 if uniform_fraction >= 0.985 else None


def read_unusual_box_count(screen, deadline):
    # Run OCR once on a settled counter. The two crops share one short time budget.
    deadline = min(deadline, time.monotonic() + BOX_OCR_SECONDS)
    for counter in (screen[200:267, 1058:1130], screen[185:285, 975:1140]):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        crop = cv2.resize(counter, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR)
        count = parse_count(read_text(crop, timeout=remaining))
        if count is not None:
            return count
    return None


def wait_for_result_sample(seconds):
    stop = stop_signal.get()
    if stop is None:
        time.sleep(seconds)
    elif stop.wait(seconds):
        raise KeyboardInterrupt


def check_result_stage(screen, expected_stage):
    stage = detect_stage(screen, ['ANTI_BOT', 'CONNECTION_LOST', expected_stage])
    if stage == 'ANTI_BOT':
        raise RuntimeError('Player verification required. Complete it in LDPlayer, then start again.')
    if stage == 'CONNECTION_LOST':
        raise ResultConnectionLost
    return stage == expected_stage


def read_result_screen(initial_screen):
    box_observations = Counter()
    last_amounts = {}
    streaks = Counter()
    rewards = {}
    confirmed_boxes = None
    previous_box_crop = None
    stable_box_crop = False
    evidence_screen = initial_screen
    check_result_stage(initial_screen, 'GAME_COMPLETE')
    started = time.monotonic()
    deadline = started + RESULT_READ_SECONDS
    sample_at = started + RESULT_SETTLE_SECONDS
    for _ in range(RESULT_CAPTURE_LIMIT):
        now = time.monotonic()
        if now >= deadline or sample_at >= deadline:
            break
        if sample_at > now:
            wait_for_result_sample(sample_at - now)
        sample_at = time.monotonic() + RESULT_SAMPLE_SECONDS
        last_screen = device_capture_screen(DEVICE_IP, DEVICE_PORT)
        if not check_result_stage(last_screen, 'GAME_COMPLETE'):
            last_amounts = {}
            streaks.clear()
            rewards = {}
            previous_box_crop = None
            stable_box_crop = False
            continue
        evidence_screen = last_screen
        amounts = read_rewards(last_screen, settled_only=True)
        streaks = Counter({name: streaks[name] + 1 if amount == last_amounts.get(name) else 1
                           for name, amount in amounts.items()})
        last_amounts = amounts
        rewards = {name: amount for name, amount in amounts.items()
                   if streaks[name] >= REWARD_STABLE_FRAMES}
        if confirmed_boxes is None:
            count = count_from_screen(last_screen)
            if count is not None:
                box_observations[count] += 1
                if box_observations[count] >= 2:
                    confirmed_boxes = count
            box_crop = last_screen[195:275, 985:1130]
            stable_box_crop = np.array_equal(box_crop, previous_box_crop)
            previous_box_crop = box_crop
        if len(rewards) == 2 and (confirmed_boxes is not None or stable_box_crop):
            break
    if confirmed_boxes is None and stable_box_crop:
        try:
            confirmed_boxes = read_unusual_box_count(evidence_screen, deadline)
        except (RuntimeError, OSError, ValueError, TimeoutExpired) as error:
            print(f'⚠️ Box count could not be read: {error}')
    label = 'result-boxes-unknown' if confirmed_boxes is None else f'result-{confirmed_boxes}-boxes'
    return confirmed_boxes, save_evidence(evidence_screen, label), rewards
