"""One optional jump sequence after the opening gameplay controls are ready."""
import time
from dataclasses import dataclass

from adb import device_tap
from config import DEVICE_IP, DEVICE_PORT
from detection import detect_templates


def gameplay_controls_visible(screen):
    if screen is None or screen.shape[:2] != (720, 1280):
        return None
    return bool(
        detect_templates(screen, ['START_JUMP_CONTROL.png'], (35, 570, 285, 689))
        and detect_templates(screen, ['START_SLIDE_CONTROL.png'], (1000, 570, 1250, 689))
    )


@dataclass
class OpeningJumps:
    deadline: float
    fast_start: bool
    activated: bool = False
    hidden_frames: int = 0
    visible_frames: int = 0

    def observe(self, screen, wait):
        if time.monotonic() >= self.deadline:
            print('Warning: Skipping opening jumps; normal controls were not confirmed in time.')
            return True
        if self.fast_start and not self.activated:
            return False
        visible = gameplay_controls_visible(screen)
        if visible is None:
            return False
        if self.fast_start and self.hidden_frames < 2:
            # Wait for a visible transition through the boost before sending taps.
            self.hidden_frames = 0 if visible else self.hidden_frames + 1
            return False
        self.visible_frames = self.visible_frames + 1 if visible else 0
        if self.visible_frames < 2:
            return False
        print('Opening jumps: 7 taps.')
        for index in range(7):
            if index:
                wait(0.45)
            device_tap(DEVICE_IP, DEVICE_PORT, 160, 630)
        return True
