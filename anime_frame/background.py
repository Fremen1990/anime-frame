"""Empty-room image for effects that replace the person."""

from __future__ import annotations

import math

import numpy as np

CAPTURE_SECONDS = 3.0
MEDIAN_WINDOW = 0.5
STEP_OUT = "Step out of the chair."
COME_BACK = "You can return."


class Background:
    def __init__(self) -> None:
        self.image: np.ndarray | None = None
        self.capturing = False
        self._started = 0.0
        self._frames: list[tuple[float, np.ndarray]] = []

    @property
    def started_at(self) -> float:
        return self._started

    def start(self, now: float) -> None:
        if self.capturing:
            return
        self.capturing = True
        self._started = now
        self._frames = []
        print(STEP_OUT)

    def cancel(self) -> None:
        self.capturing = False
        self._frames = []

    def seconds_left(self, now: float) -> int:
        if not self.capturing:
            return 0
        remaining = CAPTURE_SECONDS - (now - self._started)
        if remaining <= 0:
            return 0
        return int(math.ceil(remaining - 1e-9))

    def update(self, frame: np.ndarray, now: float) -> None:
        if not self.capturing:
            return
        self._frames.append((now, frame.copy()))
        cutoff = now - MEDIAN_WINDOW
        self._frames = [(stamp, sample) for stamp, sample in self._frames if stamp >= cutoff]
        if now - self._started < CAPTURE_SECONDS:
            return
        stack = np.stack([sample for _, sample in self._frames], axis=0)
        self.image = np.median(stack, axis=0).round().astype(np.uint8)
        self.capturing = False
        self._frames = []
        print(COME_BACK)
