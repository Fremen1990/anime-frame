"""Pure landmark math shared by every gesture.

Points are NumPy arrays of x, y in the same units as each other. Hand rows are
the 21-point MediaPipe hand. Face rows are the face-landmarker mesh. Body rows
are the 33-point pose landmarker. Nothing here opens a camera.
"""

from __future__ import annotations

from collections import deque

import numpy as np

WRIST = 0
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_PIP, PINKY_TIP = 18, 20

FOREHEAD = 10
CHIN = 152

STRAIGHT_RATIO = 0.8
TIP_GAP_RATIO = 0.5
FOREHEAD_REACH = 0.2
SAMPLE_INTERVAL = 0.1
SAMPLES_TO_FIRE = 8
WINDOW_SIZE = 10
FAILURES_TO_CLEAR = 3


def _as_points(points: np.ndarray | None, minimum: int) -> np.ndarray | None:
    if points is None:
        return None
    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or array.shape[0] < minimum or array.shape[1] < 2:
        return None
    return array


def _hands(hands: list[np.ndarray] | None):
    if not hands:
        return
    for hand in hands:
        array = _as_points(hand, 21)
        if array is not None:
            yield array


def _distance(a: np.ndarray, b: np.ndarray) -> float:
    offset = np.asarray(a[:2], dtype=np.float64) - np.asarray(b[:2], dtype=np.float64)
    return float(np.hypot(offset[0], offset[1]))


def _extended(hand: np.ndarray, tip: int, pip: int) -> bool:
    return _distance(hand[tip], hand[WRIST]) > _distance(hand[pip], hand[WRIST])


def _folded(hand: np.ndarray, tip: int, pip: int) -> bool:
    return _distance(hand[tip], hand[WRIST]) < _distance(hand[pip], hand[WRIST])


def _straight(hand: np.ndarray, mcp: int, pip: int, tip: int) -> bool:
    span = _distance(hand[mcp], hand[pip]) + _distance(hand[pip], hand[tip])
    if span <= 1e-6:
        return False
    return _distance(hand[mcp], hand[tip]) >= STRAIGHT_RATIO * span


def fingers_together(hand: np.ndarray) -> bool:
    """Index and middle extended, adjacent, and straight; ring and pinky folded.

    The thumb is ignored. This is the Goku Instant Transmission finger test.
    """
    array = _as_points(hand, 21)
    if array is None:
        return False
    if not (_extended(array, INDEX_TIP, INDEX_PIP) and _extended(array, MIDDLE_TIP, MIDDLE_PIP)):
        return False
    if not (_straight(array, INDEX_MCP, INDEX_PIP, INDEX_TIP) and _straight(array, MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP)):
        return False
    if not (_folded(array, RING_TIP, RING_PIP) and _folded(array, PINKY_TIP, PINKY_PIP)):
        return False
    index_length = _distance(array[INDEX_TIP], array[INDEX_MCP])
    middle_length = _distance(array[MIDDLE_TIP], array[MIDDLE_MCP])
    shorter = min(index_length, middle_length)
    if shorter <= 1e-6:
        return False
    return _distance(array[INDEX_TIP], array[MIDDLE_TIP]) < TIP_GAP_RATIO * shorter


def face_height(face: np.ndarray) -> float:
    array = _as_points(face, CHIN + 1)
    if array is None:
        return 0.0
    return _distance(array[FOREHEAD], array[CHIN])


def tips_on_forehead(hand: np.ndarray, face: np.ndarray) -> bool:
    """Midpoint of the index and middle tips is within about a fifth of the face height of landmark 10."""
    array = _as_points(hand, 21)
    mesh = _as_points(face, CHIN + 1)
    if array is None or mesh is None:
        return False
    height = _distance(mesh[FOREHEAD], mesh[CHIN])
    if height <= 1e-6:
        return False
    midpoint = (array[INDEX_TIP, :2] + array[MIDDLE_TIP, :2]) / 2.0
    return _distance(midpoint, mesh[FOREHEAD]) <= FOREHEAD_REACH * height


def instant_transmission_pose(hands: list[np.ndarray] | None, face: np.ndarray | None) -> bool:
    if _as_points(face, CHIN + 1) is None:
        return False
    return any(fingers_together(hand) and tips_on_forehead(hand, face) for hand in _hands(hands))


def report_pose(debug: bool, effect_id: str, pose_ok: bool, window: PoseWindow) -> None:
    if not debug or not window.sampled:
        return
    if window.fired:
        print(f"{effect_id}: fired")
    elif window.cleared:
        print(f"{effect_id}: cleared")
    else:
        print(f"{effect_id}: {'yes' if pose_ok else 'no'} ({window.true_count}/{SAMPLES_TO_FIRE})")


class PoseWindow:
    """Shared gesture window.

    Sample about ten times a second. Fire once when eight of the last ten
    samples passed. Three failures in a row clear the window. After a fire,
    the pose must drop before another gesture can fill.
    """

    def __init__(self) -> None:
        self.samples: deque[bool] = deque(maxlen=WINDOW_SIZE)
        self.fail_run = 0
        self.true_count = 0
        self.fired = False
        self.cleared = False
        self.sampled = False
        self._last_time: float | None = None
        self._wait_release = False

    @property
    def progress(self) -> float:
        return min(1.0, self.true_count / SAMPLES_TO_FIRE)

    def update(self, pose_ok: bool, now: float) -> None:
        self.fired = False
        self.cleared = False
        self.sampled = False
        # 0.1 is not exact in binary, so allow a tiny early sample.
        if self._last_time is not None and (now - self._last_time) < SAMPLE_INTERVAL - 1e-4:
            return
        self._last_time = now
        self.sampled = True
        if self._wait_release:
            if not pose_ok:
                self._wait_release = False
                self.samples.clear()
                self.fail_run = 0
                self.true_count = 0
            return
        if pose_ok:
            self.fail_run = 0
            self.samples.append(True)
        else:
            self.fail_run += 1
            if self.fail_run >= FAILURES_TO_CLEAR:
                self.samples.clear()
                self.fail_run = 0
                self.true_count = 0
                self.cleared = True
                return
            self.samples.append(False)
        self.true_count = sum(1 for sample in self.samples if sample)
        if self.true_count >= SAMPLES_TO_FIRE:
            self.fired = True
            self.samples.clear()
            self.true_count = 0
            self.fail_run = 0
            self._wait_release = True
