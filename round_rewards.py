"""Read the coin and XP values from the 1280×720 game result screen."""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

GLYPH_SIZE = (24, 32)
REWARD_ROWS = {'coins': (380, 430), 'exp': (463, 514)}


def reward_glyphs(row):
    # A darker cutoff keeps adjacent antialiased digits from merging.
    mask = cv2.inRange(row, 0, 110)
    _, _, components, _ = cv2.connectedComponentsWithStats(mask)
    components = sorted(components[1:], key=lambda part: part[0])
    if not components or components[-1][0] + components[-1][2] < 173:
        return None
    glyphs = []
    for x, y, width, height, area in components:
        if area < 10:
            continue
        if 4 <= width <= 12 and 6 <= height <= 15 and 30 <= y + height <= 46:
            glyphs.append(',')
        elif 7 <= width <= 59 and 20 <= height <= 33 and 24 <= y + height <= 44:
            digit = mask[y:y + height, x:x + width]
            parts = (digit,)
            if width > 34:
                # Adjacent characters can touch through a few dark pixels.
                # Split only where there is a narrow connection between two plausible glyphs.
                left = max(8, width - 29)
                right = min(width - 8, 29)
                if left >= right:
                    return None
                ink = np.count_nonzero(digit, axis=0)
                split = left + int(np.argmin(ink[left:right]))
                if ink[split] > 4:
                    return None
                parts = (digit[:, :split], digit[:, split:])
            for part in parts:
                x1, y1, w1, h1 = cv2.boundingRect(part)
                if w1 < 7 or h1 < 20:
                    return None
                glyph = cv2.resize(part[y1:y1 + h1, x1:x1 + w1], GLYPH_SIZE)
                glyphs.append(glyph > 127)
        else:
            return None
    return glyphs


@lru_cache(maxsize=1)
def reward_digit_templates():
    path = Path(__file__).with_name('templates') / 'RESULT_REWARD_DIGITS.png'
    sheet = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    width, height = GLYPH_SIZE
    return np.stack([sheet[:, digit * width:(digit + 1) * width]
                     .reshape(-1, height, width) > 127 for digit in range(10)])


def read_reward_amount(row):
    glyphs = reward_glyphs(row)
    if glyphs is None or not 1 <= len(glyphs) <= 11:
        return None
    templates = reward_digit_templates()
    characters = []
    for glyph in glyphs:
        if isinstance(glyph, str):
            characters.append(glyph)
            continue
        scores = np.mean(glyph != templates, axis=(2, 3)).min(axis=1)
        best, second = np.argsort(scores)[:2]
        if scores[best] > 0.19 or scores[second] - scores[best] < 0.035:
            return None
        characters.append(str(best))
    text = ''.join(characters)
    digits = text.replace(',', '')
    if not digits:
        return None
    amount = int(digits)
    return amount if text == f'{amount:,}' else None


def read_rewards(screen, *, settled_only=False):
    if screen is None or screen.shape != (720, 1280, 3):
        return {}
    amounts = {}
    for name, (top, bottom) in REWARD_ROWS.items():
        if settled_only:
            # Reward particles cross the narrow gap before the large icon.
            # Compare it to the adjacent panel so the check works on different episodes.
            panel_color = np.median(screen[top:bottom, 914:929], axis=(0, 1))
            gap = screen[top:bottom, 837:849]
            occupied = np.max(np.abs(gap.astype(np.float32) - panel_color), axis=2) > 21
            if name == 'coins':
                # A gold boost badge can sparkle into this gap on a settled screen.
                # The moving silver coins are muted and darker than the panel.
                hsv = cv2.cvtColor(gap, cv2.COLOR_BGR2HSV)
                occupied &= (hsv[:, :, 1] < 85) & (hsv[:, :, 2] < 225)
            if np.mean(occupied) > 0.035:
                continue
        row = cv2.cvtColor(screen[top:bottom, 935:1130], cv2.COLOR_BGR2GRAY)
        if np.median(row) < 190:
            continue
        amount = read_reward_amount(row)
        if amount is not None:
            amounts[name] = amount
    return amounts
