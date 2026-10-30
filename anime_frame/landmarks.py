"""Hand, face, and pose landmarks for one mirrored frame."""

from __future__ import annotations

import os
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("GLOG_minloglevel", "2")

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    HandLandmarker,
    HandLandmarkerOptions,
    PoseLandmarker,
    PoseLandmarkerOptions,
    RunningMode,
)


def _base(path: Path) -> BaseOptions:
    return BaseOptions(model_asset_path=str(path), delegate=BaseOptions.Delegate.CPU)


def _pixels(landmarks, width: int, height: int) -> np.ndarray:
    points = np.empty((len(landmarks), 2), np.float64)
    for index, landmark in enumerate(landmarks):
        points[index, 0] = landmark.x * width
        points[index, 1] = landmark.y * height
    return points


def _world(landmarks) -> np.ndarray:
    return np.asarray([(point.x, point.y, point.z) for point in landmarks], dtype=np.float64)


@dataclass
class LandmarkObservation:
    timestamp_ms: int
    hands: list[np.ndarray] = field(default_factory=list)
    face: np.ndarray | None = None
    body: np.ndarray | None = None
    hand_world: list[np.ndarray] = field(default_factory=list)
    body_world: np.ndarray | None = None
    body_confidence: np.ndarray | None = None


class Landmarks:
    """Pose, hands and face on a worker thread. The camera loop only reuses the latest result."""

    def __init__(self, models: Path) -> None:
        self._models = models
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="anime-pose")
        self._hands: HandLandmarker | None = None
        self._face: FaceLandmarker | None = None
        self._pose: PoseLandmarker | None = None
        self._future: Future | None = None
        self._generation = 0
        self._last_submit = float("-inf")
        self._latest: tuple[float, LandmarkObservation] | None = None

    def sample(self, frame_bgr: np.ndarray, timestamp_ms: int, now: float) -> tuple[LandmarkObservation | None, float | None]:
        if self._future is not None and self._future.done():
            future, self._future = self._future, None
            try:
                generation, _stamp, observation = future.result()
                if generation == self._generation and observation is not None:
                    # Age starts when the camera thread can use the pose, not when it was submitted.
                    self._latest = (now, observation)
            except Exception as exc:
                print(f"Landmark detection unavailable: {exc}")
        if self._future is None and now - self._last_submit >= 0.09:
            self._last_submit = now
            self._future = self._executor.submit(self._infer, self._generation, frame_bgr.copy(), int(timestamp_ms), now)
        if self._latest is None:
            return None, None
        return self._latest[1], self._latest[0]

    def reset(self) -> None:
        self._generation += 1
        self._latest = None
        self._last_submit = float("-inf")

    def _ensure(self) -> None:
        if self._hands is not None:
            return
        models = self._models
        self._hands = HandLandmarker.create_from_options(
            HandLandmarkerOptions(
                base_options=_base(models / "hand_landmarker.task"),
                running_mode=RunningMode.VIDEO,
                num_hands=2,
                min_hand_detection_confidence=0.3,
                min_hand_presence_confidence=0.3,
                min_tracking_confidence=0.3,
            )
        )
        self._face = FaceLandmarker.create_from_options(
            FaceLandmarkerOptions(
                base_options=_base(models / "face_landmarker.task"),
                running_mode=RunningMode.VIDEO,
                num_faces=1,
            )
        )
        self._pose = PoseLandmarker.create_from_options(
            PoseLandmarkerOptions(
                base_options=_base(models / "pose_landmarker_lite.task"),
                running_mode=RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=0.3,
                min_pose_presence_confidence=0.3,
                min_tracking_confidence=0.3,
            )
        )

    def _infer(self, generation: int, frame_bgr: np.ndarray, timestamp_ms: int, now: float):
        self._ensure()
        return generation, now, self._detect(frame_bgr, timestamp_ms)

    def _detect(self, frame_bgr: np.ndarray, timestamp_ms: int) -> LandmarkObservation:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        if not rgb.flags["C_CONTIGUOUS"]:
            rgb = np.ascontiguousarray(rgb)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        height, width = frame_bgr.shape[:2]
        hands_result = self._hands.detect_for_video(image, timestamp_ms)
        face_result = self._face.detect_for_video(image, timestamp_ms)
        pose_result = self._pose.detect_for_video(image, timestamp_ms)
        hands = [_pixels(hand, width, height) for hand in (hands_result.hand_landmarks or [])]
        face = None
        if face_result.face_landmarks:
            face = _pixels(face_result.face_landmarks[0], width, height)
        body = None
        if pose_result.pose_landmarks:
            body = _pixels(pose_result.pose_landmarks[0], width, height)
        hand_world = [_world(hand) for hand in (hands_result.hand_world_landmarks or [])]
        body_world = None
        confidence = None
        if pose_result.pose_world_landmarks:
            body_world = _world(pose_result.pose_world_landmarks[0])
        if pose_result.pose_landmarks:
            confidence = np.asarray(
                [min(float(point.visibility or 0.0), float(point.presence or 0.0))
                 for point in pose_result.pose_landmarks[0]],
                dtype=np.float64,
            )
        return LandmarkObservation(timestamp_ms, hands, face, body, hand_world, body_world, confidence)

    def close(self) -> None:
        self._generation += 1
        if self._future is not None:
            try:
                self._future.result()
            except Exception:
                pass
            self._future = None
        if self._hands is not None:
            def _close() -> None:
                self._hands.close()
                self._face.close()
                self._pose.close()

            self._executor.submit(_close).result()
            self._hands = self._face = self._pose = None
        self._executor.shutdown(wait=True)
