"""Classify visible unopened mystery boxes from local reference images."""
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from adb import device_capture_screen
from config import DEVICE_IP, DEVICE_PORT
from screen_text import save_evidence


BOX_TYPES = ('wood', 'silver', 'gold', 'rainbow')


@lru_cache(maxsize=1)
def references():
    directory = Path(__file__).parent / 'templates'
    result = {}
    for name in BOX_TYPES:
        image = cv2.imread(str(directory / f'BOX_TYPE_{name.upper()}.png'))
        if image is None:
            raise RuntimeError(f'Missing box reference image: {name}')
        result[name] = image
    return result


def colour_similarity(image, template):
    image = cv2.resize(image, (64, 64))
    template = cv2.resize(template, (64, 64))
    # Compare actual colour as well as shape; wood and gold share similar outlines.
    difference = np.mean(np.abs(image.astype(float) - template.astype(float)))
    return max(0.0, 1.0 - difference / 100.0)


def detect_box_types(screen, expected_count):
    if screen is None or screen.ndim != 3 or screen.shape[0] < 100:
        return None
    if type(expected_count) is not int or not 0 <= expected_count <= 20:
        return None
    normalized = cv2.resize(screen, (1280, 720))
    area = normalized[135:555, 90:1190]
    candidates = []
    for name, template in references().items():
        for scale in (0.60, 0.70, 0.80, 0.90, 1.0, 1280 / 1200, 1.15, 1.25, 1.40):
            width = round(template.shape[1] * scale)
            height = round(template.shape[0] * scale)
            resized = cv2.resize(template, (width, height))
            matches = cv2.matchTemplate(area, resized, cv2.TM_CCOEFF_NORMED)
            for _ in range(20):
                _, score, _, (x, y) = cv2.minMaxLoc(matches)
                if score < 0.78:
                    break
                patch = area[y:y + height, x:x + width]
                colour = colour_similarity(patch, resized)
                if colour >= 0.65:
                    candidates.append((0.65 * score + 0.35 * colour,
                                       name, x, y, width, height))
                matches[max(0, y - height // 2):y + height // 2 + 1,
                        max(0, x - width // 2):x + width // 2 + 1] = -1
    selected = []
    for candidate in sorted(candidates, reverse=True):
        score, name, x, y, width, height = candidate
        center = (x + width / 2, y + height / 2)
        if any(abs(center[0] - (other[2] + other[4] / 2)) < 0.6 * max(width, other[4])
               and abs(center[1] - (other[3] + other[5] / 2)) < 0.6 * max(height, other[5])
               for other in selected):
            continue
        ambiguous = any(
            other[1] != name and other[0] >= score - 0.04
            and abs(center[0] - (other[2] + other[4] / 2)) < 0.6 * max(width, other[4])
            and abs(center[1] - (other[3] + other[5] / 2)) < 0.6 * max(height, other[5])
            for other in candidates
        )
        if ambiguous:
            candidate = (score, 'unknown', x, y, width, height)
        selected.append(candidate)
    if len(selected) > expected_count:
        return None
    counts = Counter(candidate[1] for candidate in selected)
    result = {name: counts[name] for name in BOX_TYPES}
    result['unknown'] = expected_count - sum(result.values())
    return result


def read_box_types(expected_count):
    previous = None
    time.sleep(0.8)
    for attempt in range(3):
        screen = device_capture_screen(DEVICE_IP, DEVICE_PORT)
        counts = detect_box_types(screen, expected_count)
        if counts is not None and counts == previous:
            evidence = save_evidence(screen, 'mystery-box-types')
            return counts, evidence
        previous = counts
        time.sleep(0.5)
    evidence = save_evidence(screen, 'mystery-box-types-unknown')
    return None, evidence
