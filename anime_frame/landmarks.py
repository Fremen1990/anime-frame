"""Hand, face, and pose landmarks for one mirrored frame."""

from __future__ import annotations

import os
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


class Landmarks:
    def __init__(self, models: Path) -> None:
        self._hands = HandLandmarker.create_from_options(
            HandLandmarkerOptions(
                base_options=_base(models / "hand_landmarker.task"),
                running_mode=RunningMode.VIDEO,
                num_hands=2,
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
            )
        )

    def detect(
        self, frame_bgr: np.ndarray, timestamp_ms: int
    ) -> tuple[list[np.ndarray], np.ndarray | None, np.ndarray | None]:
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
        return hands, face, body

    def close(self) -> None:
        self._hands.close()
        self._face.close()
        self._pose.close()
