"""Pure landmark math shared by every gesture.

Points are NumPy arrays of x, y in the same units as each other. Hand rows are
the 21-point MediaPipe hand. Face rows are the face-landmarker mesh. Body rows
are the 33-point pose landmarker. Nothing here opens a camera.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

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


def _body_scale(body: np.ndarray | None, confidence: np.ndarray | None = None) -> float:
    points = _as_points(body, 25)
    if points is None:
        return 0.0
    # Elbows are often hidden by a chair. Shoulders and wrists are the pose.
    if confidence is not None and any(confidence[index] < 0.35 for index in (11, 12, 15, 16)):
        return 0.0
    return _distance(points[11], points[12])


def _paired_hands(hands: list[np.ndarray], body: np.ndarray, scale: float) -> tuple[np.ndarray, np.ndarray] | None:
    valid = list(_hands(hands))
    if len(valid) < 2:
        return None
    wrists = (body[15], body[16])
    choices = []
    for first in range(len(valid)):
        for second in range(len(valid)):
            if first == second:
                continue
            distances = (_distance(valid[first][WRIST], wrists[0]), _distance(valid[second][WRIST], wrists[1]))
            choices.append((sum(distances), max(distances), valid[first], valid[second]))
    _, furthest, left, right = min(choices, key=lambda item: item[0])
    return (left, right) if furthest < 1.6 * scale else None


def _fist(hand: np.ndarray) -> bool:
    return all(_folded(hand, tip, pip) for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)))


def super_saiyan_pose(hands: list[np.ndarray], body: np.ndarray | None, confidence: np.ndarray | None = None) -> bool:
    scale = _body_scale(body, confidence)
    if scale <= 1e-6 or (pair := _paired_hands(hands, body, scale)) is None:
        return False
    center_x = (body[11, 0] + body[12, 0]) / 2.0
    wrists = (body[15], body[16])
    return (
        all(_fist(hand) for hand in pair)
        and abs(wrists[0][0] - wrists[1][0]) > 1.05 * scale
        and all(abs(wrist[0] - center_x) > 0.45 * scale for wrist in wrists)
        and all(min(abs(wrist[1] - shoulder[1]) for shoulder in (body[11], body[12])) < 0.6 * scale for wrist in wrists)
    )


def kamehameha_pose(hands: list[np.ndarray], body: np.ndarray | None, confidence: np.ndarray | None = None) -> bool:
    """Cupped wrists beside either side of the torso, allowing one hidden hand."""
    scale = _body_scale(body, confidence)
    points = _as_points(body, 25)
    if scale <= 1e-6 or points is None:
        return False
    wrists = (points[15], points[16])
    if _distance(*wrists) > 1.05 * scale:
        return False
    center = (wrists[0][:2] + wrists[1][:2]) / 2.0
    shoulder_x = (points[11, 0] + points[12, 0]) / 2.0
    if not 0.35 * scale < abs(center[0] - shoulder_x) < 1.5 * scale:
        return False
    shoulder_y = (points[11, 1] + points[12, 1]) / 2.0
    hip_y = (points[23, 1] + points[24, 1]) / 2.0
    if not (shoulder_y + 0.08 * scale < center[1] < hip_y + 0.45 * scale):
        return False
    # Cupped hands often hide both meshes. Wrist position is enough; a visible fist does not count.
    detected = list(_hands(hands))
    if not detected:
        return True
    return any(not _fist(hand) and min(_distance(hand[0], wrist) for wrist in wrists) < 0.8 * scale for hand in detected)


def hands_in_front(body: np.ndarray | None, confidence: np.ndarray | None = None) -> bool:
    """Both wrists together in front of the upper torso; depth is checked separately."""
    scale = _body_scale(body, confidence)
    points = _as_points(body, 25)
    if scale <= 1e-6 or points is None:
        return False
    center = (points[15] + points[16]) / 2.0
    shoulders = (points[11] + points[12]) / 2.0
    hips = (points[23] + points[24]) / 2.0
    return (
        _distance(points[15], points[16]) < 1.2 * scale
        and abs(center[0] - shoulders[0]) < 0.65 * scale
        and shoulders[1] - 0.5 * scale < center[1] < hips[1] + 0.2 * scale
    )


def kikoho_pose(hands: list[np.ndarray], body: np.ndarray | None, confidence: np.ndarray | None = None) -> bool:
    """Wrists together in front of the chest. Finger shape is ignored, and one hand mesh is enough."""
    del hands
    scale = _body_scale(body, confidence)
    points = _as_points(body, 25)
    if scale <= 1e-6 or points is None:
        return False
    left, right = points[15], points[16]
    if _distance(left, right) > 0.95 * scale:
        return False
    center = (left[:2] + right[:2]) / 2.0
    sternum_x = (points[11, 0] + points[12, 0]) / 2.0
    if abs(float(center[0]) - sternum_x) > 0.48 * scale:
        return False
    shoulder_y = (points[11, 1] + points[12, 1]) / 2.0
    hip_y = (points[23, 1] + points[24, 1]) / 2.0
    torso = hip_y - shoulder_y
    if torso <= scale * 0.2:
        return False
    return shoulder_y - 0.12 * scale < float(center[1]) < shoulder_y + 0.72 * torso


@dataclass(frozen=True)
class ForwardBaseline:
    relative_depth: tuple[float, float]
    elbow_angles: tuple[float, float]
    shoulder_width: float


def _elbow_angle(world: np.ndarray, shoulder: int, elbow: int, wrist: int) -> float:
    first = world[shoulder] - world[elbow]
    second = world[wrist] - world[elbow]
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    if denominator <= 1e-6:
        return 0.0
    return float(np.degrees(np.arccos(np.clip(np.dot(first, second) / denominator, -1, 1))))


def forward_baseline(world: np.ndarray | None, confidence: np.ndarray | None = None) -> ForwardBaseline | None:
    if world is None or np.asarray(world).shape != (33, 3):
        return None
    joints = [11, 12, 13, 14, 15, 16]
    if not np.isfinite(np.asarray(world)[joints]).all():
        return None
    if confidence is not None and (len(confidence) < 17 or not np.isfinite(confidence[joints]).all() or np.any(confidence[joints] < 0.35)):
        return None
    scale = float(np.linalg.norm(world[11] - world[12]))
    if scale <= 1e-6:
        return None
    return ForwardBaseline(
        (float(world[15, 2] - world[11, 2]), float(world[16, 2] - world[12, 2])),
        (_elbow_angle(world, 11, 13, 15), _elbow_angle(world, 12, 14, 16)),
        scale,
    )


def arm_reach(body: np.ndarray | None) -> tuple[float, float] | None:
    """Mean shoulder-to-wrist length, and the mean wrist height, in image pixels."""
    points = _as_points(body, 17)
    if points is None:
        return None
    reach = (_distance(points[11], points[15]) + _distance(points[12], points[16])) / 2.0
    wrist_y = float(points[15, 1] + points[16, 1]) / 2.0
    return reach, wrist_y


def aimed_at_camera(world: np.ndarray | None, confidence: np.ndarray | None = None) -> bool:
    """Both wrists are closer to the lens than the elbows and the shoulders.

    MediaPipe's z gets smaller as a joint moves toward the camera. A lean of
    the whole body does not count, because every joint moves together.
    """
    if forward_baseline(world, confidence) is None or world is None:
        return False
    points = np.asarray(world)
    for shoulder, elbow, wrist in ((11, 13, 15), (12, 14, 16)):
        wrist_z = float(points[wrist, 2])
        if wrist_z >= float(points[elbow, 2]) - 0.025 or wrist_z >= float(points[shoulder, 2]) - 0.05:
            return False
    return True


def pushed_forward(baseline: ForwardBaseline, world: np.ndarray | None, confidence: np.ndarray | None = None) -> bool:
    current = forward_baseline(world, confidence)
    if current is None:
        return False
    depth = [start - end for start, end in zip(baseline.relative_depth, current.relative_depth)]
    opening = [end - start for start, end in zip(baseline.elbow_angles, current.elbow_angles)]
    return min(depth) > 0.09 * baseline.shoulder_width and sum(opening) / 2.0 > 6.0


def report_pose(debug: bool, effect_id: str, pose_ok: bool, window: PoseWindow) -> None:
    if not debug or not window.sampled:
        return
    if window.fired:
        print(f"{effect_id}: fired")
    elif window.cleared:
        print(f"{effect_id}: cleared")
    else:
        print(f"{effect_id}: {'yes' if pose_ok else 'no'} ({window.true_count}/{window.samples_to_fire})")


class PoseWindow:
    """Shared gesture window.

    Sample about ten times a second. The default fire is eight of the last ten
    samples, and three failures in a row clear the window. A caller can ask
    for a shorter hold. After a fire, the pose must drop before another
    gesture can fill.
    """

    def __init__(self, samples_to_fire: int = SAMPLES_TO_FIRE, failures_to_clear: int = FAILURES_TO_CLEAR) -> None:
        self.samples_to_fire = samples_to_fire
        self.failures_to_clear = failures_to_clear
        self.samples: deque[bool] = deque(maxlen=WINDOW_SIZE)
        self.fail_run = 0
        self.true_count = 0
        self.fired = False
        self.cleared = False
        self.sampled = False
        self._last_time: float | None = None
        self._wait_release = False
        self._last_observation_id: int | None = None

    @property
    def progress(self) -> float:
        return min(1.0, self.true_count / self.samples_to_fire)

    def update(self, pose_ok: bool, now: float, observation_id: int | None = None) -> None:
        self.fired = False
        self.cleared = False
        self.sampled = False
        if observation_id is not None and observation_id == self._last_observation_id:
            return
        # 0.1 is not exact in binary, so allow a tiny early sample.
        # A new observation that arrives early is kept for the next interval
        # instead of being discarded.
        if self._last_time is not None and (now - self._last_time) < SAMPLE_INTERVAL - 1e-4:
            return
        if observation_id is not None:
            self._last_observation_id = observation_id
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
            if self.fail_run >= self.failures_to_clear:
                self.samples.clear()
                self.fail_run = 0
                self.true_count = 0
                self.cleared = True
                return
            self.samples.append(False)
        self.true_count = sum(1 for sample in self.samples if sample)
        if self.true_count >= self.samples_to_fire:
            self.fired = True
            self.samples.clear()
            self.true_count = 0
            self.fail_run = 0
            self._wait_release = True

    def arm_release(self) -> None:
        """A keyboard fire also requires the pose to drop before another fire."""
        self.samples.clear()
        self.true_count = 0
        self.fail_run = 0
        self._wait_release = True
