"""Read the xN box counter on the 1280x720 result screen."""
import re
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from adb import device_capture_screen
from config import DEVICE_IP, DEVICE_PORT
from detection import detect_stage
from screen_text import read_text, save_evidence


def parse_count(lines):
    text = ' '.join(line['text'] for line in lines)
    matches = re.findall(r'[xX×]\s*(\d{1,2})(?!\d)', text)
    values = {int(value) for value in matches if 0 <= int(value) <= 20}
    return next(iter(values)) if len(values) == 1 else None


def count_from_screen(screen):
    if screen is None or screen.shape[:2] != (720, 1280):
        return None
    if not detect_stage(screen, ['GAME_COMPLETE', 'OVERTAKE_BREAK_SCORE']):
        return None
    area = screen[185:285, 975:1140]
    template = cv2.imread(str(Path(__file__).parent / 'templates' / 'RESULT_BOX_ICON.png'))
    if template is None:
        raise RuntimeError('Result box icon template is missing.')
    match = cv2.matchTemplate(cv2.cvtColor(area, cv2.COLOR_BGR2GRAY),
                              cv2.cvtColor(template, cv2.COLOR_BGR2GRAY),
                              cv2.TM_CCOEFF_NORMED)
    if cv2.minMaxLoc(match)[1] >= 0.85:
        # Windows OCR misses x3 when the adjacent box artwork is included.
        # Read the isolated counter first, then retry the wider crop.
        for counter in (screen[200:267, 1058:1130], area):
            crop = cv2.resize(counter, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR)
            count = parse_count(read_text(crop))
            if count is not None:
                return count
        return None
    # A genuinely empty counter area has the same flat panel colour as below it.
    # An unreadable icon/counter is unknown rather than a zero-box round.
    reference = np.median(screen[290:305, 980:1120], axis=(0, 1))
    panel = screen[195:275, 985:1130].astype(float)
    uniform_fraction = np.mean(np.max(np.abs(panel - reference), axis=2) < 18)
    return 0 if uniform_fraction >= 0.985 else None


def read_result_boxes(initial_screen):
    observations = Counter()
    last_screen = initial_screen
    time.sleep(1)
    for attempt in range(3):
        last_screen = device_capture_screen(DEVICE_IP, DEVICE_PORT)
        count = count_from_screen(last_screen)
        if count is not None:
            observations[count] += 1
            if observations[count] >= 2:
                evidence = save_evidence(last_screen, f'result-{count}-boxes')
                return count, evidence
        time.sleep(0.5)
    evidence = save_evidence(last_screen, 'result-boxes-unknown')
    return None, evidence
