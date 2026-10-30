"""Optional hair segmentation, kept off the camera thread."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from anime_frame.hair_geometry import head_anchor
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.tasks.python.vision import ImageSegmenter, ImageSegmenterOptions, RunningMode


class HairTracker:
    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="anime-hair")
        self._segmenter: ImageSegmenter | None = None
        self._future: Future | None = None
        self._generation = 0
        self._last_submit = float("-inf")
        self._latest: tuple[float, np.ndarray] | None = None
        self.reference_anchor = None
        self._pending_anchor = None

    def _infer(self, generation: int, frame: np.ndarray, timestamp_ms: int, now: float):
        if self._segmenter is None:
            self._segmenter = ImageSegmenter.create_from_options(
                ImageSegmenterOptions(
                    base_options=BaseOptions(
                        model_asset_path=str(self.model_path), delegate=BaseOptions.Delegate.CPU
                    ),
                    running_mode=RunningMode.VIDEO,
                    output_confidence_masks=True,
                    output_category_mask=False,
                )
            )
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self._segmenter.segment_for_video(image, timestamp_ms)
        masks = result.confidence_masks or []
        if not masks:
            return generation, now, None
        raw = np.array(np.squeeze(masks[1 if len(masks) > 1 else 0].numpy_view()), dtype=np.float32, copy=True)
        if raw.shape != frame.shape[:2]:
            raw = cv2.resize(raw, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_LINEAR)
        return generation, now, np.clip(raw, 0.0, 1.0)

    def sample(self, frame: np.ndarray, timestamp_ms: int, now: float, face: np.ndarray | None = None) -> tuple[np.ndarray | None, float | None]:
        if self._future is not None and self._future.done():
            future, self._future = self._future, None
            try:
                generation, stamp, mask = future.result()
                if generation == self._generation and mask is not None:
                    self._latest = (stamp, mask)
                    self.reference_anchor = self._pending_anchor
            except Exception as exc:
                print(f"Hair segmentation unavailable: {exc}")
        if self._future is None and now - self._last_submit >= 0.1:
            self._last_submit = now
            self._pending_anchor = head_anchor(face)
            self._future = self._executor.submit(self._infer, self._generation, frame.copy(), timestamp_ms, now)
        if self._latest is not None and now - self._latest[0] <= 0.25:
            return self._latest[1], self._latest[0]
        return None, None

    def reset(self) -> None:
        self._generation += 1
        self._latest = None
        self.reference_anchor = None
        self._last_submit = float("-inf")

    def close(self) -> None:
        if self._future is not None:
            try:
                self._future.result()
            except Exception:
                pass
            self._future = None
        if self._segmenter is not None:
            self._executor.submit(self._segmenter.close).result()
            self._segmenter = None
        self._executor.shutdown(wait=True)
