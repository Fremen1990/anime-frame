"""Person mask from the landscape selfie segmenter."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("GLOG_minloglevel", "2")

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.tasks.python.vision import ImageSegmenter, ImageSegmenterOptions, RunningMode

_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))


class Segmenter:
    """Landscape selfie segmenter. The person class is thresholded at 0.5.

    The model ships one confidence mask labeled "selfie". That mask is the
    person. A small close keeps the rim continuous. The bounding box of the
    latest mask is cached on this object.
    """

    def __init__(self, model_path: Path) -> None:
        options = ImageSegmenterOptions(
            base_options=BaseOptions(
                model_asset_path=str(model_path),
                delegate=BaseOptions.Delegate.CPU,
            ),
            running_mode=RunningMode.VIDEO,
            output_confidence_masks=True,
            output_category_mask=False,
        )
        self._segmenter = ImageSegmenter.create_from_options(options)
        self.bbox: tuple[int, int, int, int] | None = None

    def segment(self, frame_bgr: np.ndarray, timestamp_ms: int) -> np.ndarray:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        if not rgb.flags["C_CONTIGUOUS"]:
            rgb = np.ascontiguousarray(rgb)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._segmenter.segment_for_video(image, timestamp_ms)
        height, width = frame_bgr.shape[:2]
        masks = result.confidence_masks or []
        if not masks:
            raw = np.zeros((height, width), np.float32)
        else:
            # One mask: the selfie (person). Two masks: index 1 is the person.
            choice = masks[1] if len(masks) > 1 else masks[0]
            raw = np.array(np.squeeze(choice.numpy_view()), dtype=np.float32, copy=True)
            if raw.shape[:2] != (height, width):
                raw = cv2.resize(raw, (width, height), interpolation=cv2.INTER_LINEAR)
        binary = (raw >= 0.5).astype(np.uint8)
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, _KERNEL)
        mask = closed.astype(np.float32)
        points = cv2.findNonZero(closed)
        if points is None:
            self.bbox = None
        else:
            x, y, box_w, box_h = cv2.boundingRect(points)
            self.bbox = (x, y, x + box_w, y + box_h)
        return mask

    def close(self) -> None:
        self._segmenter.close()
